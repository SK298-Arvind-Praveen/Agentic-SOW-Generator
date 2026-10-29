"""Small, local reference library. Advisory context, never project requirements."""
from functools import lru_cache
import json
import hashlib
import logging
from pathlib import Path
import re
from urllib.parse import urlparse

LIBRARY = Path(__file__).resolve().parents[2] / 'knowledge/architecture/patterns.json'
USER_LIBRARY = LIBRARY.with_name('user-patterns.json')
LOG = logging.getLogger(__name__)
POLICY = '''AWS REFERENCE PATTERNS — ADVISORY, NOT SOURCE REQUIREMENTS
Apply only the structure that fits the agreed project. The BRD, exclusions and
selected solution take precedence. References do not establish client facts or
authorize unrelated integrations, deliverables or replacement of existing systems.
The architect may propose supporting networking, availability and security for
the selected workload even when unnamed in the BRD; record those as design choices,
not confirmed requirements. Do not copy a reference's capacity, SLA or customer estate.
Use component roles; map them only to supported project technologies. Do not copy
an entire reference diagram. Historical sources are topology examples, not current
service recommendations. Keep these references and their provenance out of the SOW.
Separate request, ingestion and control paths. Do not invent connections to make
nodes look connected. The layout engine, not the reference, owns coordinates.
'''


def validate_library(data):
    if data.get('schema_version') != 1 or not data.get('library_version'):
        raise ValueError('Unsupported architecture library version')
    seen = set()
    for card in data.get('patterns', []):
        if not card.get('id') or card['id'] in seen:
            raise ValueError('Missing or duplicate pattern id')
        seen.add(card['id'])
        for key in ('title', 'source_url', 'reviewed_on', 'review_type', 'triggers',
                    'use_when', 'avoid', 'flow', 'layout', 'anchors'):
            if not card.get(key):
                raise ValueError(f'{card["id"]}: missing {key}')
        url = urlparse(card['source_url'])
        if card.get('source_type') == 'user_reference':
            if card['source_url'] != 'local:' + card.get('image_path', ''):
                raise ValueError('User reference must identify its curated local image')
            if card.get('source_archive'):
                if card.get('category') not in CATEGORY_TRIGGERS:
                    raise ValueError('Invalid reference category')
                if card.get('view') not in {'logical', 'deployment', 'mixed'}:
                    raise ValueError('Invalid reference view')
                if not isinstance(card.get('visual_enabled'), bool):
                    raise ValueError('Explicit visual review decision required')
                if not card.get('source_file') or card.get('review_type') != 'visual_user_reference':
                    raise ValueError('Missing reviewed image provenance')
                if any(c not in CATEGORY_TRIGGERS for c in card.get('secondary_categories', [])):
                    raise ValueError('Invalid secondary category')
            reference_image_path(card)
        elif url.scheme != 'https' or url.netloc != 'docs.aws.amazon.com':
            raise ValueError('Only official AWS documentation is allowed')
        if not isinstance(card['triggers'], list) or not all(isinstance(x, str) and x.strip() for x in card['triggers']):
            raise ValueError('Invalid retrieval triggers')
    if not seen:
        raise ValueError('Empty architecture library')
    return data


def reference_image_path(card):
    """Only curated, integrity-checked images inside the reference directory."""
    root = (LIBRARY.parent / 'references').resolve()
    path = (LIBRARY.parent / card['image_path']).resolve()
    if not path.is_relative_to(root) or path.suffix.lower() not in {'.png', '.jpg', '.jpeg'}:
        raise ValueError('Invalid reference image path')
    if hashlib.sha256(path.read_bytes()).hexdigest() != card.get('image_sha256'):
        raise ValueError('Reference image changed; review it before use')
    return path


def reference_image(requirements):
    """At most one matching visual, never a customer image for unrelated workloads."""
    for card in select_patterns(requirements):
        if card.get('source_type') == 'user_reference' and card.get('visual_enabled', True):
            image = reference_image_path(card).read_bytes()
            if len(image) > 3_500_000 or not image.startswith(b'\x89PNG'):
                LOG.warning('[ARCHITECTURE][KNOWLEDGE] text-only reference=%s; image outside request budget/format', card['id'])
                continue
            LOG.info('[ARCHITECTURE][KNOWLEDGE] visual_reference=%s', card['id'])
            return image
    return None


@lru_cache(maxsize=1)
def load_library():
    data = validate_library(json.loads(LIBRARY.read_text(encoding='utf-8')))
    if USER_LIBRARY.exists():
        user = validate_library(json.loads(USER_LIBRARY.read_text(encoding='utf-8')))
        cards = {card['id']: card for card in data['patterns']}
        cards.update({card['id']: card for card in user['patterns']})
        data = {**data, 'patterns': list(cards.values()),
                'library_version': data['library_version'] + '+' + user['library_version']}
    return data


CATEGORY_TRIGGERS = {
    'genai': ('genai', 'generative ai', 'chatbot', 'agentic', 'llm', 'ocr', 'underwriting',
              'document qa', 'speech analytics', 'claim registration', 'omnichannel'),
    'data': ('data lake', 'datalake', 'lakehouse', 'warehouse', 'analytics', 'cdc', 'etl',
             'iceberg', 'hudi', 'db2', 'data platform', 'streaming', 's3 tables'),
    'cloud': ('cloud migration', 'landing zone', 'network topology', 'multi account',
              'disaster recovery', 'infrastructure migration', 'hybrid cloud'),
}


def classify_categories(requirements):
    """Transparent multi-label workload routing, not an LLM or embedding classifier."""
    text = ' ' + _positive_text(requirements) + ' '
    scores = {category: sum(' ' + _normal(term) + ' ' in text for term in triggers)
              for category, triggers in CATEGORY_TRIGGERS.items()}
    return [key for key in sorted(scores, key=lambda key: -scores[key]) if scores[key]]


def _normal(text):
    return re.sub(r'[^a-z0-9]+', ' ', str(text).lower()).strip()


def _positive_text(value):
    """Ignore transport, meta and excluded fields; suppress negative clauses.

    Conservative lexical retrieval is deliberate: no vectors, customer uploads,
    paid model call, database, or network access on the generation path.
    """
    if isinstance(value, dict):
        return ' '.join(_positive_text(v) for k, v in value.items()
                        if not str(k).startswith('_') and not re.search(
                            r'exclud|out.of.scope|future|raw|source|supporting|pricing|token|clarification', str(k), re.I))
    if isinstance(value, list):
        return ' '.join(_positive_text(v) for v in value)
    if not isinstance(value, str):
        return ''
    clauses = re.split(r'[\n.;!?]|\bbut\b', value, flags=re.I)
    return ' '.join(_normal(x) for x in clauses if not re.search(
        r'\b(no|not|without|excluded?|excluding|future|optional)\b', x, re.I))


def select_patterns(requirements, limit=3):
    text = ' ' + _positive_text(requirements) + ' '
    excluded = ' ' + _normal(' '.join(_excluded_text(requirements))) + ' '
    ranked = []
    categories = classify_categories(requirements)
    for card in load_library()['patterns']:
        matches = [t for t in card['triggers'] if ' ' + _normal(t) + ' ' in text]
        veto = any(' ' + _normal(t) + ' ' in excluded for t in card['triggers'])
        if matches and not veto:
            category_match = bool(set(categories) & {card.get('category'), *card.get('secondary_categories', [])})
            ranked.append((len(matches), max(len(t.split()) for t in matches),
                           int(category_match), int(card.get('source_type') == 'user_reference'), card['id'], card))
    ranked.sort(key=lambda x: (-x[0], -x[1], -x[2], -x[3], x[4]))
    selected = [x[5] for x in ranked[:max(0, min(limit, 3))]]
    LOG.info('[ARCHITECTURE][KNOWLEDGE] categories=%s selected=%s', categories, [c['id'] for c in selected])
    return selected


def _excluded_text(value, excluded=False):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _excluded_text(child, excluded or bool(re.search(
                r'exclud|out.of.scope|future', str(key), re.I)))
    elif isinstance(value, list):
        for child in value:
            yield from _excluded_text(child, excluded)
    elif isinstance(value, str):
        for clause in re.split(r'[\n.;!?]|\bbut\b', value, flags=re.I):
            if excluded or re.search(r'\b(no|not|without|excluded?|excluding|future|optional)\b', clause, re.I):
                yield clause


def reference_context(requirements, max_chars=5000):
    try:
        cards = select_patterns(requirements)
        if not cards:
            LOG.info('[ARCHITECTURE][KNOWLEDGE] no applicable pattern; source-only planning')
            return ''
        chunks = [POLICY]
        included = []
        for c in cards:
            item = '\n' + json.dumps({k: c[k] for k in (
                'id', 'title', 'use_when', 'avoid', 'flow', 'layout', 'source_url', 'historical')}
                | {'deployment_checks': c.get('deployment_checks', []),
                   'category': c.get('category', 'aws_general'), 'view': c.get('view', 'reference'),
                   'visual_conventions': c.get('visual_conventions', '')}, ensure_ascii=False)
            if sum(map(len, chunks)) + len(item) > max_chars:
                break
            chunks.append(item)
            included.append(c['id'])
        LOG.info('[ARCHITECTURE][KNOWLEDGE] version=%s patterns=%s chars=%s',
                 load_library()['library_version'], ','.join(included), sum(map(len, chunks)))
        return ''.join(chunks) if included else ''
    except (OSError, ValueError, KeyError, TypeError):
        LOG.exception('[ARCHITECTURE][KNOWLEDGE] library unavailable; source-only planning')
        return ''
