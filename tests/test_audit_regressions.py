"""Regressions found by the end-to-end jobbot audit. No live APIs or personal data."""
import json
from pathlib import Path

import httpx
import pytest

from agents import core, discover, fit, latex, notify, packet as pipeline, tailor, tracker
from agents.schemas import FitRestriction, FitResult
from checks import ats_parse, contact_sources, restriction_quotes
from tests.test_checks import good_packet


def shortlist(job):
    conn = core.connect()
    conn.execute("INSERT INTO fit (job_id,score,decision) VALUES (?,80,'shortlist')", (job['id'],))
    core.set_status(conn, job['id'], 'shortlisted')
    return conn


def test_distinct_requisitions_are_not_merged(env):
    conn = core.connect()
    base = dict(company='Acme', title='Engineer', location='Boston', source='greenhouse', raw_text='JD')
    ids = discover.upsert_jobs(conn, [base | {'req_id': 'R-1'}, base | {'req_id': 'R-2'}], {}, parse=False)
    assert len(ids) == 2 and ids[0] != ids[1]
    assert discover.upsert_jobs(conn, [base | {'req_id': 'R-1', 'title': 'Updated Engineer'}], {}, parse=False) == []
    assert conn.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] == 2
    assert core.get_job(conn, ids[0])['title'] == 'Updated Engineer'


def test_legacy_ids_and_changed_postings(env):
    conn = core.connect()
    j = dict(company='Acme', title='Engineer', location='Boston', req_id='R-1', source='greenhouse', raw_text='Old JD')
    legacy = core.job_id_for(j['company'], j['title'], j['location'])
    conn.execute("INSERT INTO jobs (id,company,title,location,req_id,raw_text,parsed_json,status) "
                 "VALUES (?,?,?,?,?,?,?,'shortlisted')", (legacy, 'Acme', 'Engineer', 'Boston', 'R-1', 'Old JD', '{}'))
    conn.execute("INSERT INTO fit (job_id,score,decision) VALUES (?,80,'shortlist')", (legacy,))
    conn.commit()
    assert discover.upsert_jobs(conn, [j | {'raw_text': 'New JD', 'raw_html': '<p>New JD</p>'}], {}, parse=False) == []
    row = core.get_job(conn, legacy)
    assert row['raw_text'] == 'New JD' and row['raw_html'] == '<p>New JD</p>'
    assert row['parsed_json'] is None and row['status'] == 'discovered'
    assert conn.execute('SELECT * FROM fit WHERE job_id=?', (legacy,)).fetchone() is None


def test_board_refresh_uses_requisition_identity(env, monkeypatch):
    conn = core.connect()
    j = dict(company='Acme', title='Engineer', location='Boston', req_id='R-1', source='greenhouse', raw_text='JD')
    [jid] = discover.upsert_jobs(conn, [j], {}, parse=False)
    monkeypatch.setattr(core, 'load_companies', lambda: [{'name': 'Acme', 'ats': 'greenhouse', 'slug': 'acme'}])
    monkeypatch.setattr(discover, 'fetch_board', lambda *args: [j])
    discover.poll_boards(conn, {})
    assert core.get_job(conn, jid)['active'] == 1


def test_ats_url_must_start_at_approved_host():
    assert discover.parse_ats_url('https://evil.example/https://boards.greenhouse.io/acme/jobs/123') is None
    assert discover.parse_ats_url('https://boards.greenhouse.io/acme/jobs/123') == ('greenhouse','acme','123')


def test_branded_greenhouse_urls_retain_a_verifiable_board_identity(monkeypatch):
    payload = {'id': 123, 'requisition_id': 'REQ-7', 'title': 'Robotics Engineer',
               'absolute_url': 'https://careers.example.org/opening?gh_jid=123',
               'location': {'name': 'Boston, MA'}, 'content': '<p>Required: Python.</p>'}
    job = discover._greenhouse_job('acme', payload)
    assert discover.parse_ats_url(job['url']) == ('greenhouse', 'acme', '123')
    assert job['req_id'] == '123'  # public posting ID, not the shared internal requisition
    seen = []

    class Response:
        def json(self):
            return payload

    def fetch(url, **params):
        seen.append(url)
        return Response()

    monkeypatch.setattr(discover, '_get', fetch)
    live = discover.fetch_by_url(job['url'])
    assert seen == ['https://boards-api.greenhouse.io/v1/boards/acme/jobs/123']
    assert live['req_id'] == job['req_id'] and live['raw_text'] == job['raw_text']


def test_checkpoint_invalidates_on_writer_and_check_code_changes(job, env, monkeypatch):
    monkeypatch.setattr(core, 'ROOT', env)
    requested = env / 'requested_changes.md'
    for folder in ('agents', 'checks'):
        (env / folder).mkdir()
    writer = env / 'agents' / 'tailor.py'
    check = env / 'checks' / 'required_content.py'
    writer.write_text('revision = 1\n')
    check.write_text('revision = 1\n')
    key = lambda: pipeline._inputs(job, requested, False, False, False)
    before = key()
    writer.write_text('revision = 2\n')
    changed_writer = key()
    assert changed_writer != before
    check.write_text('revision = 2\n')
    assert key() != changed_writer
    stable = key()
    cache = env / 'agents' / '__pycache__'
    cache.mkdir()
    (cache / 'tailor.pyc').write_bytes(b'compiled cache')
    assert key() == stable


def test_quotes_do_not_accept_empty_evidence(packet):
    conn = core.connect()
    jid = json.loads((packet / 'meta.json').read_text())['job_id']
    conn.execute("INSERT INTO fit (job_id,restrictions_json,decision) VALUES (?,?,'blocked')",
                 (jid, json.dumps([{'type': 'citizenship', 'quote': ''}])))
    conn.commit()
    assert restriction_quotes.check(packet)
    assert not core.quote_in_text('', 'JD')
    assert not core.quote_in_text('Citizens only', 'Citizens? Only some roles.')


def test_eligibility_mentions_are_not_automatic_blocks():
    r = lambda t, q: FitRestriction(type=t, quote=q, note='')
    assert fit.restriction_effect(r('sponsorship', 'Visa sponsorship is available'),
                                  {'needs_sponsorship_now': True}) == 'question'
    assert fit.restriction_effect(r('sponsorship', 'We do not sponsor visas'), {}) == 'question'
    assert fit.restriction_effect(r('citizenship', 'U.S. citizens only'),
                                  {'export_control_eligible': True}) == 'question'


def test_fit_cannot_drop_a_parsed_restriction(job, monkeypatch):
    result = FitResult(score=95, strengths=[], gaps=[], restrictions=[], unknowns=[], questions=[], summary='good')
    monkeypatch.setattr(core, 'llm_json', lambda *a, **k: result)
    profile = core.load_profile()
    profile['authorization']['export_control_eligible'] = 'no'
    scored = fit.score_job(core.connect(), job['id'], profile)
    assert scored['decision'] == 'blocked' and scored['blockers']


def test_fit_rescore_preserves_application_state(job, monkeypatch):
    core.set_status(core.connect(), job['id'], 'interview')
    monkeypatch.setattr(core, 'llm_json', lambda *a, **k: FitResult(
        score=90, strengths=[], gaps=[], restrictions=[], unknowns=[], questions=[], summary='good'))
    fit.score_job(core.connect(), job['id'])
    assert core.get_job(core.connect(), job['id'])['status'] == 'interview'


def test_document_versions_retain_their_bytes(job, tmp_path):
    conn = core.connect()
    path = tmp_path / 'resume.pdf'
    path.write_bytes(b'version one')
    first = core.record_document(conn, job['id'], 'resume', path)
    path.write_bytes(b'version two')
    second = core.record_document(conn, job['id'], 'resume', path)
    assert second != first
    rows = conn.execute('SELECT * FROM documents ORDER BY version').fetchall()
    assert [r['version'] for r in rows] == [1, 2]
    assert [(core.ROOT / r['path']).read_bytes() for r in rows] == [b'version one', b'version two']
    for row in rows:
        assert core.sha256_file(core.ROOT / row['path']) == row['sha256']
    assert core.record_document(conn, job['id'], 'resume', path) == second


def test_recording_an_application_twice_preserves_history(packet):
    jid = json.loads((packet / 'meta.json').read_text())['job_id']
    conn = core.connect()
    core.record_document(conn, jid, 'resume', packet / 'resume.pdf')
    first = tracker.mark_applied(jid)
    tracker.record_outcome(jid, 'interview')
    assert tracker.mark_applied(jid) == first
    assert core.get_job(conn, jid)['status'] == 'interview'
    assert conn.execute("SELECT COUNT(*) FROM actions WHERE action='applied'").fetchone()[0] == 1
    assert conn.execute('SELECT COUNT(*) FROM followups').fetchone()[0] == 1
    tracker.record_outcome(jid, 'rejected')
    assert not tracker.due_followups(conn, on='2099-01-01')


def test_tampered_document_cannot_be_recorded_as_submitted(packet):
    conn = core.connect()
    jid = json.loads((packet / 'meta.json').read_text())['job_id']
    doc_id = core.record_document(conn, jid, 'resume', packet / 'resume.pdf')
    row = conn.execute('SELECT path FROM documents WHERE id=?', (doc_id,)).fetchone()
    (core.ROOT / row['path']).write_bytes(b'changed bytes')
    with pytest.raises(core.JobbotError, match='missing or changed'):
        tracker.mark_applied(jid)
    assert conn.execute('SELECT COUNT(*) FROM actions').fetchone()[0] == 0


def test_manual_review_resumes_the_same_artifacts(job, monkeypatch):
    shortlist(job)
    monkeypatch.setenv('JOBBOT_MODE', 'manual')
    calls = []
    def draft(*args):
        calls.append(args)
        return good_packet()
    monkeypatch.setattr(tailor, 'draft', draft)
    monkeypatch.setattr(tailor, 'unslop', lambda paragraphs, profile: paragraphs)
    with pytest.raises(core.ManualTaskPending) as waiting:
        pipeline.build(job['id'], offline=True, skip_panel=True)
    d = core.job_dir(job['id'])
    before = core.sha256_file(d / 'resume.pdf')
    version = json.loads((d / 'meta.json').read_text())['version']
    assert json.loads((d / 'packet_state.json').read_text())['phase'] == 'review'
    answer = waiting.value.path.with_name(waiting.value.key + '.answer.json')
    answer.write_text(json.dumps({'findings': [], 'overall': 'Ready for human review'}))
    result = pipeline.build(job['id'], offline=True, skip_panel=True)
    assert result['status'] == 'ready_for_review'
    assert len(calls) == 1 and core.sha256_file(d / 'resume.pdf') == before
    assert json.loads((d / 'meta.json').read_text())['version'] == version


def test_panel_revision_limit_requires_human_input(job, monkeypatch):
    shortlist(job)
    monkeypatch.setattr(tailor, 'draft', lambda *args: good_packet())
    monkeypatch.setattr(tailor, 'unslop', lambda paragraphs, profile: paragraphs)
    monkeypatch.setattr(pipeline.review, 'review', lambda *a: type('J', (), {'findings': []})())
    rounds = []
    def reject(conn, jid, d, round_no):
        rounds.append(round_no)
        return {'done': False, 'revisions': ['Improve the evidence description']}
    monkeypatch.setattr(pipeline.panel, 'run', reject)
    result = pipeline.build(job['id'], offline=True)
    assert result['status'] == 'needs_input' and rounds == [1, 2, 3]
    assert 'Review panel still requests' in (core.job_dir(job['id']) / 'open_issues.md').read_text()


def test_panel_stops_without_redrafting_when_only_new_evidence_can_meet_target(job, monkeypatch):
    shortlist(job)
    drafts = []
    monkeypatch.setattr(tailor, 'draft', lambda *args: drafts.append(1) or good_packet())
    monkeypatch.setattr(tailor, 'unslop', lambda paragraphs, profile: paragraphs)
    monkeypatch.setattr(pipeline.review, 'review', lambda *a: type('J', (), {'findings': []})())
    monkeypatch.setattr(pipeline.panel, 'run', lambda *a: {
        'done': False, 'revisions': [], 'plan': {'needs_new_evidence': ['Held-out accuracy']}})
    result = pipeline.build(job['id'], offline=True)
    assert result['status'] == 'needs_input' and drafts == [1]
    assert 'new evidence required: Held-out accuracy' in (core.job_dir(job['id']) / 'open_issues.md').read_text()


def test_daily_run_resumes_drafted_and_reviewed_jobs(job, monkeypatch):
    import run_daily
    conn = shortlist(job)
    monkeypatch.setattr(run_daily.discover, 'run', lambda **k: [])
    monkeypatch.setattr(run_daily.fit, 'run', lambda: [])
    seen = []
    monkeypatch.setattr(run_daily.packet, 'build', lambda jid: seen.append(jid) or
                        {'job_id': jid, 'status': 'waiting_for_claude'})
    for status in ('packet_drafted', 'reviewed'):
        core.set_status(conn, job['id'], status)
        run_daily.main(['--no-web', '--no-alerts'])
    assert seen == [job['id'], job['id']]


def test_latex_pdf_uses_its_own_headings_and_section_order(packet, monkeypatch):
    import typst
    meta = json.loads((packet / 'meta.json').read_text())
    meta['format'] = 'latex'
    (packet / 'meta.json').write_text(json.dumps(meta))
    data = json.loads((packet / 'resume.json').read_text())
    data['experience'][0]['title'] = 'Research Assistant'
    (packet / 'resume.json').write_text(json.dumps(data))
    def compile_pdf(tex):
        pdf = tex.with_suffix('.pdf')
        # Exercise the real PDF parser with LaTeX's actual headings and order.
        typst.compile(bytes('''#set page(paper: "us-letter")
Alex Example #text("alex@example.com")
= EDUCATION
Example Polytechnic Institute
= SKILLS
PyTorch, ROS 2
= RESEARCH  EXPERIENCE
Research Assistant
= PROJECTS
Camera processing
''', 'utf-8'), output=str(pdf))
        return pdf
    monkeypatch.setattr(latex, 'compile_pdf', compile_pdf)
    tailor.render(packet)
    rendered = json.loads((packet / 'resume.json').read_text())
    assert rendered['sections'] == ['education', 'skills', 'experience', 'projects']
    assert rendered['section_headings']['experience'] == 'RESEARCH EXPERIENCE'
    assert ats_parse.check(packet) == []


def test_failed_render_removes_old_pdf(packet, monkeypatch):
    def fail(src):
        raise RuntimeError('renderer failed')
    monkeypatch.setattr(tailor, 'compile_typst', fail)
    with pytest.raises(core.JobbotError, match='renderer failed'):
        tailor.render(packet)
    assert not (packet / 'resume.pdf').exists()


def test_latex_links_cannot_inject_commands(tmp_path):
    link = str(latex._href('https://example.com/}\\input{secret}', 'Code'))
    assert r'\input' not in link and r'\%7D' in link


def test_contacts_require_both_name_and_company(monkeypatch):
    def respond(url):
        return '<p>Alex Example works at Other Company</p>', url
    monkeypatch.setattr(contact_sources, 'public_page', respond)
    assert not contact_sources.page_confirms('https://example.com', 'Alex Example', 'Acme')
    assert contact_sources.page_confirms('https://example.com', 'Alex Example', 'Other Company')


def test_contact_check_skips_its_own_report(tmp_path, monkeypatch):
    d = tmp_path / 'outreach'
    d.mkdir()
    (d / 'checks.json').write_text('{"contact_sources": []}')
    (d / 'alex.json').write_text(json.dumps({'name': 'Alex Example', 'company': 'Acme',
                                            'sources': ['https://a.example', 'https://b.example']}))
    monkeypatch.setattr(contact_sources, 'verified_sources', lambda sources, *a: sources)
    assert contact_sources.check(tmp_path) == []


WEBHOOK = 'https://discord.com/api/webhooks/123/test-token'


def test_discord_network_failure_does_not_leak_secret(monkeypatch, capsys):
    monkeypatch.setenv('DISCORD_WEBHOOK_URL', WEBHOOK)
    def fail(*a, **k):
        raise httpx.ConnectError('failure ' + WEBHOOK)
    monkeypatch.setattr(notify.httpx, 'post', fail)
    assert not notify.post('Update')
    assert 'test-token' not in capsys.readouterr().err


def test_discord_multipart_limits_and_rate_limit(monkeypatch, tmp_path):
    monkeypatch.setenv('DISCORD_WEBHOOK_URL', WEBHOOK + '?thread_id=456')
    file = tmp_path / 'demo.gif'
    file.write_bytes(b'GIF89a')
    requests = []
    def send(url, **kwargs):
        requests.append((url, kwargs, kwargs['files']['files[0]'][1].read()))
        if len(requests) == 1:
            return httpx.Response(429, json={'retry_after': 0})
        return httpx.Response(200, json={'id': '1'})
    monkeypatch.setattr(notify.httpx, 'post', send)
    assert notify.post('t' * 300, 'b' * 4500, fields={str(i) * 256: 'v' * 2000 for i in range(30)}, attachment=file)
    assert len(requests) == 2 and all(r[2] == b'GIF89a' for r in requests)
    url, kwargs, _ = requests[-1]
    assert url.params['wait'] == 'true' and url.params['thread_id'] == '456'
    payload = json.loads(kwargs['data']['payload_json'])
    assert payload['allowed_mentions'] == {'parse': []}
    embed = payload['embeds'][0]
    assert sum(len(f['name']) + len(f['value']) for f in embed['fields']) + len(embed['title']) + len(embed['description']) <= 6000


def test_requisition_artifact_folders_are_separate_before_tailoring(env):
    conn = core.connect()
    base = dict(company='Acme', title='Engineer', location='Boston', source='greenhouse', raw_text='JD')
    ids = discover.upsert_jobs(conn, [base | {'req_id': 'R-1'}, base | {'req_id': 'R-2'}], {}, parse=False)
    a = core.job_dir(ids[0], conn)
    (a / 'gaps.md').write_text('First requisition')
    b = core.job_dir(ids[1], conn)
    assert a != b and core.job_dir(ids[0], conn) == a
    assert (a / 'gaps.md').read_text() == 'First requisition'
    assert not (b / 'gaps.md').exists()


def test_answer_bank_values_cannot_be_reversed(job):
    data = good_packet()
    data.answers[1].answer = 'A made-up identity'
    data.answers[1].fact_ids = ['F003']
    result = tailor.enforce(data, core.load_profile(), job['id'], [])
    assert result['answers'][1]['answer'] == 'Decline to answer'
    data.answers[0].fact_ids = ['F999']
    result = tailor.enforce(data, core.load_profile(), job['id'], [])
    assert result['answers'][0]['need_input']


def test_manual_mode_completes_real_review_and_panel(job, monkeypatch):
    from tests.test_ats_panel_master import _reviews, _plan
    shortlist(job)
    monkeypatch.setenv('JOBBOT_MODE', 'manual')
    calls = []
    def draft(*args):
        calls.append(args)
        return good_packet()
    monkeypatch.setattr(tailor, 'draft', draft)
    monkeypatch.setattr(tailor, 'unslop', lambda paragraphs, profile: paragraphs)
    reviews = _reviews()
    answers = {type(v).__name__: v.model_dump() for v in reviews.values()}
    answers['LeadJudgment'] = {'findings': [], 'overall': 'Ready for human review'}
    answers['RevisionPlan'] = _plan(revisions=0, bulletproof=True).model_dump()
    for _ in range(5):
        try:
            result = pipeline.build(job['id'], offline=True)
            break
        except core.ManualTaskPending:
            for task in core.pending_tasks():
                schema = task.read_text().splitlines()[0].split(' -> ')[-1]
                key = task.name.removesuffix('.task.md')
                task.with_name(key + '.answer.json').write_text(json.dumps(answers[schema]))
    else:
        pytest.fail('Manual review/panel did not converge after answering all queued tasks')
    assert result['status'] == 'ready_for_review' and len(calls) == 1
    state = json.loads((core.job_dir(job['id']) / 'packet_state.json').read_text())
    assert state['phase'] == 'complete' and state['panel_round'] == 1


def test_packet_cannot_omit_required_letter_or_question(packet):
    from checks import required_content
    jid = json.loads((packet / 'meta.json').read_text())['job_id']
    conn = core.connect()
    parsed = {'cover_letter_requested': True, 'application_questions': ['Why robotics?', 'When can you start?']}
    conn.execute('UPDATE jobs SET parsed_json=? WHERE id=?', (json.dumps(parsed),jid))
    conn.commit()
    (packet / 'cover_letter.md').unlink()
    bad = required_content.check(packet)
    assert any('cover letter' in p for p in bad)
    assert any('When can you start?' in p for p in bad)
    assert not any('Why robotics?' in p for p in bad)


def test_mark_applied_cannot_select_an_old_draft(packet):
    conn = core.connect()
    jid = json.loads((packet / 'meta.json').read_text())['job_id']
    core.record_document(conn, jid, 'resume', packet / 'resume.pdf')
    (packet / 'resume.pdf').write_bytes(b'new unrecorded draft')
    with pytest.raises(core.JobbotError, match='differs from the recorded'):
        tracker.mark_applied(jid)
    assert conn.execute('SELECT COUNT(*) FROM actions').fetchone()[0] == 0
