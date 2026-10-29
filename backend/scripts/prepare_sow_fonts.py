"""One-time maintainer utility: bundle OFL fonts as static Word-compatible faces."""
from io import BytesIO
from pathlib import Path
from urllib.request import urlopen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

target = Path(__file__).resolve().parents[1] / 'assets/fonts'
for family in ('AlbertSans', 'SpaceGrotesk'):
    base = 'https://raw.githubusercontent.com/google/fonts/main/ofl/' + family.lower() + '/'
    raw = urlopen(base + family + '%5Bwght%5D.ttf', timeout=30).read()
    (target / (family + '-OFL.txt')).write_bytes(urlopen(base + 'OFL.txt', timeout=30).read())
    for face, weight in [('Regular', 400), ('Bold', 700)]:
        font = instantiateVariableFont(TTFont(BytesIO(raw)), {'wght': weight}, inplace=False)
        name = 'Albert Sans' if family == 'AlbertSans' else 'Space Grotesk'
        for platform, encoding, language in [(3, 1, 1033), (1, 0, 0)]:
            for name_id, value in [(1, name), (2, face), (4, name + ' ' + face),
                                   (6, family + '-' + face), (16, name), (17, face)]:
                font['name'].setName(value, name_id, platform, encoding, language)
        font.save(target / (family + '-' + face + '.ttf'))
        print(f'Prepared {family}-{face}.ttf')
