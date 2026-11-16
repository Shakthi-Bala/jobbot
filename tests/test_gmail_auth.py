from types import SimpleNamespace as NS
import sys
import pytest
from agents import core, discover


def test_daily_gmail_does_not_open_browser_when_auth_is_missing(env):
    (core.DATA / 'credentials.json').write_text('{}')
    with pytest.raises(core.JobbotError, match='gmail-auth'):
        discover.gmail_alert_urls()
    assert not (core.DATA / 'token.json').exists()


def test_explicit_gmail_auth_is_bounded_and_saves_private_token(env, monkeypatch):
    (core.DATA / 'credentials.json').write_text('{}')
    options = []
    def local_server(**kwargs):
        options.append(kwargs)
        return NS(to_json=lambda: '{"token": "example"}')
    factory = NS(from_client_secrets_file=lambda *a: NS(run_local_server=local_server))
    monkeypatch.setitem(sys.modules, 'google_auth_oauthlib.flow', NS(InstalledAppFlow=factory))
    discover.gmail_credentials(interactive=True)
    assert options == [{'port': 0, 'timeout_seconds': 120}]
    assert (core.DATA / 'token.json').stat().st_mode & 0o777 == 0o600
