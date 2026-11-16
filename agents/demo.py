"""Run the actual CLI with isolated synthetic data and recorded structured answers."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

from . import core, schemas

SOURCE = Path(__file__).resolve().parents[1]


def run() -> dict:
    base = core.OUT / 'demo'
    base.mkdir(parents=True, exist_ok=True)
    # Never overwrite a previous run, a real tracker, or an edited demo profile.
    number = 1
    while (base / f'run-{number:03d}').exists():
        number += 1
    root = base / f'run-{number:03d}'
    root.mkdir()
    (root / 'data').mkdir()
    for name in ('schema.sql', 'models.example.yaml'):
        shutil.copy(SOURCE / name, root / name)
    for folder in ('skills', 'principles', 'templates'):
        shutil.copytree(SOURCE / folder, root / folder)
    for name in ('profile.example.yaml', 'answers_bank.example.yaml'):
        shutil.copy(SOURCE / 'data' / name, root / 'data' / name)
    (root / 'data/companies.yaml').write_text('companies: []\n')
    posting = root / 'posting.txt'
    shutil.copy(SOURCE / 'data/evals/example-perception/posting.txt', posting)
    fixtures = json.loads((SOURCE / 'data/demo/answers.json').read_text())
    env = dict(os.environ, JOBBOT_ROOT=str(root), JOBBOT_MODE='manual')
    # Force the recorded offline route; inherited provider keys are never used.
    events = []

    def execute(args):
        command = [sys.executable, str(SOURCE / 'jobbot.py'), *args]
        result = subprocess.run(command, cwd=SOURCE, env=env, text=True,
                                capture_output=True, timeout=180)
        shown = ['python', 'jobbot.py', *[str(arg).replace(str(root), '<demo>') for arg in args]]
        output = (result.stdout + result.stderr).replace(str(root), '<demo>')
        events.append({'command': shlex.join(shown), 'output': output, 'exit_code': result.returncode})
        print('$ ' + shlex.join(shown))
        print(output.rstrip())
        if result.returncode not in (0, 3):
            raise core.JobbotError('Offline demo command failed; inspect the isolated run log')
        return result

    def complete(args):
        for _ in range(25):
            result = execute(args)
            if result.returncode == 0:
                return
            answered = 0
            for task in sorted((root / 'out/tasks').glob('*.task.md')):
                answer = task.with_name(task.name.replace('.task.md', '.answer.json'))
                if answer.exists():
                    continue
                match = re.search(r' -> (\w+)', task.read_text().splitlines()[0])
                name = match[1] if match else ''
                if name not in fixtures:
                    raise core.JobbotError(f'Demo has no fixture for {name}')
                value = getattr(schemas, name).model_validate(fixtures[name])
                answer.write_text(core.dumps(value.model_dump()))
                answered += 1
            if not answered:
                raise core.JobbotError('Demo paused without a pending task')
        raise core.JobbotError('Demo exceeded its task resumption limit')

    try:
        complete(['init'])
        profile = core.load_yaml(root / 'data/profile.yaml')
        profile['preferences'].update(resume_format='typst', resume_summary=False,
                                      cover_letter='always', resume_min_projects=4,
                                      resume_min_project_bullets=2)
        import yaml
        (root / 'data/profile.yaml').write_text(yaml.safe_dump(profile, sort_keys=False))
        complete(['add-jd', str(posting), '--company', 'Example Robotics',
                  '--title', 'Perception Engineer', '--location', 'Boston, MA'])
        # Read the isolated tracker, never the candidate's production database.
        conn = core.connect(root / 'data/tracker.db')
        try:
            jid = conn.execute('SELECT id FROM jobs').fetchone()[0]
        finally:
            conn.close()
        complete(['packet', jid, '--offline'])
        complete(['checks', jid, '--offline'])
        packet = next(path.parent for path in (root / 'out').glob('*/meta.json')
                      if json.loads(path.read_text()).get('job_id') == jid)
        result = {'workspace': str(root), 'packet': str(packet), 'job_id': jid,
                  'synthetic_data': True, 'review_source': 'recorded fixtures; no model assessment',
                  'network_calls': False}
        (base / 'latest.json').write_text(core.dumps(result))
        print('Offline demo complete. Scores are recorded fixtures, not model or employer judgments.')
        print(f'Resume: {packet / "resume.pdf"}')
        return result
    finally:
        (root / 'demo-recording.json').write_text(core.dumps({
            'synthetic_data': True, 'review_source': 'recorded fixtures', 'events': events}))
