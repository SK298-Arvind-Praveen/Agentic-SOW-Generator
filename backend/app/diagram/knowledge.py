"""Curated AWS and user references. Advisory context, never project requirements."""
from datetime import date
from functools import lru_cache
import json
import hashlib
import logging
from pathlib import Path
import re
from urllib.parse import urlparse

LIBRARY = Path(__file__).resolve().parents[2] / 'knowledge/architecture/patterns.json'
USER_LIBRARY = LIBRARY.with_name('user-patterns.json')
AWS_LIBRARY = LIBRARY.with_name('aws-patterns.json')
MAX_REFERENCE_CHARS = 10000
MAX_REFERENCE_PATTERNS = 6
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
Service choices and relationship checks below are conditional design guidance,
not mandatory inventories or executable validators. Select alternatives explicitly.
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
        date.fromisoformat(card['reviewed_on'])
        for key in ('service_choices', 'relationship_checks', 'deployment_checks'):
            if key in card and (not isinstance(card[key], list) or not all(
                    isinstance(item, str) and item.strip() for item in card[key])):
                raise ValueError(f'{card["id"]}: invalid {key}')
        if card.get('pattern_role', 'workload') not in {'workload', 'decision', 'support'}:
            raise ValueError(f'{card["id"]}: invalid pattern_role')
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
    aws = validate_library(json.loads(AWS_LIBRARY.read_text(encoding='utf-8')))
    # Official additions must not silently replace an older card. User-reviewed
    # overrides retain their existing explicit precedence below.
    data = validate_library({**data, 'patterns': data['patterns'] + aws['patterns'],
                             'library_version': data['library_version'] + '+' + aws['library_version']})
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
              'disaster recovery', 'infrastructure migration', 'hybrid cloud',
              'database migration', 'private subnets', 'catalogue service', 'booking portal'),
    'application': ('web portal', 'serverless api', 'container platform', 'human review',
                    'multi tenant', 'it help desk', 'itsm', 'event routing'),
    'security': ('identity federation', 'user authentication', 'security tooling', 'named reviewers'),
    'operations': ('cost ceiling', 'budget alerts', 'cost tracking', 'spending limit'),
}


def classify_categories(requirements):
    """Transparent multi-label workload routing, not an LLM or embedding classifier."""
    text = ' ' + _positive_text(requirements) + ' '
    scores = {category: sum(' ' + _normal(term) + ' ' in text for term in triggers)
              for category, triggers in CATEGORY_TRIGGERS.items()}
    return [key for key in sorted(scores, key=lambda key: -scores[key]) if scores[key]]


def _normal(text):
    return re.sub(r'[^a-z0-9]+', ' ', str(text).lower()).strip()


GENERATED_FIELDS = {'service_design', 'architecture_design', 'architecture_previous_design',
                    'architecture_revision_history'}
NEGATIVE = re.compile(r'\b(no|not|without|excluded?|excluding|future|optional)\b', re.I)
POSTFIX_EXCLUSION = re.compile(
    r'\b(?:is|are|be)\s+(?:excluded?|optional)\b|'
    r'\bnot\s+(?:required|needed|supported|permitted|planned|selected|included|added|deployed|used|in scope)\b|'
    r'\bexcluded?\s*$', re.I)


def _positive_text(value):
    """Ignore transport, meta and excluded fields; suppress negative clauses.

    Conservative lexical retrieval is deliberate: no vectors, customer uploads,
    paid model call, database, or network access on the generation path.
    """
    if isinstance(value, dict):
        return ' '.join(_positive_text(v) for k, v in value.items()
                        if k not in GENERATED_FIELDS
                        and not str(k).startswith('_') and not re.search(
                            r'exclud|out.of.scope|future|raw|source|supporting|pricing|token|clarification', str(k), re.I))
    if isinstance(value, list):
        return ' '.join(_positive_text(v) for v in value)
    if not isinstance(value, str):
        return ''
    clauses = re.split(r'[\n.;!?]|\bbut\b', value, flags=re.I)
    # Preserve a capability before a separate negative qualifier: "document
    # extraction without human review" still describes document extraction.
    return ' '.join(_normal(NEGATIVE.split(x, maxsplit=1)[0]) for x in clauses
                    if not POSTFIX_EXCLUSION.search(x))


def select_patterns(requirements, limit=3):
    text = ' ' + _positive_text(requirements) + ' '
    excluded = ' ' + _normal(' '.join(_excluded_text(requirements))) + ' '
    ranked = []
    categories = classify_categories(requirements)
    # These IDs are selected by the architect from the full semantic directory,
    # not inferred from the literal spelling of the customer's requirements.
    design = requirements.get('service_design') or {} if isinstance(requirements, dict) else {}
    semantic_ids = set(design.get('reference_pattern_ids') or [])
    for card in load_library()['patterns']:
        matches = [t for t in card['triggers'] if ' ' + _normal(t) + ' ' in text]
        veto = any(' ' + _normal(t) + ' ' in excluded for t in card['triggers'])
        if (matches or card['id'] in semantic_ids) and not veto:
            category_match = bool(set(categories) & {card.get('category'), *card.get('secondary_categories', [])})
            role = {'workload': 0, 'decision': 1, 'support': 2}[card.get('pattern_role', 'workload')]
            ranked.append((-1 if card['id'] in semantic_ids else role, len(matches), max((len(t.split()) for t in matches), default=0),
                           int(category_match), int(card.get('source_type') == 'user_reference'), card['id'], card))
    # Generic controls must not crowd the defining workload out of its own prompt.
    ranked.sort(key=lambda x: (x[0], -x[1], -x[2], -x[3], -x[4], x[5]))
    selected = [x[6] for x in ranked[:max(0, min(limit, MAX_REFERENCE_PATTERNS))]]
    LOG.info('[ARCHITECTURE][KNOWLEDGE] categories=%s selected=%s', categories, [c['id'] for c in selected])
    return selected


def semantic_directory():
    """Every pattern is visible to the existing design call, independent of wording."""
    try:
        return [{'id': c['id'], 'title': c['title'], 'use_when': c['use_when'],
                 'flow': c['flow']} for c in load_library()['patterns']]
    except (OSError, ValueError, KeyError, TypeError):
        LOG.exception('[ARCHITECTURE][KNOWLEDGE] semantic directory unavailable')
        return []


def _excluded_text(value, excluded=False):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in GENERATED_FIELDS or str(key).startswith('_') or re.search(
                    r'raw|source|supporting|pricing|token|clarification', str(key), re.I):
                continue
            yield from _excluded_text(child, excluded or bool(re.search(
                r'exclud|out.of.scope|future', str(key), re.I)))
    elif isinstance(value, list):
        for child in value:
            yield from _excluded_text(child, excluded)
    elif isinstance(value, str):
        for clause in re.split(r'[\n.;!?]|\bbut\b', value, flags=re.I):
            if excluded:
                yield clause
            elif negative := NEGATIVE.search(clause):
                # A suffix such as "not production" does not exclude the source
                # clone mentioned earlier. Postfixed exclusion still vetoes its
                # subject: "OCR is not required" or "OCR excluded".
                if POSTFIX_EXCLUSION.search(clause):
                    yield clause
                else:
                    yield clause[negative.start():]


def reference_bundle(requirements, max_chars=MAX_REFERENCE_CHARS):
    """Return exactly the context supplied plus audit metadata, with whole cards.

    A content digest also invalidates cached service designs after a relevant
    reference changes. No live web fetch or extra inference is performed here.
    """
    try:
        cards = select_patterns(requirements, limit=MAX_REFERENCE_PATTERNS)
        chunks = [POLICY]
        included, omitted = [], []
        for c in cards:
            item = '\n' + json.dumps({k: c[k] for k in (
                'id', 'title', 'use_when', 'avoid', 'flow', 'layout', 'source_url', 'historical')}
                | {'deployment_checks': c.get('deployment_checks', []),
                   'service_choices': c.get('service_choices', []),
                   'relationship_checks': c.get('relationship_checks', []),
                   'category': c.get('category', 'aws_general'), 'view': c.get('view', 'reference'),
                   'visual_conventions': c.get('visual_conventions', '')},
                ensure_ascii=False, separators=(',', ':'))
            if sum(map(len, chunks)) + len(item) > max_chars:
                omitted.append(c['id'])
                continue
            chunks.append(item)
            included.append(c['id'])
        context = ''.join(chunks) if included else ''
        result = {'context': context, 'library_version': load_library()['library_version'],
                  'pattern_ids': included, 'omitted_for_budget': omitted,
                  'context_sha256': hashlib.sha256(context.encode('utf-8')).hexdigest()}
        LOG.info('[ARCHITECTURE][KNOWLEDGE] version=%s patterns=%s omitted=%s chars=%s',
                 result['library_version'], included, omitted, len(context))
        return result
    except (OSError, ValueError, KeyError, TypeError):
        LOG.exception('[ARCHITECTURE][KNOWLEDGE] library unavailable; source-only planning')
        return {'context': '', 'library_version': 'unavailable', 'pattern_ids': [],
                'omitted_for_budget': [], 'context_sha256': '', 'error': 'library_unavailable'}


def reference_context(requirements, max_chars=MAX_REFERENCE_CHARS):
    return reference_bundle(requirements, max_chars)['context']


def reference_layout_context(provenance, max_chars=2500):
    """Only arrangement guidance for the fixed-graph composition stage.

    Resolve previously selected IDs locally; never retrieve again from model-
    generated prose, which would amplify the planner's own service assumptions.
    """
    ids = provenance.get('pattern_ids', []) if isinstance(provenance, dict) else []
    if not ids:
        return []
    try:
        by_id = {c['id']: c for c in load_library()['patterns']}
        result = []
        used = 0
        for key in ids[:MAX_REFERENCE_PATTERNS]:
            if key not in by_id:
                continue
            item = {'id': key, 'layout': by_id[key]['layout']}
            size = len(json.dumps(item, ensure_ascii=False))
            if used + size <= max_chars:
                result.append(item)
                used += size
        return result
    except (OSError, ValueError, KeyError, TypeError):
        LOG.exception('[ARCHITECTURE][KNOWLEDGE] layout guidance unavailable; retaining fixed graph')
        return []
