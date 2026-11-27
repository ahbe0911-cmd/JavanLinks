"""Generate a multi-resolution Windows icon and obtain licensed Vazirmatn assets."""
from pathlib import Path
from urllib.request import urlopen, Request
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'assets'
FONTS = ASSETS / 'fonts'
SCALE = 4


def make_icon():
    im = Image.new('RGBA', (256*SCALE, 256*SCALE))
    d = ImageDraw.Draw(im)
    def rect(box, radius, fill, outline=None, width=1):
        d.rounded_rectangle(tuple(x*SCALE for x in box), radius*SCALE, fill=fill,
                            outline=outline, width=width*SCALE)
    rect((7, 7, 249, 249), 55, '#14263C')
    rect((20, 20, 236, 236), 43, '#203B52')
    rect((42, 54, 214, 192), 22, '#F4FAFB')
    rect((42, 54, 214, 90), 15, '#A5DAD4')
    for x in (61, 76, 91):
        d.ellipse((x*SCALE, 67*SCALE, (x+7)*SCALE, 74*SCALE), fill='#176C70')
    rect((64, 108, 133, 145), 18, None, '#176C70', 10)
    rect((123, 135, 192, 172), 18, None, '#176C70', 10)
    d.line((104*SCALE, 136*SCALE, 152*SCALE, 146*SCALE), fill='#176C70', width=10*SCALE)
    d.ellipse((173*SCALE, 174*SCALE, 217*SCALE, 218*SCALE), fill='#E8B750', outline='#14263C', width=5*SCALE)
    d.line((184*SCALE, 196*SCALE, 192*SCALE, 204*SCALE, 207*SCALE, 188*SCALE),
           fill='#14263C', width=5*SCALE, joint='curve')
    im = im.resize((256, 256), Image.Resampling.LANCZOS)
    ASSETS.mkdir(exist_ok=True)
    im.save(ASSETS / 'javan.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
    im.save(ASSETS / 'javan.png')


def fetch(name, url):
    dest = FONTS / name
    if dest.is_file() and dest.stat().st_size > 0:
        return
    with urlopen(Request(url, headers={'User-Agent':'JavanLinks-build'}), timeout=60) as response:
        data = response.read(10_000_001)
    if not data or len(data) > 10_000_000:
        raise RuntimeError('Invalid font asset download')
    if name.endswith('.ttf') and data[:4] not in (b'\x00\x01\x00\x00', b'OTTO'):
        raise RuntimeError('Invalid font format')
    if name == 'OFL.txt' and b'SIL OPEN FONT LICENSE' not in data:
        raise RuntimeError('Font license not found')
    dest.write_bytes(data)


def main():
    make_icon()
    FONTS.mkdir(parents=True, exist_ok=True)
    base = 'https://raw.githubusercontent.com/google/fonts/main/ofl/vazirmatn/'
    fetch('Vazirmatn.ttf', base + 'Vazirmatn%5Bwght%5D.ttf')
    fetch('OFL.txt', base + 'OFL.txt')


if __name__ == '__main__':
    main()
