"""Phase 1: immutable sample catalog, independent of Qt."""
from dataclasses import dataclass
import unicodedata
from urllib.parse import urlsplit


@dataclass(frozen=True, slots=True)
class Link:
    id: str
    title: str
    url: str
    category: str
    description: str = ''

    def __post_init__(self):
        parsed = urlsplit(self.url)
        if not self.id.strip() or not self.title.strip() or not self.category.strip():
            raise ValueError('Link id, title and category are required')
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('Expected an HTTP(S) URL without credentials')


SAMPLE_LINKS = (
    Link('gov', 'پنجره ملی خدمات دولت هوشمند', 'https://my.gov.ir/', 'خدمات دولتی', 'ورود به خدمات دولت'),
    Link('tax', 'سازمان امور مالیاتی', 'https://tax.gov.ir/', 'خدمات دولتی', 'درگاه سازمان مالیاتی'),
    Link('cbi', 'بانک مرکزی جمهوری اسلامی ایران', 'https://www.cbi.ir/', 'بانکی و چک', 'اطلاعات و خدمات بانکی'),
    Link('sanjesh', 'سازمان سنجش آموزش کشور', 'https://www.sanjesh.org/', 'آموزشی و دانشگاهی', 'آزمون و ثبت‌نام کنکور'),
    Link('post', 'شرکت ملی پست', 'https://www.post.ir/', 'خدمات پستی', 'درگاه خدمات پستی'),
    Link('tracking', 'رهگیری مرسولات پستی', 'https://tracking.post.ir/', 'خدمات پستی', 'پیگیری بسته و مرسوله'),
)

_TRANSLATION = str.maketrans({'ي': 'ی', 'ى': 'ی', 'ك': 'ک', 'ۀ': 'ه', 'ة': 'ه', '\u200c': ' ', '\u200d': ' ', '\u0640': '', **{a: str(i) for i, a in enumerate('۰۱۲۳۴۵۶۷۸۹')}, **{a: str(i) for i, a in enumerate('٠١٢٣٤٥٦٧٨٩')}})


def normalize(text: str) -> str:
    text = unicodedata.normalize('NFKC', text).translate(_TRANSLATION).casefold()
    return ' '.join(''.join(ch for ch in text if unicodedata.category(ch) not in ('Mn', 'Me', 'Cf')).split())


def filter_links(links: tuple[Link, ...], query: str) -> tuple[Link, ...]:
    terms = normalize(query).split()
    if not terms:
        return tuple(links)
    matches = []
    for link in links:
        field = normalize(' '.join((link.title, link.category, link.url, link.description)))
        compact = field.replace(' ', '')
        if all(term in field or term in compact for term in terms):
            matches.append(link)
    return tuple(matches)


def group_links(links: tuple[Link, ...]) -> dict[str, list[Link]]:
    groups: dict[str, list[Link]] = {}
    for link in links:
        groups.setdefault(link.category, []).append(link)
    return groups
