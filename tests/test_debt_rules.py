import tempfile
import unittest
from pathlib import Path
from javan.ledger_snapshot import LedgerSnapshot, LedgerError, encode_json
from javan.debt_rules import remaining, sensitive_change
from javan.admin_pin import PinStore
from tests.test_ledger_snapshot import sample


class DebtRulesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.store = LedgerSnapshot(self.folder)

    def credit(self):
        d = sample()
        d['invoices'][0]['paymentStatus'] = 'نسیه'
        return d

    def test_old_credit_is_not_guessed(self):
        self.store.save(0, encode_json(self.credit()), 'migration')
        d = self.store.load()['data']
        self.assertEqual(len(d['debts']), 1)
        self.store.save(1, encode_json(d))
        self.assertEqual(len(self.store.load()['data']['debts']), 1)

    def test_credit_creates_exactly_one_link(self):
        data = self.credit()
        self.store.save(0, encode_json(data))
        d = self.store.load()['data']
        linked = [x for x in d['debts'] if x.get('invoiceId') == 'i1']
        self.assertEqual(len(linked), 1)
        self.assertEqual(remaining(linked[0]), 2000)
        self.store.save(1, encode_json(d))
        self.assertEqual(len(self.store.load()['data']['debts']), 2)

    def test_partial_and_overpayment(self):
        self.store.save(0, encode_json(self.credit()))
        d = self.store.load()['data']
        linked = d['debts'][0]
        linked['payments'].append({'id':'p1','amount':500,'date':'1405/09/06'})
        self.store.save(1, encode_json(d))
        self.assertEqual(remaining(self.store.load()['data']['debts'][0]), 1500)
        linked['payments'].append({'id':'p2','amount':1600,'date':'1405/09/06'})
        with self.assertRaises(LedgerError):
            self.store.save(2, encode_json(d))
        self.assertEqual(self.store.load()['revision'], 2)

    def test_paid_invoice_cannot_be_deleted(self):
        self.store.save(0, encode_json(self.credit()))
        d = self.store.load()['data']
        d['debts'][0]['payments'] = [{'id':'p1','amount':100,'date':'1405/09/06'}]
        self.store.save(1, encode_json(d))
        d['invoices'] = []
        with self.assertRaises(LedgerError):
            self.store.save(2, encode_json(d))

    def test_sensitive_cancel_preserves_revision(self):
        self.store.save(0, encode_json(sample()))
        d = sample()
        d['invoices'] = []
        with self.assertRaises(LedgerError):
            self.store.save(1, encode_json(d), authorize=lambda old,new,reason: not sensitive_change(old,new,reason))
        self.assertEqual(self.store.load()['revision'], 1)

    def test_pin_hash_and_validation(self):
        pins = PinStore(self.folder)
        pins.configure('123456')
        self.assertTrue(pins.verify('123456'))
        self.assertFalse(pins.verify('123457'))
        self.assertFalse(pins.verify('abc'))
        self.assertNotIn('123456', pins.path.read_text())
        with self.assertRaises(ValueError):
            pins.configure('777777')
