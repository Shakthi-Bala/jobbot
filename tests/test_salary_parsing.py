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


@pytest.mark.parametrize('text', ['Salary paid monthly $120,000 - $150,000',
                                 '$120,000-$150,000 per month'])
def test_annual_sized_amounts_are_not_multiplied_by_payment_cadence(text):
    assert core.parse_pay_text(text) == (120000, 150000)


@pytest.mark.parametrize('text', [
    'Salary $120,000-$150,000; $2,000-$3,000 per month housing stipend',
    '$2,000-$3,000 per month housing stipend; Salary $120,000-$150,000',
    'Base salary $120,000-$150,000 plus housing stipend $2,000-$3,000 per month'])
def test_stipends_do_not_widen_base_salary_range(text):
    assert core.parse_pay_text(text) == (120000, 150000)


@pytest.mark.parametrize('suffix', ['M&A focus', 'B.S. required'])
def test_degree_and_merger_labels_are_not_funding(suffix):
    assert core.parse_pay_text(f'Salary $90,000-$110,000 {suffix}') == (90000, 110000)


def test_a_stipend_alone_is_not_base_salary():
    assert core.parse_pay_text('$2,000-$3,000 per month housing stipend') is None
