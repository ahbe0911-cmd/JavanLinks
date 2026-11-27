import unittest
from javan.browser_utils import next_zoom, safe_filename, web_address, origin_label


class BrowserUtilsTests(unittest.TestCase):
    def test_zoom(self):
        self.assertEqual(next_zoom(100, 1), 110)
        self.assertEqual(next_zoom(195, 1), 200)
        self.assertEqual(next_zoom(50, -1), 50)

    def test_filename(self):
        self.assertEqual(safe_filename(r'..\..\form.pdf'), 'form.pdf')
        self.assertEqual(safe_filename('CON.txt'), '_CON.txt')
        self.assertEqual(safe_filename(''), 'download')
        self.assertEqual(safe_filename('a:b?.pdf'), 'a_b_.pdf')

    def test_address(self):
        self.assertEqual(web_address('example.com'), 'https://example.com')
        self.assertEqual(web_address('http://example.com:8080/a'), 'http://example.com:8080/a')
        for url in ('javascript:alert(1)', 'file:///a.html', 'https://u:p@example.com', 'https://', 'a b'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                web_address(url)

    def test_origin(self):
        self.assertEqual(origin_label('https://example.com/path?token=secret'), 'https://example.com')


class RiskyDownloadTests(unittest.TestCase):
    def test_executable_extensions(self):
        from javan.browser_utils import risky_download
        for name in ('report.pdf.exe', 'file.JS', 'shortcut.lnk', 'installer.msi', 'file.cmd. '):
            self.assertTrue(risky_download(name), name)

    def test_ordinary_documents(self):
        from javan.browser_utils import risky_download
        for name in ('report.pdf', 'photo.jpg', 'backup.json', 'list.csv', 'archive.zip'):
            self.assertFalse(risky_download(name), name)


class LinkReuseTests(unittest.TestCase):
    def test_unrelated_edit_does_not_reload_existing_page(self):
        from javan.catalog import Link
        from javan.browser_utils import unchanged_link_ids
        a = Link('a','A','https://a.example/','cat')
        b = Link('b','B','https://b.example/','cat')
        renamed = Link('a','New title','https://a.example/','new cat')
        changed = Link('b','B','https://new.example/','cat')
        self.assertEqual(unchanged_link_ids([a,b],[renamed,changed]), {'a'})
