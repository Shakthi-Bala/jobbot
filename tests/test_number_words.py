"""Quantitative prose must retain numerical and unit provenance."""
import pytest
from agents import core
from checks import numbers_match
from checks._lib import numbers, quantities


@pytest.mark.parametrize('text,value', [('zero', 0), ('point five', 0.5), ('zero point five', 0.5),
    ('twenty-four point zero five', 24.05), ('ten', 10), ('twenty-four', 24),
    ('one hundred and twenty-five', 125), ('two thousand and six', 2006),
    ('a hundred', 100), ('two million three hundred thousand five', 2300005)])
def test_cardinal_numbers(text, value):
    assert numbers(text) == {value}


@pytest.mark.parametrize('text,expected', [
    ('twenty-four-millisecond', {(24, 'ms')}), ('72-percent', {(72, '%')}),
    ('twenty-four frames-per-second', {(24, 'fps')}), ('24‑ms', {(24, 'ms')}),
    ('ten-percentage-points', {(10, 'percentage point')}),
    ('zero point five-percent', {(0.5, '%')}),
    ('ten hertz', {(10, 'hz')}), ('two times', {(2, 'factor')})])
def test_hyphenated_quantities(text, expected):
    assert quantities(text) == expected


@pytest.mark.parametrize('claim', ['Led ten engineers', 'Evaluated one thousand scenes',
                                  'Achieved twenty-four-percent accuracy', 'Measured 24-ms latency'])
def test_unsupported_spelled_numbers_and_changed_units_fail(env, tmp_path, claim):
    (tmp_path / 'resume.tagged.md').write_text(f'- {claim} [F003]')
    assert numbers_match.check(tmp_path)


def test_supported_spelling_and_unit_paraphrases_pass(env, tmp_path):
    (tmp_path / 'resume.tagged.md').write_text(
        '- Ran at twenty-four frames-per-second [F003]\n'
        '- Achieved seventy-two-percent validation mIoU [F002]\n')
    assert numbers_match.check(tmp_path) == []


def test_spelled_source_supports_numeric_claim(env, tmp_path, monkeypatch):
    profile = core.load_profile()
    profile['facts'].append({'id': 'F099', 'text': 'Evaluated ten scenes at twenty milliseconds'})
    monkeypatch.setattr(core, 'load_profile', lambda: profile)
    (tmp_path / 'resume.tagged.md').write_text('- Evaluated 10 scenes at 20-ms latency [F099]')
    assert numbers_match.check(tmp_path) == []


def test_decimal_words_do_not_borrow_separate_source_numbers(env, tmp_path, monkeypatch):
    profile = core.load_profile()
    profile['facts'].append({'id': 'F099', 'text': 'Measured 0% drift and 5% depth error'})
    monkeypatch.setattr(core, 'load_profile', lambda: profile)
    (tmp_path / 'resume.tagged.md').write_text('- Measured zero point five-percent error [F099]')
    assert numbers_match.check(tmp_path)


@pytest.mark.parametrize('wording', ['one of the core developers', 'no one else',
    'one-hot encoding', 'zero-copy transport', 'zero‑shot classification'])
def test_nonnumeric_idioms_do_not_fail_provenance(env, tmp_path, wording):
    (tmp_path / 'resume.tagged.md').write_text(f'- Implemented {wording} [F004]')
    assert numbers_match.check(tmp_path) == []
    assert numbers(wording) == set()


def test_idioms_do_not_hide_nearby_quantities():
    assert numbers('one of twenty-one engineers used zero-copy at 24 FPS') == {21, 24}
    assert numbers('zero errors across one scene') == {0, 1}
