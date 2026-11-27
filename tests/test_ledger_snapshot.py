import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from javan.ledger_snapshot import LedgerSnapshot, LedgerError, encode_json


def sample():
    return {'services': [{'id': 's1', 'name': 'خدمت', 'price': 1000}],
            'invoices': [{'id': 'i1', 'invoiceNumber': '1001',
                          'items': [{'name': 'خدمت', 'price': 1000, 'qty': 2}],
                          'subtotal': 2000, 'discountAmount': 0, 'finalToman': 2000, 'finalRial': 20000}],
            'debts': [{'id': 'd1', 'name': 'الف', 'amount': 50, 'paid': False}],
            'nextInvoiceNumber': 1002, 'customLogo': None,
            'settings': {'phone': ''}, 'theme': 'light'}


class LedgerSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.ledger = LedgerSnapshot(self.folder)

    def test_empty(self):
        self.assertEqual(self.ledger.load(), {'revision': 0, 'data': None})

    def test_reopen(self):
        first = self.ledger.save(0, encode_json(sample()), 'migration')
        self.assertEqual(first['revision'], 1)
        self.assertEqual(LedgerSnapshot(self.folder).load()['data'], sample())

    def test_legacy_archive_idempotent(self):
        raw = '{"javan_acc_invoices_v2":"broken JSON"}'
        name = self.ledger.archive_legacy(raw)
        self.assertEqual(self.ledger.archive_legacy(raw), name)
        self.assertEqual((self.folder / 'backups' / name).read_text(), raw)

    def test_duplicate_and_invalid_preserve(self):
        self.ledger.save(0, encode_json(sample()))
        old = self.ledger.load()
        data = sample()
        data['invoices'].append(data['invoices'][0])
        with self.assertRaises(LedgerError):
            self.ledger.save(1, encode_json(data))
        self.assertEqual(self.ledger.load(), old)

    def test_stale_revision(self):
        self.ledger.save(0, encode_json(sample()))
        with self.assertRaises(LedgerError):
            self.ledger.save(0, encode_json(sample()))
        self.assertEqual(self.ledger.load()['revision'], 1)

    def test_prebackup_failure_does_not_commit(self):
        self.ledger.save(0, encode_json(sample()))
        with patch.object(self.ledger, '_backup', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.ledger.save(1, encode_json(sample()))
        self.assertEqual(self.ledger.load()['revision'], 1)

    def test_postbackup_failure_is_acknowledged(self):
        with patch.object(self.ledger, '_backup', side_effect=OSError('disk full')):
            result = self.ledger.save(0, encode_json(sample()))
        self.assertEqual(result['revision'], 1)
        self.assertTrue(result['warning'])
        self.assertEqual(self.ledger.load()['revision'], 1)

    def test_restore_backup_preserves_old(self):
        self.ledger.save(0, encode_json(sample()))
        data = sample()
        data['invoices'] = []
        self.ledger.save(1, encode_json(data), 'restore')
        path = next((self.folder / 'backups').glob('pre-restore-*.json'))
        self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['data'], sample())

    def test_corrupt_db_not_replaced(self):
        path = self.ledger.path
        path.write_bytes(b'not a database')
        before = path.read_bytes()
        with self.assertRaises(sqlite3.DatabaseError):
            LedgerSnapshot(self.folder)
        self.assertEqual(path.read_bytes(), before)

    def test_historical_amounts_unchanged(self):
        data = sample()
        data['invoices'][0]['finalToman'] = 1000.5
        self.ledger.save(0, encode_json(data))
        self.assertEqual(self.ledger.load()['data']['invoices'][0]['finalToman'], 1000.5)


    def test_backup_retention_unique_revisions(self):
        for revision in range(34):
            self.ledger.save(revision, encode_json(sample()))
        files = sorted((self.folder / 'backups').glob('snapshot-r*.json'))
        self.assertEqual(len(files), 30)
        self.assertTrue(files[-1].name.endswith('000000000034.json'))

    def test_process_exit_after_commit(self):
        import subprocess
        import sys
        code = ("import os,sys; from javan.ledger_snapshot import LedgerSnapshot;"
                "LedgerSnapshot(sys.argv[1]).save(0, sys.argv[2]);os._exit(0)")
        completed = subprocess.run([sys.executable, '-c', code, str(self.folder), encode_json(sample())], check=False)
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(self.ledger.load()['data'], sample())
