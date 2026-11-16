import pytest
from agents import core, tracker


def test_read_only_packet_lookup_does_not_create_folders(job):
    assert list(core.OUT.iterdir()) == []
    path = core.job_dir(job['id'], create=False)
    assert not path.exists() and list(core.OUT.iterdir()) == []


@pytest.mark.parametrize('status', tracker.OUTCOMES)
def test_dashboard_draft_actions_preserve_recorded_status(job, status):
    conn = core.connect()
    core.set_status(conn, job['id'], status)
    for changes in (None, 'Rewrite the first bullet'):
        with pytest.raises(core.JobbotError, match='history is recorded'):
            tracker.edit_draft(job['id'], changes=changes)
    assert core.get_job(conn, job['id'])['status'] == status
    assert not core.job_dir(job['id'], create=False).exists()


def test_dashboard_checks_history_even_if_page_status_is_stale(job):
    conn = core.connect()
    core.record_action(conn, job['id'], 'me', 'applied')
    with pytest.raises(core.JobbotError):
        tracker.edit_draft(job['id'])


def test_dashboard_can_request_changes_to_an_unsubmitted_draft(job):
    tracker.edit_draft(job['id'], changes='Use the measured baseline')
    assert core.get_job(core.connect(), job['id'])['status'] == 'shortlisted'
    assert (core.job_dir(job['id'], create=False) / 'requested_changes.md').read_text().strip() == 'Use the measured baseline'


@pytest.mark.parametrize('status', ['responded', 'interview', 'rejected', 'offer', 'closed'])
def test_mark_applied_cannot_regress_an_outcome_from_a_stale_dashboard(job, status):
    conn = core.connect()
    core.set_status(conn, job['id'], status)
    with pytest.raises(core.JobbotError, match='cannot overwrite'):
        tracker.mark_applied(job['id'])
    assert core.get_job(conn, job['id'])['status'] == status
    assert conn.execute('SELECT COUNT(*) FROM actions').fetchone()[0] == 0
