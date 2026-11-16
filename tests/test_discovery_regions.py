import pytest
from agents import core, discover


def test_greenhouse_eu_keeps_regional_api_and_public_url(monkeypatch):
    calls = []
    class Response:
        def json(self):
            return {'id': 123, 'title': 'Engineer', 'content': 'Synthetic posting'}
    monkeypatch.setattr(discover, '_get', lambda url, **kw: calls.append(url) or Response())
    job = discover.fetch_by_url('https://job-boards.eu.greenhouse.io/example/jobs/123')
    assert calls == ['https://boards-api.eu.greenhouse.io/v1/boards/example/jobs/123']
    assert job['url'] == 'https://job-boards.eu.greenhouse.io/example/jobs/123'


@pytest.mark.parametrize('error', [ValueError, KeyError, TypeError])
def test_ingest_bad_board_data_does_not_stop_later_urls(env, monkeypatch, error):
    urls = ['https://boards.greenhouse.io/example/jobs/1', 'https://boards.greenhouse.io/example/jobs/2']
    def fetch(url):
        if url == urls[0]:
            raise error('bad response')
        return discover._greenhouse_job('example', {'id': 2, 'title': 'Engineer', 'content': 'JD'})
    monkeypatch.setattr(discover, 'fetch_by_url', fetch)
    monkeypatch.setattr(discover, 'parse_posting', lambda *a: (_ for _ in ()).throw(core.ManualTaskPending('x', core.OUT / 'x')))
    assert len(discover.ingest_urls(core.connect(), urls, {}, 'web')) == 1


def test_same_named_boards_do_not_deactivate_each_other(env, monkeypatch):
    conn = core.connect()
    for slug, jid in [('alpha', 1), ('beta', 2)]:
        job = discover._greenhouse_job(slug, {'id': jid, 'title': 'Engineer', 'content': 'JD'})
        discover.upsert_jobs(conn, [job | {'company': 'Same Name'}], {}, parse=False)
    monkeypatch.setattr(core, 'load_companies', lambda: [
        {'name': 'Same Name', 'ats': 'greenhouse', 'slug': slug} for slug in ['alpha', 'beta']])
    monkeypatch.setattr(discover, 'fetch_board', lambda *a: [])
    # Poll only alpha: beta must remain active.
    ids = {row['req_id']: row['id'] for row in conn.execute('SELECT * FROM jobs')}
    assert discover.mark_missing_inactive(conn, 'Same Name', set(), ('greenhouse', 'alpha', 'us')) == 1
    assert core.get_job(conn, ids['1'])['active'] == 0
    assert core.get_job(conn, ids['2'])['active'] == 1
