import json
from agents import core, demo


def test_offline_demo_runs_real_cli_and_keeps_candidate_data_untouched(env, monkeypatch):
    monkeypatch.setenv('JOBBOT_MODE', 'api')  # the demo must explicitly force manual mode
    profile = (core.DATA / 'profile.yaml').read_bytes()
    core.DB_PATH.write_bytes(b'production tracker must stay untouched')
    result = demo.run()
    packet = __import__('pathlib').Path(result['packet'])
    assert result['network_calls'] is False
    assert (core.DATA / 'profile.yaml').read_bytes() == profile
    assert core.DB_PATH.read_bytes() == b'production tracker must stay untouched'
    checks = json.loads((packet / 'checks.json').read_text())
    assert checks and all(not findings for findings in checks.values())
    assert (packet / 'resume.pdf').read_bytes().startswith(b'%PDF')
    rounds = json.loads((packet / 'panel.json').read_text())
    assert len(rounds) == 2
    assert rounds[0]['revisions'] and not rounds[1]['revisions']
    panel = rounds[-1]
    assert len(panel['reviews']) == 7
    assert 'DEMO FIXTURE' in panel['reviews']['ats_gate']['reason']
    recording = json.loads((__import__('pathlib').Path(result['workspace']) / 'demo-recording.json').read_text())
    revision = recording['revision']
    assert revision['rounds'] == [1, 2]
    assert revision['before_sha256'] != revision['after_sha256']
    assert revision['critique']['quote'] == revision['before']['text']
    assert 'Implemented an Open3D' in revision['after']['text']
    assert revision['before']['text'] not in (packet / 'resume.tagged.md').read_text()
    assert revision['after']['text'] in (packet / 'resume.tagged.md').read_text()
