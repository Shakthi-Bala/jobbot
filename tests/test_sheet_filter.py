"""Refreshing a workbook respects job status without losing candidate inputs."""
import pytest
from openpyxl import load_workbook
from agents import core, sheet, tracker


@pytest.mark.parametrize('status', ['skipped', 'blocked', 'closed'])
def test_refresh_filters_old_rows_and_restores_notes_when_reopened(packet, job, tmp_path, status):
    path = tmp_path / 'applications.xlsx'
    assert sheet.build(path)['rows'] == 1
    wb = load_workbook(path)
    wb['Applications'].cell(sheet.FIRST_ROW, sheet.COL['notes']).value = 'Keep my referral note'
    wb.save(path)
    conn = core.connect()
    core.set_status(conn, job['id'], status)
    for _ in range(2):
        assert sheet.build(path)['rows'] == 0
        assert sheet.read_user_edits(path)[job['id']]['notes'] == 'Keep my referral note'
        assert load_workbook(path)[sheet.SAVED_EDITS_SHEET].sheet_state == 'hidden'
    core.set_status(conn, job['id'], 'shortlisted')
    assert sheet.build(path)['rows'] == 1
    assert load_workbook(path)['Applications'].cell(
        sheet.FIRST_ROW, sheet.COL['notes']).value == 'Keep my referral note'


def test_failed_applied_edit_remains_visible_for_correction(packet, job, tmp_path, monkeypatch):
    path = tmp_path / 'applications.xlsx'
    sheet.build(path)
    wb = load_workbook(path)
    wb['Applications'].cell(sheet.FIRST_ROW, sheet.COL['applied']).value = 'Yes'
    wb.save(path)
    core.set_status(core.connect(), job['id'], 'closed')
    def fail(job_id):
        raise core.JobbotError('Cannot verify saved document')
    monkeypatch.setattr(tracker, 'mark_applied', fail)
    result = sheet.build(path)
    assert result['rows'] == 1 and job['id'] in result['errors']
    assert sheet.read_user_edits(path)[job['id']]['applied'] == 'Yes'



def test_sheet_collection_does_not_create_job_directories(job):
    d = core.job_dir(job['id'], create=False)
    assert not d.exists()
    assert sheet.collect(core.connect()) == []
    assert not d.exists()


@pytest.mark.parametrize('value', ['2025-10-01', __import__('datetime').datetime(2025, 10, 1)])
def test_date_applied_controls_action_and_followup(job, value):
    conn = core.connect()
    assert sheet.apply_edits(conn, {job['id']: {'applied': 'Yes', 'date_applied': value}}) == [job['id']]
    assert conn.execute("SELECT at FROM actions WHERE action='applied'").fetchone()[0] == '2025-10-01'
    assert conn.execute('SELECT due FROM followups').fetchone()[0] == '2025-10-11'


def test_invalid_applied_date_is_reported_without_recording(job, capsys):
    errors = {}
    conn = core.connect()
    assert sheet.apply_edits(conn, {job['id']: {'applied': 'Yes', 'date_applied': 'yesterday'}}, errors) == []
    assert job['id'] in errors
    assert 'Date applied' in capsys.readouterr().err
    assert conn.execute('SELECT COUNT(*) FROM actions').fetchone()[0] == 0
