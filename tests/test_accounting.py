import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
from javan.accounting import prepare_accounting, import_fonts, collect_fonts


class AccountingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.assets = self.base / 'assets'
        (self.assets / 'accounting').mkdir(parents=True)
        (self.assets / 'accounting' / 'index.html').write_text('<html>accounting</html>', encoding='utf-8')
        self.folder = self.base / 'data'

    def test_stable_path_and_update(self):
        p = prepare_accounting(self.folder, self.assets)
        marker = p.parent / 'persistent-data'
        marker.write_text('keep')
        (self.assets / 'accounting' / 'index.html').write_text('<html>new</html>')
        self.assertEqual(prepare_accounting(self.folder, self.assets), p)
        self.assertEqual(marker.read_text(), 'keep')
        self.assertIn('new', p.read_text())
        self.assertTrue((p.parent / 'fonts' / 'accounting.css').is_file())

    def test_only_known_font_members(self):
        z = self.base / 'fonts.zip'
        raw = b'\x00\x01\x00\x00' + b'0' * 32
        with ZipFile(z, 'w') as archive:
            archive.writestr('some/path/A Rooznameh.ttf', raw)
            archive.writestr('some/path/Far_Nazanin.ttf', raw)
            archive.writestr('../../unrelated.py', 'not a font')
        names = import_fonts(self.folder, [z], self.assets)
        self.assertEqual(set(names), {'Nazanin.ttf', 'Rooznameh.ttf'})
        root = self.folder / 'accounting' / 'fonts'
        self.assertEqual((root / 'Nazanin.ttf').read_bytes(), raw)
        css = (root / 'accounting.css').read_text()
        self.assertIn("url('Nazanin.ttf')", css)
        self.assertNotIn('unrelated.py', css)

    def test_invalid_font(self):
        p = self.base / 'A Rooznameh.ttf'
        p.write_bytes(b'invalid')
        with self.assertRaises(ValueError):
            collect_fonts([p])

    def test_missing_bundled_asset(self):
        with self.assertRaises(FileNotFoundError):
            prepare_accounting(self.folder, self.base / 'missing')
