"""Audit the curated library; optional public-source checks, never a generation step.

Run from backend: python scripts/validate_architecture_knowledge.py --online
"""
import argparse
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlparse, urljoin
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.diagram.knowledge import load_library, select_patterns, reference_context, reference_image_path


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
        self.images = []

    def handle_data(self, value):
        self.text.append(value)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'img' and attrs.get('src') and 'warning' not in attrs.get('src', '').lower():
            self.images.append(attrs['src'])


def read(url):
    with urlopen(Request(url, headers={'User-Agent': 'SOWArchitectureReferenceAudit/1.0'}), timeout=25) as response:
        if urlparse(response.url).netloc != 'docs.aws.amazon.com':
            raise ValueError('Unexpected source redirect')
        content = response.read(3_000_001)
        if len(content) > 3_000_000:
            raise ValueError('Source too large')
        return response.url, content


def audit(online=False):
    data = load_library()
    result = {'library_version': data['library_version'],
              'checked_at': datetime.now(timezone.utc).isoformat(),
              'review_scope': 'Source text and retrieval, not visual or solution-certification review',
              'patterns': [], 'errors': []}
    robots = None
    if online:
        _, raw = read('https://docs.aws.amazon.com/robots.txt')
        robots = RobotFileParser()
        robots.parse(raw.decode('utf-8').splitlines())
    for card in data['patterns']:
        row = {'id': card['id'], 'source_url': card['source_url']}
        selected = select_patterns({'features': [card['triggers'][0]]})
        row['retrieval_ok'] = card['id'] in [x['id'] for x in selected]
        if not row['retrieval_ok']:
            result['errors'].append(card['id'] + ': retrieval failed')
        if card.get('source_type') == 'user_reference':
            path = reference_image_path(card)
            row.update(source_ok=True, source_type='user_reference', sha256=card['image_sha256'], image_path=str(path))
        elif online:
            try:
                if not robots.can_fetch('SOWArchitectureReferenceAudit', card['source_url']):
                    raise ValueError('Source disallowed by robots.txt')
                final_url, raw = read(card['source_url'])
                page = Page()
                page.feed(raw.decode('utf-8'))
                body = ' '.join(page.text).casefold()
                missing = [a for a in card['anchors'] if a.casefold() not in body]
                if missing:
                    raise ValueError('Missing evidence anchors: ' + ', '.join(missing))
                row.update(source_ok=True, final_url=final_url,
                           sha256=hashlib.sha256(raw).hexdigest(),
                           diagram_urls=[urljoin(final_url, x) for x in page.images])
            except Exception as exc:
                row.update(source_ok=False, error=str(exc))
                result['errors'].append(card['id'] + ': ' + str(exc))
            time.sleep(0.2)
        result['patterns'].append(row)
    start = time.perf_counter()
    for _ in range(100):
        context = reference_context({'features': ['Knowledge base', 'Fargate', 'AgentCore']})
        assert len(context) <= 5000
    result['retrieval_mean_ms'] = (time.perf_counter() - start) * 10
    result['pattern_count'] = len(result['patterns'])
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--online', action='store_true')
    parser.add_argument('--output', default='output/architecture-knowledge-validation.json')
    args = parser.parse_args()
    report = audit(args.online)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'patterns': report['pattern_count'], 'errors': report['errors'],
                      'retrieval_mean_ms': report['retrieval_mean_ms'], 'report': str(path)}, indent=2))
    sys.exit(bool(report['errors']))
