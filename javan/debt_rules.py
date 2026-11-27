"""Debt linkage and payment rules; never infer historical debt matches by name."""
from datetime import datetime, timezone
from uuid import uuid4
import re


def remaining(debt):
    if debt.get('payments') is None:
        return 0 if debt['paid'] else debt['amount']
    return debt['amount'] - sum(p['amount'] for p in debt['payments'])


def validate_debts(data, fail):
    invoices = {i['id']: i for i in data['invoices']}
    linked = set()
    payment_ids = set()
    for d in data['debts']:
        iid = d.get('invoiceId')
        if iid is not None:
            inv = invoices.get(iid) if isinstance(iid, str) else None
            if not inv or iid in linked or inv.get('paymentStatus') != 'نسیه' or inv['finalToman'] != d['amount']:
                fail('ارتباط نسیه و فاکتور نامعتبر یا تکراری است.')
            linked.add(iid)
        payments = d.get('payments')
        if payments is None:
            if iid is not None:
                fail('سوابق پرداخت نسیه متصل ناقص است.')
            continue
        if type(d['amount']) is not int or d['amount'] < 0 or not isinstance(payments, list):
            fail('مبلغ نسیه و فهرست پرداخت‌ها نامعتبر است.')
        for p in payments:
            if not isinstance(p, dict):
                fail('پرداخت نامعتبر است.')
            uid = p.get('id')
            if not isinstance(uid, str) or not uid or uid in payment_ids:
                fail('شناسه پرداخت نامعتبر یا تکراری است.')
            payment_ids.add(uid)
            if type(p.get('amount')) is not int or p['amount'] <= 0 or not isinstance(p.get('date'), str) or not re.fullmatch(r'\d{4}/\d{2}/\d{2}', p['date']):
                fail('مبلغ یا تاریخ پرداخت نامعتبر است.')
        balance = remaining(d)
        if balance < 0 or d['paid'] != (balance == 0):
            fail('مانده نسیه و وضعیت پرداخت همخوان نیستند.')


def reconcile_new_invoices(old, data, fail):
    """Create links only for newly issued credit invoices, not historical invoices."""
    old_invoices = {i['id']: i for i in (old or {}).get('invoices', [])}
    debts = {d['invoiceId']: d for d in data['debts'] if d.get('invoiceId')}
    new_invoices = {i['id']: i for i in data['invoices']}
    for previous in (old or {}).get('debts', []):
        iid = previous.get('invoiceId')
        if not iid:
            continue
        inv = new_invoices.get(iid)
        candidate = debts.get(iid)
        if inv is None or inv.get('paymentStatus') != 'نسیه':
            if previous.get('payments'):
                fail('فاکتور دارای پرداخت است؛ ابتدا اصلاح حساب با مدیر انجام شود.')
            data['debts'] = [d for d in data['debts'] if d.get('invoiceId') != iid]
            debts.pop(iid, None)
        elif candidate is None:
            fail('حذف مستقل نسیه متصل به فاکتور مجاز نیست.')
        elif previous.get('payments') and inv['finalToman'] != previous['amount']:
            fail('مبلغ فاکتور دارای پرداخت قابل تغییر نیست.')
        else:
            candidate['amount'] = inv['finalToman']
            candidate['name'] = inv.get('customerName') or 'مشتری حضوری'
            candidate['paid'] = remaining(candidate) == 0
    for iid, inv in new_invoices.items():
        previous = old_invoices.get(iid)
        if inv.get('paymentStatus') != 'نسیه' or iid in debts:
            continue
        if previous and previous.get('paymentStatus') == 'نسیه':
            continue
        amount = inv['finalToman']
        if type(amount) is not int or amount < 0:
            fail('مبلغ فاکتور نسیه باید تومان صحیح باشد.')
        data['debts'].insert(0, {
            'id': 'debt-' + uuid4().hex, 'invoiceId': iid, 'name': inv.get('customerName') or 'مشتری حضوری',
            'amount': amount, 'date': inv.get('date', ''), 'paid': amount == 0,
            'paidDate': None, 'payments': [], 'createdAt': int(datetime.now(timezone.utc).timestamp()*1000)
        })


def sensitive_change(old, new, reason):
    if reason == 'restore':
        return True
    if not old:
        return False
    for key in ('invoices', 'services', 'debts'):
        current = {d['id']: d for d in new[key]}
        for before in old[key]:
            after = current.get(before['id'])
            if after is None:
                return True
            if before == after:
                continue
            if key != 'debts':
                return True
            # Ordinary append-only receipts are allowed. Reversals, amount edits,
            # identity changes and old settled-record reopening require manager.
            if before['paid'] or before['amount'] != after['amount']:
                return True
            if any(before.get(k) != after.get(k) for k in ('name','invoiceId','date')):
                return True
            prior = before.get('payments') or []
            later = after.get('payments') or []
            if len(later) <= len(prior) or later[:len(prior)] != prior:
                return True
    return False
