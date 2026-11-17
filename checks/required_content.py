"""Required letters and application questions cannot silently disappear from a packet."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checks._lib import cli, core, db, diagnostic, meta  # noqa: E402


def check(d: Path) -> list[str]:
    info = meta(d)
    job_id = info.get('job_id')
    job = db().execute('SELECT parsed_json, raw_text FROM jobs WHERE id=?', (job_id,)).fetchone()
    if job is None:
        return ['job missing from tracker']
    parsed = json.loads(job['parsed_json'] or '{}')
    bad = []
    prefs = core.load_profile().get('preferences', {})
    minimum = max(int(info.get('min_projects', 0)), int(prefs.get('resume_min_projects', 0)))
    if minimum:
        path = d / 'resume.json'
        resume = json.loads(path.read_text()) if path.exists() else {}
        projects = {p.get('ref_id') or p.get('heading') for p in resume.get('projects', [])
                    if p.get('bullets') and (p.get('ref_id') or p.get('heading'))}
        if len(projects) < minimum:
            bad.append(f'resume has {len(projects)} distinct projects; candidate requires at least {minimum}')
    minimum_bullets = max(int(info.get('min_project_bullets', 0)), int(prefs.get('resume_min_project_bullets', 0)))
    if minimum_bullets:
        path = d / 'resume.json'
        resume = json.loads(path.read_text()) if path.exists() else {}
        for project in resume.get('projects', []):
            bullets = {b.strip() for b in project.get('bullets', []) if isinstance(b, str) and b.strip()}
            if len(bullets) < minimum_bullets:
                label = project.get('heading') or project.get('ref_id') or 'unnamed project'
                bad.append(diagnostic(f'project has {len(bullets)} distinct bullets; candidate requires at least {minimum_bullets}', project=label))
    letter = d / 'cover_letter.md'
    from agents.tailor import wants_cover_letter
    if wants_cover_letter(parsed, {'preferences': prefs}) and (
            not letter.exists() or not letter.read_text().strip()):
        bad.append('a cover letter is required (posting request or preferences.cover_letter), '
                   'but the packet has none')
    if letter.exists() and info.get('company') and core.normalize(info['company']) not in core.normalize(
            letter.read_text()):
        bad.append(diagnostic('cover letter never names the company', company=info['company']))
    answers = d / 'answers.tagged.md'
    present = {core.normalize(line.removeprefix('## Q:').strip())
               for line in (answers.read_text().splitlines() if answers.exists() else [])
               if line.startswith('## Q:')}
    declared = {core.normalize(q) for q in parsed.get('application_questions', [])}
    for label in (answers.read_text().splitlines() if answers.exists() else []):
        if label.startswith('## Q:'):
            question = label.removeprefix('## Q:').strip()
            if core.normalize(question) not in declared or not core.quote_in_text(question, job['raw_text'] or ''):
                bad.append('unverified application question in packet:\n' + core.untrusted('application_question', question))
    for question in parsed.get('application_questions', []):
        if not core.quote_in_text(question, job['raw_text'] or ''):
            bad.append('application question is not quoted in the posting source:\n' + core.untrusted('application_question', question))
        if core.normalize(question) not in present:
            bad.append('required application question missing:\n' + core.untrusted('application_question', question))
    return bad


if __name__ == '__main__':
    cli(check, 'required_content')
