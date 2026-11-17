import pytest
from agents import discover


@pytest.mark.parametrize('currency', ['CAD', 'AUD', 'EUR'])
def test_lever_foreign_board_pay_is_not_relabelled_usd(currency):
    job = discover._lever_job('example', {'id': 'one', 'text': 'Engineer',
        'descriptionPlain': 'Base salary $100,000-$150,000',
        'salaryRange': {'min': 100000, 'max': 150000, 'currency': currency, 'interval': 'year'}})
    assert job['comp_max'] is None and job['comp_currency'] is None


def test_ashby_foreign_board_pay_is_not_relabelled_usd():
    job = discover._ashby_job('example', {'id': 'one', 'title': 'Engineer',
        'descriptionPlain': 'Base salary $100,000-$150,000',
        'compensation': {'summaryComponents': [{'compensationType': 'Salary', 'minValue': 100000,
            'maxValue': 150000, 'currencyCode': 'CAD', 'interval': 'YEAR'}]}})
    assert job['comp_max'] is None and job['comp_currency'] is None


def test_foreign_hint_still_allows_an_explicit_usd_range():
    pay = discover._pay_from_text('CAD $100,000-$120,000; USD $90,000-$110,000', currency_hint='CAD')
    assert (pay['comp_min'], pay['comp_max'], pay['comp_currency']) == (90000, 110000, 'USD')
