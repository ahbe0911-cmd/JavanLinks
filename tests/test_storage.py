import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from dataclasses import replace
from javan.catalog import Link, SAMPLE_LINKS
from javan.storage import CatalogStore, State, encode, decode, read_state


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'catalog.json'
        self.store = CatalogStore(self.path)
        self.link = Link('new', 'سامانه تازه', 'https://example.com/', 'دسته جدید')

    def test_initial(self):
        self.assertEqual(read_state(self.path).links, SAMPLE_LINKS)

    def test_crud_and_reopen(self):
        self.store.add(self.link)
        updated = replace(self.link, title='ویرایش شد')
        self.store.edit(updated)
        self.assertEqual(CatalogStore(self.path).state.links[-1], updated)
        self.store.delete(updated.id)
        self.assertEqual(CatalogStore(self.path).state.links, SAMPLE_LINKS)

    def test_empty_is_preserved(self):
        self.store.restore(State(()))
        self.assertEqual(CatalogStore(self.path).state.links, ())

    def test_settings(self):
        self.store.set_sidebar(True)
        self.assertTrue(CatalogStore(self.path).state.sidebar_collapsed)

    def test_duplicate_does_not_modify_disk(self):
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            self.store.add(SAMPLE_LINKS[0])
        self.assertEqual(self.path.read_bytes(), before)

    def test_failed_write_does_not_modify_state(self):
        before = self.store.state
        with patch('javan.storage.os.replace', side_effect=OSError('disk')):
            with self.assertRaises(OSError):
                self.store.add(self.link)
        self.assertEqual(self.store.state, before)
        self.assertEqual(read_state(self.path), before)
        self.assertFalse(list(self.path.parent.glob('.javan-*')))

    def test_backup_and_restore(self):
        backup = self.path.parent / 'backup.json'
        self.store.export(backup)
        self.store.add(self.link)
        previous = self.store.state
        self.store.restore(read_state(backup))
        self.assertEqual(self.store.state.links, SAMPLE_LINKS)
        self.assertEqual(read_state(self.path.with_suffix('.previous.json')), previous)

    def test_invalid_backup(self):
        for raw in (b'not json', b'{}', b'{"schema_version":2,"links":[]}',
                    b'{"schema_version":1,"links":[{}]}',
                    b'{"schema_version":1,"links":[],"settings":{"sidebar_collapsed":1}}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                decode(raw)

    def test_corrupt_startup_is_not_overwritten(self):
        self.path.write_bytes(b'bad')
        with self.assertRaises(ValueError):
            CatalogStore(self.path)
        self.assertEqual(self.path.read_bytes(), b'bad')

    def test_local_roundtrip_and_missing_file(self):
        link = Link('html', 'ابزار', r'C:\Tools\فاکتور.html', 'محلی', kind='html')
        self.assertEqual(decode(encode(State((link,)))).links[0], link)

    def test_reject_relative_or_network_or_non_html(self):
        for address in ('tool.html', r'\\server\share\tool.html', r'C:\Tools\test.exe'):
            with self.subTest(address=address), self.assertRaises(ValueError):
                Link('bad', 'نام', address, 'محلی', kind='html')

    def test_export_cannot_overwrite_live_file(self):
        with self.assertRaises(ValueError):
            self.store.export(self.path)


if __name__ == '__main__':
    unittest.main()
