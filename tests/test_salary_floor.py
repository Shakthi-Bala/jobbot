"""A disclosed zero ceiling is different from an undisclosed salary."""
import pytest
from agents import core, discover


@pytest.mark.parametrize('ceiling,accepted', [(None, True), (0, False), (79999, False),
                                            (80000, True), (150000, True)])
def test_salary_floor_distinguishes_unknown_from_zero(env, ceiling, accepted):
    job = {'company': 'Example', 'title': 'Engineer', 'location': '', 'source': 'manual',
           'raw_text': 'Synthetic posting', 'raw_html': ''} | discover._pay(None, ceiling, '', 'ats')
    conn = core.connect()
    ids = discover.upsert_jobs(conn, [job], {}, parse=False, min_pay=80000)
    assert bool(ids) is accepted
    assert conn.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] == int(accepted)


@pytest.mark.parametrize('maximum', [0, 150000])
def test_ats_salary_endpoints_preserve_zero_and_missing_lower_bound(maximum):
    lever = discover._lever_job('example', {'id': '1', 'text': 'Engineer', 'salaryRange': {
        'min': None, 'max': maximum, 'currency': 'USD', 'interval': 'year'}})
    ashby = discover._ashby_job('example', {'id': '2', 'title': 'Engineer', 'compensation': {
        'summaryComponents': [{'compensationType': 'Salary', 'minValue': None,
                               'maxValue': maximum, 'currencyCode': 'USD', 'interval': 'YEAR'}]}})
    for job in (lever, ashby):
        assert job['comp_min'] is None
        assert job['comp_max'] == (maximum or None)


@pytest.mark.parametrize('lo,hi', [(90000, 0), (150000, 90000), (-1, 100000), (None, float('nan'))])
def test_invalid_board_pay_falls_back_to_posting_text(lo, hi):
    pay = discover._board_pay(lo, hi, 'YEAR', '', 'Salary $90,000-$110,000 m/w/d')
    assert (pay['comp_min'], pay['comp_max'], pay['comp_source']) == (90000, 110000, 'text')


def test_monthly_board_pay_and_genuine_zero_lower_bound():
    assert discover._board_pay(0, 10000, 'MONTH', '', '')['comp_max'] == 120000
    assert discover._board_pay(0, 10000, 'MONTH', '', '')['comp_min'] == 0
