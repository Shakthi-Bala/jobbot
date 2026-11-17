"""Currency and excluded benefits belong to their own compensation range."""
import pytest
from agents import core


@pytest.mark.parametrize('currency', ['CAD', 'AUD', 'EUR', 'GBP', 'SGD'])
@pytest.mark.parametrize('text', ['$150,000 - $180,000 ({currency})',
    '{currency}: $150,000 - $180,000', 'Toronto ({currency}): $150,000 - $180,000',
    'Toronto [{currency}]: base salary $150,000 - $180,000',
    '150,000 - 180,000 ({currency})', '150,000 - 180,000 {currency}'])
def test_explicit_foreign_currency_is_not_usd(currency, text):
    assert core.parse_pay_text(text.format(currency=currency)) is None


@pytest.mark.parametrize('foreign', ['Toronto (CAD): $110,000 - $140,000',
    '$110,000 - $140,000 (CAD)', '110,000 - 140,000 CAD'])
@pytest.mark.parametrize('foreign_first', [True, False])
def test_foreign_range_does_not_widen_us_base(foreign, foreign_first):
    us = 'US: $160,000 - $205,000'
    text = '; '.join([foreign, us] if foreign_first else [us, foreign])
    assert core.parse_pay_text(text) == (160000, 205000)


@pytest.mark.parametrize('text,expected', [
    ('$150,000 - $200,000 excluding bonus and equity', (150000, 200000)),
    ('$125,000 - $175,000 exclusive of stock and bonus', (125000, 175000)),
    ('$130,000 - $190,000 not including bonus', (130000, 190000)),
    ('$110,000 - $170,000 without equity', (110000, 170000)),
    ('120,000 - 150,000 USD', (120000, 150000)),
    ('120 - 150k USD', (120000, 150000)),
    ('120,000 - 150,000 (USD)', (120000, 150000)),
    ('120,000 - 150,000 [USD]', (120000, 150000)),
    ('8,000 - 10,000 USD per month', (96000, 120000)),
    ('$120,000 - $150,000 (USD)', (120000, 150000)),
    ('$120,000 - $150,000 (CAD); 155,000 - 190,000 USD', (155000, 190000)),
    ('US: $160,000-$205,000\nCAD: $110,000-$140,000', (160000, 205000)),
    ('CAD: $110,000-$140,000\nUSD: $160,000-$205,000', (160000, 205000)),
    ('Bonus 20,000 - 30,000 USD; 140,000 - 180,000 USD excluding equity', (140000, 180000)),
    ('120,000 - 150,000', None),
    ('Bonus $20,000 - $30,000 excluding equity', None),
    ('120,000 - 150,000 USD total compensation', None),
    ('$150,000 - $200,000 including bonus and equity', None),
    ('$120,000 - $150,000 USD (CAD)', None)])
def test_range_edges(text, expected):
    assert core.parse_pay_text(text) == expected


def test_trailing_usd_overrides_foreign_board_default():
    assert core.parse_pay_text('120,000 - 150,000 USD', default_currency='CAD') == (120000, 150000)
