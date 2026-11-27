import sqlite3
import tempfile
import unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
from javan.ledger_snapshot import LedgerSnapshot, LedgerError, encode_json
from tests.test_ledger_snapshot import sample


class RelationalLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def seed_v1(self, data):
        path = self.folder / 'ledger.db'
        with closing(sqlite3.connect(path)) as db, db:
            db.execute('CREATE TABLE snapshot(id INTEGER PRIMARY KEY,revision INTEGER NOT NULL,payload TEXT NOT NULL)')
            db.execute('INSERT INTO snapshot VALUES(1,7,?)', (encode_json(data),))
            db.execute('PRAGMA user_version=1')
        return path

    def test_v1_migration_retains_exact_data_and_original_snapshot(self):
        original = sample()
        original['invoices'][0]['finalToman'] = 1999.5
        self.seed_v1(original)
        store = LedgerSnapshot(self.folder)
        self.assertEqual(store.load(), {'revision': 7, 'data': original})
        with closing(store.connect()) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 2)
            self.assertEqual(db.execute('SELECT payload FROM snapshot').fetchone()[0], encode_json(original))
            self.assertEqual(db.execute('SELECT COUNT(*) FROM invoice_items').fetchone()[0], 1)
        self.assertEqual(len(list(store.backups.glob('pre-schema2-*.json'))), 1)

    def test_migration_backup_failure_preserves_version(self):
        path = self.seed_v1(sample())
        with patch.object(LedgerSnapshot, '_backup', side_effect=OSError('full disk')):
            with self.assertRaises(OSError):
                LedgerSnapshot(self.folder)
        with closing(sqlite3.connect(path)) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT revision FROM snapshot').fetchone()[0], 7)

    def test_deleted_invoice_is_retained_and_audited(self):
        store = LedgerSnapshot(self.folder)
        store.save(0, encode_json(sample()))
        edited = sample()
        edited['invoices'] = []
        store.save(1, encode_json(edited))
        self.assertEqual(store.load()['data'], edited)
        with closing(store.connect()) as db:
            self.assertEqual(db.execute('SELECT active FROM invoices WHERE id="i1"').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM invoice_items').fetchone()[0], 1)
            row = db.execute("SELECT action,before_json,after_json FROM audit_log WHERE entity='invoices' ORDER BY id DESC LIMIT 1").fetchone()
            self.assertEqual(row[0], 'save:void')
            self.assertIsNotNone(row[1])
            self.assertIsNone(row[2])
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute('DELETE FROM audit_log')

    def test_no_duplicate_audit_for_unchanged_records(self):
        store = LedgerSnapshot(self.folder)
        store.save(0, encode_json(sample()))
        with closing(store.connect()) as db:
            count = db.execute('SELECT COUNT(*) FROM audit_log').fetchone()[0]
        store.save(1, encode_json(sample()))
        with closing(store.connect()) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM audit_log').fetchone()[0], count)

    def test_reordering_and_restore_keeps_exact_items(self):
        store = LedgerSnapshot(self.folder)
        data = sample()
        second = dict(data['invoices'][0], id='i2', invoiceNumber='1002')
        data['invoices'].append(second)
        store.save(0, encode_json(data))
        data['invoices'].reverse()
        store.save(1, encode_json(data))
        self.assertEqual(store.load()['data'], data)
        removed = sample()
        removed['invoices'] = []
        store.save(2, encode_json(removed))
        store.save(3, encode_json(data), 'restore')
        self.assertEqual(store.load()['data'], data)

    def test_invoice_number_swap_is_atomic(self):
        store = LedgerSnapshot(self.folder)
        data = sample()
        data['invoices'].append(dict(data['invoices'][0], id='i2', invoiceNumber='1002'))
        store.save(0, encode_json(data))
        data['invoices'][0]['invoiceNumber'] = '1002'
        data['invoices'][1]['invoiceNumber'] = '1001'
        store.save(1, encode_json(data), 'restore')
        self.assertEqual(store.load()['data'], data)

    def test_failure_mid_sync_rolls_back_all_records(self):
        store = LedgerSnapshot(self.folder)
        store.save(0, encode_json(sample()))
        data = sample()
        data['services'][0]['price'] = 9000
        from javan import ledger_snapshot as module
        original = module.sync_relational
        def fail(db, *args):
            original(db, *args)
            raise sqlite3.OperationalError('simulated failure')
        with patch.object(module, 'sync_relational', side_effect=fail):
            with self.assertRaises(sqlite3.OperationalError):
                store.save(1, encode_json(data))
        self.assertEqual(store.load(), {'revision': 1, 'data': sample()})
