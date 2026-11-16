from agents import core, discover


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
