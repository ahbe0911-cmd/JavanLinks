"""Stable offline accounting content and optional local typefaces.

Financial data lives in the dedicated persistent WebEngine profile, not
the EXE or the installed HTML. Never replace that profile on update.
"""
from pathlib import Path
from zipfile import ZipFile, BadZipFile
from .storage import atomic_write

ASSETS = Path(__file__).resolve().parent.parent / 'assets'
FONT_NAMES = {
    'a rooznameh.ttf': 'Rooznameh.ttf',
    'far_nazanin.ttf': 'Nazanin.ttf',
    'vazirmatn_regular.ttf': 'Vazirmatn-Regular.ttf',
    'vazirmatn_medium.ttf': 'Vazirmatn-Medium.ttf',
    'vazirmatn_semibold.ttf': 'Vazirmatn-SemiBold.ttf',
    'vazirmatn_bold.ttf': 'Vazirmatn-Bold.ttf',
}
MAX_FONT_BYTES = 2 * 1024 * 1024


def write_if_changed(path, data):
    if not path.is_file() or path.read_bytes() != data:
        atomic_write(path, data)


def make_font_css(folder):
    rules = []
    def face(filename, family, weight):
        if (folder / filename).is_file():
            rules.append(f"@font-face {{ font-family: '{family}'; src: url('{filename}') format('truetype'); font-weight: {weight}; font-display: swap; }}")
            return True
        return False
    face('Vazirmatn.ttf', 'JavanVazir', '100 900')
    for name, weight in [('Regular', 400), ('Medium', 500), ('SemiBold', 600), ('Bold', 700)]:
        face(f'Vazirmatn-{name}.ttf', 'JavanVazirLocal', weight)
    face('Rooznameh.ttf', 'JavanHeadline', '400')
    face('Nazanin.ttf', 'JavanNazanin', '400')
    rules.append("""
:root { --font-main: 'JavanVazirLocal', 'JavanVazir', 'Vazirmatn', Tahoma, sans-serif; }
.brand-text h1, .print-shop-name { font-family: 'JavanHeadline', var(--font-main); font-weight: 700; }
@media print {
  .print-doc:not(.print-80mm) .print-shop-info,
  .print-doc:not(.print-80mm) .print-words-box,
  .print-doc:not(.print-80mm) .print-signatures,
  .print-doc:not(.print-80mm) .print-footer-note {
    font-family: 'JavanNazanin', var(--font-main);
    font-size: 11pt;
  }
}
""")
    return '\n'.join(rules).encode('utf-8')


def prepare_accounting(data_folder, assets=ASSETS):
    # This file URL and directory name MUST remain constant across releases.
    root = Path(data_folder).resolve() / 'accounting'
    font_dir = root / 'fonts'
    font_dir.mkdir(parents=True, exist_ok=True)
    source = Path(assets) / 'accounting' / 'index.html'
    if not source.is_file():
        raise FileNotFoundError('فایل داخلی حسابداری در بسته برنامه یافت نشد.')
    write_if_changed(root / 'index.html', source.read_bytes())
    default_font = Path(assets) / 'fonts' / 'Vazirmatn.ttf'
    if default_font.is_file():
        write_if_changed(font_dir / 'Vazirmatn.ttf', default_font.read_bytes())
    license_file = Path(assets) / 'fonts' / 'OFL.txt'
    if license_file.is_file():
        write_if_changed(font_dir / 'OFL.txt', license_file.read_bytes())
    write_if_changed(font_dir / 'accounting.css', make_font_css(font_dir))
    return root / 'index.html'


def validate_font(data):
    if not 12 <= len(data) <= MAX_FONT_BYTES or data[:4] not in (b'\x00\x01\x00\x00', b'OTTO', b'true'):
        raise ValueError('فایل فونت معتبر نیست.')
    return data


def collect_fonts(paths):
    """Read only explicitly supported font basenames, not other ZIP contents."""
    result = {}
    for name in paths:
        path = Path(name)
        if path.suffix.lower() == '.zip':
            with ZipFile(path) as archive:
                for info in archive.infolist():
                    target = FONT_NAMES.get(info.filename.replace('\\', '/').rsplit('/', 1)[-1].casefold())
                    if not target or info.is_dir():
                        continue
                    if info.file_size > MAX_FONT_BYTES:
                        raise ValueError('حجم فونت بیش از حد مجاز است.')
                    with archive.open(info) as stream:
                        result[target] = validate_font(stream.read(MAX_FONT_BYTES + 1))
        else:
            target = FONT_NAMES.get(path.name.casefold())
            if target:
                with path.open('rb') as stream:
                    result[target] = validate_font(stream.read(MAX_FONT_BYTES + 1))
    return result


def import_fonts(data_folder, paths, assets=ASSETS):
    selected = collect_fonts(paths)
    if not selected:
        raise ValueError('هیچ‌یک از فونت‌های روزنامه، نازنین یا وزیرمتن مورد انتظار یافت نشد.')
    root = prepare_accounting(data_folder, assets).parent
    folder = root / 'fonts'
    for name, data in selected.items():
        write_if_changed(folder / name, data)
    write_if_changed(folder / 'accounting.css', make_font_css(folder))
    return tuple(sorted(selected))
