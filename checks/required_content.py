"""Required letters and application questions cannot silently disappear from a packet."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checks._lib import cli, core, db, meta  # noqa: E402


def check(d: Path) -> list[str]:
    job_id = meta(d).get('job_id')
    job = db().execute('SELECT parsed_json FROM jobs WHERE id=?', (job_id,)).fetchone()
    if job is None:
        return ['job missing from tracker']
    parsed = json.loads(job['parsed_json'] or '{}')
    bad = []
    letter = d / 'cover_letter.md'
    if parsed.get('cover_letter_requested') and (not letter.exists() or not letter.read_text().strip()):
        bad.append('posting requests a cover letter, but the packet has none')
    answers = d / 'answers.tagged.md'
    present = {core.normalize(line.removeprefix('## Q:').strip())
               for line in (answers.read_text().splitlines() if answers.exists() else [])
               if line.startswith('## Q:')}
    for question in parsed.get('application_questions', []):
        if core.normalize(question) not in present:
            bad.append(f'required application question missing: {question}')
    return bad


if __name__ == '__main__':
    cli(check, 'required_content')
