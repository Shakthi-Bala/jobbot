import json
from pathlib import Path
import subprocess
import sys
from agents import core, demo


def test_offline_demo_runs_real_cli_and_keeps_candidate_data_untouched(env, monkeypatch):
    monkeypatch.setenv('JOBBOT_MODE', 'api')  # the demo must explicitly force manual mode
    profile = (core.DATA / 'profile.yaml').read_bytes()
    core.DB_PATH.write_bytes(b'production tracker must stay untouched')
    result = demo.run()
    packet = Path(result['packet'])
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
    workspace = Path(result['workspace'])
    recording = json.loads((workspace / 'demo-recording.json').read_text())
    revision = recording['revision']
    assert revision['rounds'] == [1, 2]
    assert revision['before_sha256'] != revision['after_sha256']
    assert revision['critique']['quote'] == revision['before']['text']
    assert 'Implemented an Open3D' in revision['after']['text']
    assert revision['before']['text'] not in (packet / 'resume.tagged.md').read_text()
    assert revision['after']['text'] in (packet / 'resume.tagged.md').read_text()
    for row in rounds:
        scores = [row['reviews'][reader]['score'] for reader in ('team_lead', 'competing_applicant',
                   'ceo', 'senior_engineer', 'recruiter')]
        assert len(set(scores)) > 1 and min(scores) >= 6.8 and max(scores) <= 7.6
    assert rounds[1]['reviews']['senior_engineer']['score'] > rounds[0]['reviews']['senior_engineer']['score']
    # Invalid rendered evidence must still fail with Python's assertions disabled.
    code = '''
import json, sys
from pathlib import Path
from agents import demo
revision = json.loads(Path(sys.argv[1]).read_text())['revision']
revision['after']['text'] = 'An unsupported replacement'
demo._record_revision(Path(sys.argv[2]), Path(sys.argv[3]), revision)
'''
    invalid = subprocess.run([sys.executable, '-O', '-c', code,
                              str(workspace / 'demo-recording.json'), str(packet),
                              str(workspace / 'revision-before.pdf')], cwd=demo.SOURCE,
                             text=True, capture_output=True, timeout=30)
    assert invalid.returncode != 0
    assert 'JobbotError: Demo revised bullet is missing' in invalid.stderr
