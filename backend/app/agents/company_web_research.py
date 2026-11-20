"""Company discovery from live search, followed by bounded corporate source reads.

No client registry: name similarity proposes candidates, source identity selects them.
"""
import ipaddress
import json
import re
import socket
from datetime import datetime, timezone
from difflib import SequenceMatcher
from urllib.parse import urlencode, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from app.agents.company_sources import _request_json


def normalized_name(name):
    words = re.findall(r'[a-z0-9]+', name.casefold())
    legal = {'limited', 'ltd', 'private', 'pvt', 'inc', 'incorporated', 'llc', 'company', 'co', 'corporation', 'plc'}
    return ' '.join(w[:-1] if w in {'motors', 'hospitals', 'systems'} else w
                    for w in words if w not in legal)


def name_score(requested, candidate):
    left, right = normalized_name(requested), normalized_name(candidate)
    if not left or not right:
        return 0
    if left == right:
        return 1
    # A shared group name alone cannot identify an unrelated subsidiary.
    if len(left.split()) != len(right.split()):
        return 0
    return SequenceMatcher(None, left, right).ratio()


def _public_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in {'https', 'http'} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Invalid corporate source URL')
    if parsed.port not in {None, 80, 443}:
        raise ValueError('Unsupported corporate source port')
    addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError('Corporate source is not a public address')


def read_public(url, *, json_response=False):
    """Revalidate every redirect; never send cookies, credentials or BRD data."""
    for _ in range(4):
        _public_url(url)
        with requests.get(url, headers={'User-Agent': 'SOWCompanyResearch/1.0'},
                          timeout=(4, 8), allow_redirects=False, stream=True) as response:
            if response.is_redirect:
                url = urljoin(url, response.headers['Location'])
                continue
            response.raise_for_status()
            chunks, size = [], 0
            for chunk in response.iter_content(16384):
                size += len(chunk)
                if size > 1_000_000:
                    raise ValueError('Corporate source exceeds size limit')
                chunks.append(chunk)
            raw = b''.join(chunks).decode('utf-8', errors='replace')
            return (json.loads(raw) if json_response else raw), url
    raise ValueError('Too many source redirects')


def _wikipedia_candidates(query):
    data = _request_json({'action': 'query', 'format': 'json', 'formatversion': 2,
        'generator': 'search', 'gsrsearch': query, 'gsrnamespace': 0, 'gsrlimit': 5,
        'prop': 'extracts|pageprops', 'explaintext': 1, 'exintro': 1, 'exlimit': 5})
    return [p for p in data.get('query', {}).get('pages', [])
            if 'disambiguation' not in p.get('pageprops', {})
            and re.search(r'\b(company|manufacturer|business|corporation|retailer|hospital chain)\b', p.get('extract', ''), re.I)]


def _official_website(page):
    entity = page.get('pageprops', {}).get('wikibase_item', '')
    if not re.fullmatch(r'Q\d+', entity):
        return ''
    data, _ = read_public('https://www.wikidata.org/wiki/Special:EntityData/' + entity + '.json', json_response=True)
    claims = data.get('entities', {}).get(entity, {}).get('claims', {}).get('P856', [])
    active = [c for c in claims if c.get('rank') != 'deprecated' and 'P582' not in c.get('qualifiers', {})]
    active.sort(key=lambda c: c.get('rank') != 'preferred')
    return next((c['mainsnak']['datavalue']['value'] for c in active if 'datavalue' in c.get('mainsnak', {})), '')


def _corporate_page(url, identity, follow_about=True):
    html, final_url = read_public(url)
    soup = BeautifulSoup(html, 'html.parser')
    if follow_about:
        links = [urljoin(final_url, a['href']) for a in soup.select('a[href]')
                 if re.search(r'about|company profile|who we are', a.get_text(' ', strip=True), re.I)]
        for link in list(dict.fromkeys(links))[:2]:
            if urlparse(link).hostname != urlparse(final_url).hostname or link == final_url:
                continue
            try:
                profile = _corporate_page(link, identity, follow_about=False)
                if profile:
                    return profile
            except Exception:
                pass
    for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'noscript']):
        tag.decompose()
    text = soup.get_text(' ', strip=True)
    # Corporate sites often use Motor Co. or omit the legal suffix.
    words = normalized_name(identity).split()
    if not all(re.search(r'\b' + re.escape(word) + r's?\b', text, re.I) for word in words):
        return None
    if len(text.split()) < 40 or 'lorem ipsum' in text.casefold():
        return None
    return {'title': identity + ' corporate website', 'url': final_url, 'text': text[:14000], 'kind': 'official'}


def research_sources(company_name, config=None, llm=None):
    audit = {'company_name': company_name, 'checked_at': datetime.now(timezone.utc).isoformat(),
             'status': 'unavailable', 'sources': [], 'attempts': [], 'provider': 'live_web_research'}
    if not isinstance(company_name, str) or not company_name.strip() or len(company_name) > 200:
        audit['reason'] = 'A valid company name is required'
        return audit
    candidates = []
    # Search original wording, then normalized wording. No per-company aliases.
    for query in dict.fromkeys([company_name, normalized_name(company_name)]):
        try:
            candidates.extend(_wikipedia_candidates(query))
            audit['attempts'].append({'provider': 'wikipedia_search', 'query': query, 'status': 'ok'})
        except Exception as exc:
            audit['attempts'].append({'provider': 'wikipedia_search', 'status': type(exc).__name__})
    unique = {p['title']: p for p in candidates}
    ranked = sorted(((name_score(company_name, p['title']), p) for p in unique.values()), key=lambda p: p[0], reverse=True)
    selected = None
    if ranked and ranked[0][0] >= .84 and (len(ranked) == 1 or ranked[0][0] - ranked[1][0] >= .10):
        selected = ranked[0][1]
    if selected:
        identity = selected['title']
        try:
            expanded = _request_json({'action': 'query', 'format': 'json', 'formatversion': 2,
                'titles': identity, 'prop': 'extracts', 'explaintext': 1, 'exchars': 12000, 'exlimit': 1})
            full = next(iter(expanded.get('query', {}).get('pages', [])), {}).get('extract')
            if full:
                selected = {**selected, 'extract': full}
        except Exception:
            pass  # The identified introduction remains valid evidence.
        from urllib.parse import quote
        audit['resolved_name'] = identity
        audit['sources'] = [{'title': identity, 'url': 'https://en.wikipedia.org/wiki/' + quote(identity.replace(' ', '_')),
                             'text': selected['extract'][:10000], 'kind': 'encyclopedia'}]
        try:
            website = _official_website(selected)
            if website:
                source = _corporate_page(website, identity)
                if source:
                    audit['sources'].insert(0, source)
        except Exception as exc:
            audit['attempts'].append({'provider': 'official_website', 'status': type(exc).__name__})
    # The optional supported search API expands discovery beyond encyclopedia coverage.
    key, engine = getattr(config, 'GOOGLE_API_KEY', ''), getattr(config, 'GOOGLE_CSE_ID', '')
    if key and engine:
        try:
            response = requests.get('https://www.googleapis.com/customsearch/v1',
                params={'key': key, 'cx': engine, 'q': company_name + ' official company about', 'num': 5}, timeout=10)
            response.raise_for_status()
            for item in response.json().get('items', []):
                title = re.split(r'\s[|–—-]\s', item.get('title', ''))[0]
                if name_score(company_name, title) < .84:
                    continue
                try:
                    source = _corporate_page(item['link'], selected['title'] if selected else title)
                    if source:
                        audit['sources'].append(source)
                        audit.setdefault('resolved_name', title)
                except Exception:
                    continue
            audit['attempts'].append({'provider': 'google_search_api', 'status': 'ok'})
        except Exception as exc:
            audit['attempts'].append({'provider': 'google_search_api', 'status': type(exc).__name__})
    if llm is not None and not any(s.get('kind') == 'official' for s in audit['sources']):
        try:
            # Model memory may suggest a discovery destination, never profile facts.
            answer = llm.generate(
                'Suggest up to three public official company website/about-page URLs for the company name below. '
                'Handle spelling variants and legal suffixes. Return JSON only: {"urls": ["https://..."]}. '
                'Do not return profile prose. These URLs will be fetched and independently checked. Company name: '
                + json.dumps(company_name), task='fast', max_tokens=400, temperature=0,
                call_name='Company website discovery')
            payload = re.search(r'\{.*\}', answer.text, re.S)
            urls = json.loads(payload[0]).get('urls', []) if payload else []
            for url in urls[:3]:
                try:
                    source = _corporate_page(url, selected['title'] if selected else company_name)
                    if source:
                        audit['sources'].insert(0, source)
                        audit.setdefault('resolved_name', company_name)
                        break
                except Exception:
                    continue
            audit['attempts'].append({'provider': 'verified_website_discovery', 'status': 'ok'})
        except Exception as exc:
            audit['attempts'].append({'provider': 'verified_website_discovery', 'status': type(exc).__name__})
    if audit['sources']:
        audit['status'] = 'verified_identity'
    else:
        audit['status'] = 'needs_identity' if len(ranked) > 1 else 'unavailable'
        audit['candidates'] = [p['title'] for score, p in ranked[:3] if score > .5]
        audit['reason'] = 'Provide the company website or full legal name to identify a reliable corporate source'
    return audit
