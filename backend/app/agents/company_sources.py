"""Bounded, public corporate evidence lookup; never resolve names by similarity."""
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _request_json(params):
    # Only this fixed public host is fetched. Search titles/URLs never become
    # network destinations, and HTTP redirects cannot escape the allowlist.
    url = 'https://en.wikipedia.org/w/api.php?' + urlencode(params)
    opener = build_opener(_NoRedirects())
    for attempt in range(2):
        try:
            with opener.open(Request(url, headers={
                'User-Agent': 'AgenticSOWCompanyResearch/1.0 (public company profiles)',
                'Accept': 'application/json',
            }), timeout=5) as response:
                body = response.read(256_001)
                if len(body) > 256_000:
                    raise ValueError('Company source response exceeds size limit')
                return json.loads(body)
        except HTTPError as exc:
            if attempt or exc.code not in {429, 500, 502, 503, 504}:
                raise
        except (URLError, TimeoutError):
            if attempt:
                raise


def _identity_pattern(company):
    words = re.findall(r'\w+', company.casefold())
    while words and words[-1] in {'limited', 'ltd', 'private', 'pvt', 'inc', 'incorporated', 'llc'}:
        words.pop()
    return r'\b' + r'\W*'.join(re.escape(word) for word in words) + r'\b' if words else r'(?!)'


def _cached_sources(company_name):
    """Read dated, reviewed corporate evidence, not generated profile prose."""
    try:
        path = Path(__file__).resolve().parents[2] / 'knowledge' / 'company_sources.json'
        entries = json.loads(path.read_text(encoding='utf-8')).get('sources', [])
        return [entry for entry in entries
                if any(_identity_pattern(name) == _identity_pattern(company_name)
                       for name in [entry['company_name'], *entry.get('aliases', [])])
                and 0 <= (datetime.now(timezone.utc).date() - date.fromisoformat(entry['verified_on'])).days <= 90
                and entry.get('text') and entry.get('url', '').startswith('https://')]
    except (OSError, ValueError, KeyError, TypeError):
        return []


def verified_company_audit(audit, company_name):
    """Only reuse an identified, recent profile with retained corporate evidence."""
    if not isinstance(audit, dict) or audit.get('status') != 'verified_identity' or not company_name:
        return False
    if _identity_pattern(str(audit.get('company_name') or '')) != _identity_pattern(company_name):
        return False
    try:
        checked = datetime.fromisoformat(audit.get('checked_at', '')).date()
        if not 0 <= (datetime.now(timezone.utc).date() - checked).days <= 90:
            return False
        sources = audit.get('sources')
        return isinstance(sources, list) and bool(sources) and all(
            isinstance(source, dict) and isinstance(source.get('text'), str) and source['text'].strip()
            and urlparse(source.get('url', '')).scheme == 'https'
            and bool(urlparse(source.get('url', '')).hostname)
            for source in sources)
    except (TypeError, ValueError, AttributeError):
        return False


def lookup_company_sources(company_name):
    """Return one identified corporate page, or an auditable unavailable result."""
    audit = {'company_name': company_name, 'checked_at': datetime.now(timezone.utc).isoformat(),
             'status': 'unavailable', 'sources': []}
    if not company_name or len(company_name) > 200:
        audit['reason'] = 'Invalid company name for public lookup'
        return audit
    cached = _cached_sources(company_name)
    if cached:
        audit.update(status='verified_identity', provider='reviewed_source_cache', sources=cached)
        return audit
    try:
        data = _request_json({'action': 'query', 'format': 'json', 'formatversion': 2,
                              'generator': 'search', 'gsrsearch': '"' + company_name + '"',
                              'gsrnamespace': 0, 'gsrlimit': 3,
                              'prop': 'extracts|pageprops', 'explaintext': 1, 'exintro': 1,
                              'exlimit': 3})
        pages = data.get('query', {}).get('pages', [])
        candidates = []
        for page in pages:
            title, extract = str(page.get('title', '')), str(page.get('extract', ''))
            if 'disambiguation' in page.get('pageprops', {}):
                continue
            # Require the requested identity in the introduction itself, even
            # when a search engine returns a plausible but different company.
            if not re.search(_identity_pattern(company_name), extract[:6000], re.I):
                continue
            if not re.search(r'\b(?:company|business|retailer|manufacturer|enterprise|corporation|subsidiary|platform)\b', extract, re.I):
                continue
            candidates.append({'title': title, 'url': 'https://en.wikipedia.org/wiki/' + quote(title.replace(' ', '_')),
                               'text': extract[:6000]})
        direct = [source for source in candidates if re.fullmatch(
            _identity_pattern(company_name) + r'(?:\W+(?:limited|ltd|private|pvt|inc|incorporated|llc))*',
            source['title'], re.I)]
        if len(direct) == 1:
            candidates = direct
        if len(candidates) == 1:
            audit.update(status='verified_identity', sources=candidates)
        else:
            audit['reason'] = 'Ambiguous company identity' if candidates else 'No exact company identity in public source'
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        audit['reason'] = f'Public company lookup unavailable: {type(exc).__name__}'
    return audit
