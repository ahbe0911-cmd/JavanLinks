"""P0 durable snapshot ledger. Legacy LocalStorage is never written by this layer.

This is a transitional whole-document store, not the normalized P1 ledger.
A successful commit means SQLite has acknowledged a synchronous FULL transaction.
"""
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import re
from pathlib import Path
import sqlite3
from uuid import uuid4
from .storage import atomic_write

MAX_BYTES = 64 * 1024 * 1024
MAX_ROWS = 100_000
LEGACY_KEYS = frozenset({
    'javan_acc_services_v2', 'javan_acc_invoices_v2', 'javan_acc_next_num_v2',
    'javan_acc_logo_v2', 'javan_acc_settings_v2', 'javan_acc_theme_v2',
    'javan_acc_debts_v1',
})


class LedgerError(ValueError):
    pass


def parse_json(raw):
    if not isinstance(raw, str) or len(raw.encode('utf-8')) > MAX_BYTES:
        raise LedgerError('اندازه داده حسابداری نامعتبر است.')
    def no_constant(_):
        raise LedgerError('مقدار عددی غیرمجاز.')
    try:
        return json.loads(raw, parse_constant=no_constant)
    except (ValueError, RecursionError) as exc:
        raise LedgerError('JSON حسابداری نامعتبر است.') from exc


def encode_json(value):
    try:
        text = json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    except (ValueError, TypeError, RecursionError) as exc:
        raise LedgerError('داده حسابداری قابل ذخیره نیست.') from exc
    if len(text.encode('utf-8')) > MAX_BYTES:
        raise LedgerError('حجم دفتر از سقف نسخه آزمایشی بیشتر است.')
    return text


def require(condition, msg):
    if not condition:
        raise LedgerError(msg)


def valid_amount(value):
    # Legacy fractional amounts remain unchanged until explicit reconciliation.
    return type(value) in (int, float) and 0 <= value <= 9_007_199_254_740_991 and math.isfinite(value)


def validate_snapshot(data):
    require(isinstance(data, dict), 'ساختار دفتر نامعتبر است.')
    require(set(data) == {'services', 'invoices', 'debts', 'nextInvoiceNumber', 'customLogo', 'settings', 'theme'},
            'فیلدهای دفتر ناقص یا نامعتبر هستند.')
    for key in ('services', 'invoices', 'debts'):
        rows = data[key]
        require(isinstance(rows, list) and len(rows) <= MAX_ROWS, 'فهرست دفتر نامعتبر است.')
        ids = set()
        numbers = set()
        for row in rows:
            require(isinstance(row, dict), 'رکورد نامعتبر است.')
            uid = row.get('id')
            require(isinstance(uid, str) and 0 < len(uid) <= 256 and uid not in ids, 'شناسه خالی یا تکراری.')
            ids.add(uid)
            if key == 'services':
                require(isinstance(row.get('name'), str) and valid_amount(row.get('price')) and
                        all(row.get(k) is None or isinstance(row.get(k), str) for k in ('category', 'desc')), 'تعرفه خدمت نامعتبر است.')
            elif key == 'debts':
                require(isinstance(row.get('name'), str) and valid_amount(row.get('amount')) and type(row.get('paid')) is bool, 'رکورد نسیه نامعتبر است.')
            else:
                require(isinstance(row.get('invoiceNumber'), (str, int)) and not isinstance(row.get('invoiceNumber'), bool), 'شماره فاکتور نامعتبر است.')
                number = str(row['invoiceNumber'])
                canonical = number.lstrip('0') if number.isascii() and number.isdigit() else number
                require(bool(canonical) and canonical not in numbers, 'شماره فاکتور خالی یا تکراری است.')
                numbers.add(canonical)
                require(all(row.get(k) is None or isinstance(row.get(k), str) for k in ('date', 'customerName', 'customerPhone', 'paymentStatus', 'discountType')), 'متن فاکتور نامعتبر است.')
                require(isinstance(row.get('items'), list) and len(row['items']) <= 10_000, 'اقلام فاکتور نامعتبر است.')
                for item in row['items']:
                    require(isinstance(item, dict) and isinstance(item.get('name'), str)
                            and valid_amount(item.get('price')) and valid_amount(item.get('qty')), 'قیمت یا تعداد نامعتبر است.')
                for field in ('subtotal', 'discountAmount', 'finalToman', 'finalRial'):
                    require(valid_amount(row.get(field)), 'مبلغ تاریخی ناقص یا نامعتبر است؛ نیاز به بررسی دارد.')
    n = data['nextInvoiceNumber']
    require(type(n) is int and 1 <= n <= 9_007_199_254_740_991, 'شمارنده نامعتبر است.')
    require(isinstance(data['settings'], dict) and all(isinstance(v, str) for v in data['settings'].values()), 'تنظیمات نامعتبر است.')
    require(data['theme'] in ('light', 'dark'), 'تم نامعتبر است.')
    logo = data['customLogo']
    # Do not mutate a legacy logo; invalid/unsupported logos block migration.
    require(logo is None or (isinstance(logo, str) and len(logo) <= 3_000_000 and
            re.fullmatch(r'data:image/(?:png|jpeg|webp|gif);base64,[A-Za-z0-9+/=]+', logo) is not None),
            'فرمت لوگو نامعتبر است؛ نسخه خام محفوظ می‌ماند.')
    return data


class LedgerSnapshot:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.path = self.folder / 'ledger.db'
        self.backups = self.folder / 'backups'
        with closing(self.connect()) as db:
            if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise LedgerError('پایگاه حسابداری خراب است؛ از پشتیبان بازیابی شود.')
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1):
                raise LedgerError('نسخه پایگاه حسابداری پشتیبانی نمی‌شود.')
            if version == 0:
                with db:
                    db.execute('CREATE TABLE IF NOT EXISTS snapshot (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, payload TEXT NOT NULL)')
                    db.execute('PRAGMA user_version=1')
            # A missing table in an existing schema must not silently reset data.
            db.execute('SELECT revision, payload FROM snapshot WHERE id=1').fetchone()

    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            db.execute('PRAGMA busy_timeout=5000')
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('PRAGMA synchronous=FULL')
            db.execute('PRAGMA foreign_keys=ON')
        except Exception:
            db.close()
            raise
        return db

    def load(self):
        with closing(self.connect()) as db:
            row = db.execute('SELECT revision, payload FROM snapshot WHERE id=1').fetchone()
        if row is None:
            return {'revision': 0, 'data': None}
        return {'revision': row[0], 'data': validate_snapshot(parse_json(row[1]))}

    def archive_legacy(self, raw):
        value = parse_json(raw)
        require(isinstance(value, dict) and set(value) <= LEGACY_KEYS and
                all(v is None or isinstance(v, str) for v in value.values()), 'ساختار داده قدیمی نامعتبر است.')
        digest = sha256(raw.encode('utf-8')).hexdigest()
        path = self.backups / ('legacy-' + digest + '.json')
        if not path.exists():
            atomic_write(path, raw.encode('utf-8'))
        return path.name

    def _backup(self, revision, payload, prefix):
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        path = self.backups / (f'snapshot-r{revision:012d}.json' if prefix == 'snapshot' else f'{prefix}-{stamp}-r{revision}-{uuid4().hex[:8]}.json')
        data = {'app': 'JavanCafeNetAccounting', 'version': 3, 'revision': revision,
                'exportedAt': stamp, 'data': parse_json(payload)}
        atomic_write(path, encode_json(data).encode('utf-8'))
        return path

    def _prune(self):
        # Legacy archives and pre-restore backups are never automatically removed.
        files = sorted(self.backups.glob('snapshot-r*.json'), reverse=True)
        for path in files[30:]:
            try:
                path.unlink()
            except OSError:
                pass

    def save(self, revision, raw, reason='save'):
        require(type(revision) is int and revision >= 0, 'نسخه ذخیره نامعتبر است.')
        require(reason in ('save', 'restore', 'migration'), 'نوع عملیات نامعتبر است.')
        data = validate_snapshot(parse_json(raw))
        payload = encode_json(data)
        with closing(self.connect()) as db:
            with db:
                db.execute('BEGIN IMMEDIATE')
                old = db.execute('SELECT revision, payload FROM snapshot WHERE id=1').fetchone()
                current = old[0] if old else 0
                require(revision == current, 'دفتر تغییر کرده است؛ ابتدا دوباره بارگذاری کنید.')
                if old:
                    self._backup(current, old[1], 'pre-restore' if reason == 'restore' else 'snapshot')
                new_revision = current + 1
                db.execute('INSERT INTO snapshot(id, revision, payload) VALUES(1, ?, ?) '
                           'ON CONFLICT(id) DO UPDATE SET revision=excluded.revision, payload=excluded.payload',
                           (new_revision, payload))
        # Transaction already committed; don't falsely report it failed if the
        # extra post-commit copy fails. The pre-commit copy and DB remain intact.
        warning = ''
        try:
            self._backup(new_revision, payload, 'snapshot')
            self._prune()
        except (OSError, ValueError):
            warning = 'ثبت در پایگاه انجام شد؛ ساخت پشتیبان اضافی ناموفق بود.'
        return {'revision': new_revision, 'warning': warning}
