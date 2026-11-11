"""Build the local source index from validated AWS reference cards."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.diagram.knowledge import load_library, LIBRARY


def main():
    data = load_library()
    cards = sorted((c for c in data['patterns'] if c.get('source_type') != 'user_reference'),
                   key=lambda c: (c.get('category', 'specialist'), c['title']))
    lines = ['# AWS source catalogue', '',
             f'{len(cards)} official AWS reference cards. Version: `{data["library_version"]}`.', '',
             'Full guidance: `patterns.json` and `aws-patterns.json`. Dates are review dates, '
             'not publication dates. Historical entries teach topology only. '
             'See [the pipeline and maintenance guide](README.md).', '',
             '| ID | Reference | Area | Reviewed | Historical |',
             '|---|---|---|---|---|']
    for card in cards:
        lines.append(f'| `{card["id"]}` | [{card["title"]}]({card["source_url"]}) '
                     f'| {card.get("category", "specialist")} | {card["reviewed_on"]} '
                     f'| {"Yes" if card.get("historical") else "No"} |')
    path = LIBRARY.with_name('AWS_CATALOG.md')
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'Indexed {len(cards)} AWS sources: {path}')


if __name__ == '__main__':
    main()
