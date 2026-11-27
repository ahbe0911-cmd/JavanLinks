"""Pure browser helpers; usable without Qt."""
from pathlib import Path
from urllib.parse import urlsplit

MIN_ZOOM, MAX_ZOOM, ZOOM_STEP = 50, 200, 10


def next_zoom(current: int, delta: int) -> int:
    return max(MIN_ZOOM, min(MAX_ZOOM, current + delta * ZOOM_STEP))


def safe_filename(name: str) -> str:
    # Strip either separator, Windows control/reserved characters and devices.
    name = name.replace('\\', '/').split('/')[-1]
    name = ''.join('_' if ord(c) < 32 or c in '<>:"/\\|?*' else c for c in name).strip(' .')
    stem = name.split('.')[0].upper()
    if stem in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
        name = '_' + name
    if len(name) > 180:
        suffix = Path(name).suffix[:20]
        name = name[:180-len(suffix)] + suffix
    return name or 'download'


def web_address(value: str) -> str:
    value = value.strip()
    if not value or any(c.isspace() or ord(c) < 32 for c in value) or '\\' in value:
        raise ValueError('آدرس اینترنتی معتبر نیست.')
    if '://' not in value:
        if ':' in value.split('/')[0]:
            raise ValueError('آدرس باید HTTP یا HTTPS باشد.')
        value = 'https://' + value
    parsed = urlsplit(value)
    if parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('فقط آدرس HTTP یا HTTPS بدون اطلاعات ورود مجاز است.')
    _ = parsed.port
    return value


def origin_label(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme in ('http', 'https'):
        return parsed.scheme + '://' + parsed.netloc.rsplit('@', 1)[-1]
    return 'صفحه داخلی'
