import socket
import httpx
import pytest
from checks import contact_sources as sources


@pytest.mark.parametrize('address', ['127.0.0.1', '10.1.2.3', '169.254.169.254', '::1', 'fc00::1'])
def test_non_public_sources_are_never_requested(monkeypatch, address):
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **k: [(0, 0, 0, '', (address, 443))])
    with pytest.raises(ValueError, match='non-public'):
        sources.public_target('https://internal.example/page')


def mock_client(monkeypatch, handler):
    original = httpx.Client
    monkeypatch.setattr(sources.httpx, 'Client', lambda **kw: original(
        **kw, transport=httpx.MockTransport(handler)))
    def resolve(host, *a, **k):
        return [(0, 0, 0, '', ('127.0.0.1' if host == 'internal.example' else '93.184.216.34', 443))]
    monkeypatch.setattr(socket, 'getaddrinfo', resolve)


def test_redirect_to_private_network_is_blocked_before_second_request(monkeypatch):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(302, headers={'location': 'https://internal.example/secrets'})
    mock_client(monkeypatch, handler)
    assert not sources.page_confirms('https://public.example', 'Alex Example', 'Acme')
    assert len(calls) == 1
    assert calls[0].url.host == '93.184.216.34'
    assert calls[0].headers['host'] == 'public.example'
    assert calls[0].extensions['sni_hostname'] == 'public.example'


def test_sources_are_counted_by_final_domain(monkeypatch):
    mock_client(monkeypatch, lambda request: httpx.Response(200, text='Alex Example at Acme'))
    monkeypatch.setattr(sources, 'public_page', lambda url: ('Alex Example at Acme', 'https://same.example/team'))
    assert len(sources.verified_sources(['https://one.example', 'https://two.example'], 'Alex Example', 'Acme')) == 1


def test_redirect_to_disallowed_domain_is_blocked(monkeypatch):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(302, headers={'location': 'https://www.linkedin.com/in/person'})
    mock_client(monkeypatch, handler)
    assert not sources.page_confirms('https://public.example', 'Alex Example', 'Acme')
    assert len(calls) == 1


def test_public_confirmation_uses_pinned_address(monkeypatch):
    mock_client(monkeypatch, lambda request: httpx.Response(200, text='Alex Example at Acme'))
    assert sources.page_confirms('https://public.example/team', 'Alex Example', 'Acme')
