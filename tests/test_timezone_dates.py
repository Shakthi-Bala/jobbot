import pytest
from agents import core, sheet, tracker


def test_tomorrow_in_utc_can_be_today_in_candidate_timezone(job, monkeypatch):
    monkeypatch.setattr(core, 'today', lambda: '2026-11-16')
    tracker.mark_applied(job['id'], applied_on='2026-11-17')
    conn = core.connect()
    assert conn.execute("SELECT at FROM actions WHERE action='applied'").fetchone()[0] == '2026-11-17'
    assert conn.execute('SELECT due FROM followups').fetchone()[0] == '2026-11-27'


def test_more_than_one_day_ahead_is_rejected(job, monkeypatch):
    monkeypatch.setattr(core, 'today', lambda: '2026-11-16')
    with pytest.raises(core.JobbotError, match='future'):
        tracker.mark_applied(job['id'], applied_on='2026-11-18')
    assert core.connect().execute('SELECT COUNT(*) FROM actions').fetchone()[0] == 0


def test_whitespace_only_application_date_is_blank(job, monkeypatch):
    calls = []
    monkeypatch.setattr(tracker, 'mark_applied', lambda job_id, **kwargs: calls.append(kwargs))
    errors = {}
    assert sheet.apply_edits(core.connect(), {job['id']: {'applied': 'Yes', 'date_applied': '  \t '}}, errors) == [job['id']]
    assert calls == [{}] and errors == {}
