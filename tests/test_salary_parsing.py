import pytest
from agents import core


@pytest.mark.parametrize('suffix', ['m/w/d', 'M-F', 'm-f', 'USD m/w/d'])
def test_employment_labels_are_not_million_multipliers(suffix):
    assert core.parse_pay_text(f'Salary $90,000 - $110,000 {suffix}') == (90000, 110000)


@pytest.mark.parametrize('suffix', ['mm', 'mil', 'million', 'M', 'B', 'billion'])
def test_funding_shorthand_is_not_salary(suffix):
    assert core.parse_pay_text(f'Raised $10-20{suffix}') is None


@pytest.mark.parametrize('text', ['$8,000-$10,000 per month', '$8000-10000/month',
                                 'Monthly salary: $8000-10000', '$8000-10000 monthly'])
def test_monthly_salary_is_annualized(text):
    assert core.parse_pay_text(text) == (96000, 120000)
