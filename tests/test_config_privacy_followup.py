import os
import stat
import pytest
from agents import core, privacy


def test_private_file_is_0600_before_replacement(tmp_path, monkeypatch):
    path = tmp_path / 'token.json'
    path.write_text('old')
    path.chmod(0o644)
    replace = os.replace
    seen = []
    def inspect(source, target):
        seen.append(stat.S_IMODE(os.stat(source).st_mode))
        assert open(source).read() == 'synthetic secret'
        replace(source, target)
    monkeypatch.setattr(os, 'replace', inspect)
    core.write_private(path, 'synthetic secret')
    assert seen == [0o600] and stat.S_IMODE(path.stat().st_mode) == 0o600
    assert list(tmp_path.iterdir()) == [path]


def test_existing_models_without_mode_retains_api_default(monkeypatch):
    monkeypatch.delenv('JOBBOT_MODE', raising=False)
    monkeypatch.setattr(core, 'model_config', lambda: {'writing': 'example-model'})
    assert not core.is_manual()


@pytest.mark.parametrize('phone', ['415–555–0123', '415/555/0123', '415‑555‑0123'])
def test_phone_unicode_dashes_and_slashes_are_detected(phone):
    ids = privacy.identifiers({'person': {'phone': '+1-415-555-0123'}})
    assert privacy.inspect_blob(phone.encode(), 'example.txt', ids, {}, [])


@pytest.mark.parametrize('name', ['Li  Wu', 'Li\u00a0Wu'])
def test_full_name_whitespace_is_normalized(name):
    ids = privacy.identifiers({'person': {'name': 'Li Wu'}})
    assert privacy.inspect_blob(name.encode(), 'example.txt', ids, {}, [])
