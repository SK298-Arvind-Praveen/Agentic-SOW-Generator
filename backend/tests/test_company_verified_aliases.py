from app.agents.company_sources import lookup_company_sources, _cached_sources


def test_verified_tvs_name_variants_resolve_without_network(monkeypatch):
    def unexpected(*args):
        raise AssertionError('Verified evidence should avoid network lookup')
    monkeypatch.setattr('app.agents.company_sources._request_json', unexpected)
    for name in ['TVS Motors', 'TVS Motor', 'TVS Motor Company Limited']:
        result = lookup_company_sources(name)
        assert result['status'] == 'verified_identity'
        assert result['sources'][0]['url'] == 'https://www.tvsmotor.com/about-us/overview'


def test_aliases_do_not_match_other_tvs_businesses():
    assert not _cached_sources('TVS Supply Chain Solutions')
    assert not _cached_sources('TVS')
