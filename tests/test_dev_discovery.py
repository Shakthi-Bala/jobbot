from agents import core, discover
import pytest


def greenhouse(posting_id, location):
    return discover._greenhouse_job('acme', {
        'id': posting_id, 'title': 'Engineer', 'requisition_id': 'SHARED-REQ',
        'internal_job_id': 99, 'location': {'name': location},
        'content': f'<p>Engineer in {location}</p>'})


def test_greenhouse_location_variants_keep_their_identity_and_fit(env):
    conn = core.connect()
    postings = [greenhouse(101, 'Boston'), greenhouse(102, 'Seattle')]
    ids = discover.upsert_jobs(conn, postings, {}, parse=False)
    assert len(set(ids)) == 2
    for jid in ids:
        conn.execute("INSERT INTO fit(job_id,score,decision) VALUES (?,85,'shortlist')", (jid,))
        core.set_status(conn, jid, 'shortlisted')
    for _ in range(2):
        assert discover.upsert_jobs(conn, reversed(postings), {}, parse=False) == []
    assert conn.execute('SELECT COUNT(*) FROM fit').fetchone()[0] == 2
    assert [core.get_job(conn, jid)['status'] for jid in ids] == ['shortlisted'] * 2
    assert {core.get_job(conn, jid)['location'] for jid in ids} == {'Boston', 'Seattle'}


def test_greenhouse_migration_preserves_application_history(env):
    conn = core.connect()
    old = greenhouse(101, 'Boston') | {'req_id': 'SHARED-REQ'}
    [jid] = discover.upsert_jobs(conn, [old], {}, parse=False)
    core.set_status(conn, jid, 'interview')
    core.record_action(conn, jid, 'me', 'interview', 'screen scheduled')
    ids = discover.upsert_jobs(conn, [greenhouse(101, 'Boston'), greenhouse(102, 'Seattle')], {}, parse=False)
    assert len(ids) == 1 and ids[0] != jid
    original = core.get_job(conn, jid)
    assert original['req_id'] == '101' and original['status'] == 'interview'
    assert conn.execute('SELECT job_id FROM actions').fetchone()[0] == jid


def test_lever_missing_lower_salary_can_be_listed(env, capsys):
    import jobbot
    job = discover._lever_job('acme', {
        'id': 'lever-1', 'text': 'Engineer', 'salaryRange': {
            'min': None, 'max': 175000, 'currency': 'USD', 'interval': 'year'}})
    assert job['comp_min'] is None and job['comp_max'] == 175000
    [jid] = discover.upsert_jobs(core.connect(), [job], {}, parse=False)
    jobbot._print_jobs([jid])
    assert 'up to $175K' in capsys.readouterr().out


@pytest.mark.parametrize('text', ['$120-150K', '$120K - 150K', '$120K to $150K'])
def test_shared_salary_units(text):
    assert core.parse_pay_text(text) == (120000, 150000)


def test_bad_board_does_not_stop_other_companies(env, monkeypatch):
    monkeypatch.setattr(core, 'load_companies', lambda: [
        {'name': 'Broken', 'ats': 'lever', 'slug': 'bad'},
        {'name': 'Good', 'ats': 'greenhouse', 'slug': 'good'}])
    def fetch(ats, slug):
        if slug == 'bad':
            raise ValueError('malformed board data')
        return [greenhouse(103, 'Boston')]
    monkeypatch.setattr(discover, 'fetch_board', fetch)
    monkeypatch.setattr(discover, 'parse_posting', lambda *a: (_ for _ in ()).throw(core.JobbotError('unavailable')))
    ids = discover.poll_boards(core.connect(), {})
    assert len(ids) == 1
    assert core.get_job(core.connect(), ids[0])['company'] == 'Good'


def test_rediscovery_reopens_only_automatic_closures(env):
    conn = core.connect()
    auto, manual = greenhouse(101, 'Boston'), greenhouse(102, 'Seattle')
    ids = discover.upsert_jobs(conn, [auto, manual], {}, parse=False)
    for jid in ids:
        conn.execute("UPDATE jobs SET active=0,status='closed' WHERE id=?", (jid,))
    core.record_action(conn, ids[1], 'me', 'closed', 'no longer pursuing')
    discover.upsert_jobs(conn, [auto, manual], {}, parse=False)
    assert core.get_job(conn, ids[0])['status'] == 'discovered'
    assert core.get_job(conn, ids[0])['active'] == 1
    assert core.get_job(conn, ids[1])['status'] == 'closed'


def test_packet_can_recheck_an_automatically_closed_posting(env, monkeypatch):
    from agents import packet
    conn = core.connect()
    job = greenhouse(101, 'Boston')
    [jid] = discover.upsert_jobs(conn, [job], {}, parse=False)
    conn.execute("UPDATE jobs SET active=0,status='closed' WHERE id=?", (jid,))
    conn.commit()
    monkeypatch.setattr(discover, 'fetch_by_url', lambda url: job)
    monkeypatch.setenv('JOBBOT_MODE', 'manual')
    with pytest.raises(core.ManualTaskPending):
        packet.build(jid)
    assert core.get_job(conn, jid)['active'] == 1
    assert core.get_job(conn, jid)['status'] != 'closed'
