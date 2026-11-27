import unittest
from javan.catalog import Link, SAMPLE_LINKS, filter_links, group_links, normalize


class CatalogTests(unittest.TestCase):
    def test_empty_returns_everything(self):
        self.assertEqual(filter_links(SAMPLE_LINKS, '  '), SAMPLE_LINKS)

    def test_arabic_persian_equivalence(self):
        self.assertEqual(normalize('بانكي'), normalize('بانکی'))
        self.assertEqual([x.id for x in filter_links(SAMPLE_LINKS, 'بانكي')], ['cbi'])

    def test_category(self):
        self.assertEqual([x.id for x in filter_links(SAMPLE_LINKS, 'خدمات پستی')], ['post', 'tracking'])

    def test_domain(self):
        self.assertEqual([x.id for x in filter_links(SAMPLE_LINKS, 'TRACKING.POST.IR')], ['tracking'])

    def test_multiple_terms(self):
        self.assertEqual([x.id for x in filter_links(SAMPLE_LINKS, 'رهگیری پستی')], ['tracking'])

    def test_zwnj_and_numbers(self):
        self.assertEqual(normalize('ثبت‌نام ۱۴۰۵'), 'ثبت نام 1405')
        self.assertEqual([x.id for x in filter_links(SAMPLE_LINKS, 'ثبتنام')], ['sanjesh'])

    def test_no_match(self):
        self.assertEqual(filter_links(SAMPLE_LINKS, 'notfound123'), ())

    def test_group_order_and_count(self):
        groups = group_links(SAMPLE_LINKS)
        self.assertEqual(list(groups), ['خدمات دولتی', 'بانکی و چک', 'آموزشی و دانشگاهی', 'خدمات پستی'])
        self.assertEqual(sum(map(len, groups.values())), len(SAMPLE_LINKS))

    def test_unique_ids(self):
        self.assertEqual(len(set(x.id for x in SAMPLE_LINKS)), len(SAMPLE_LINKS))

    def test_invalid_url(self):
        for url in ('javascript:alert(1)', 'https://', 'file:///test.html', 'https://user:pass@example.com'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                Link('id', 'عنوان', url, 'دسته')

    def test_missing_fields(self):
        with self.assertRaises(ValueError):
            Link('', 'عنوان', 'https://example.com', 'دسته')


if __name__ == '__main__':
    unittest.main()
