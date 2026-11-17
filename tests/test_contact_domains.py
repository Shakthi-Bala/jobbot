import pytest
from checks import contact_sources


@pytest.mark.parametrize('url,expected', [
    ('https://www.bbc.co.uk/news', 'bbc.co.uk'),
    ('https://team.acme.co.uk/about', 'acme.co.uk'),
    ('https://a.example.com.au/team', 'example.com.au'),
    ('https://a.example.com/team', 'example.com'),
    ('https://www.alice.github.io/team', 'alice.github.io'),
    ('https://bob.blogspot.com/team', 'bob.blogspot.com')])
def test_registrable_domain_uses_public_and_private_suffixes(url, expected):
    assert contact_sources.domain(url) == expected


def test_suffix_lookup_cannot_fetch_network(monkeypatch):
    import requests
    import tldextract
    def forbidden(*args, **kwargs):
        raise AssertionError('Suffix lookups must remain offline')
    monkeypatch.setattr(requests.sessions.Session, 'get', forbidden)
    monkeypatch.setattr(contact_sources, '_DOMAIN_EXTRACTOR', tldextract.TLDExtract(
        suffix_list_urls=(), cache_dir=None, include_psl_private_domains=True))
    assert contact_sources.domain('https://bbc.co.uk') != contact_sources.domain('https://acme.co.uk')
