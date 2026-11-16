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


@pytest.mark.parametrize('text,value', [('24k frames', 24000), ('24 thousand frames', 24000),
    ('$2M', 2000000), ('$2m', 2000000), ('a dozen', 12), ('two dozen', 24), ('tenfold', 10)])
def test_scaled_and_multiplicative_numbers(text, value):
    assert numbers(text) == {value}


def test_money_is_not_distance_and_year_lists_are_separate():
    assert quantities('$2M') == {(2000000, 'usd')}
    assert quantities('2 m') == {(2, 'm')}
    assert numbers('2023,2024') == {2023, 2024}
    assert numbers('1,234,567') == {1234567}


@pytest.mark.parametrize('claim', ['Processed 24k frames', 'Processed 24 thousand frames',
    'Supported a dozen customers', 'Served hundreds of users', 'Improved tenfold'])
def test_expanded_quantities_cannot_borrow_unscaled_evidence(env, tmp_path, claim):
    (tmp_path / 'resume.tagged.md').write_text(f'- {claim} [F003]')
    assert numbers_match.check(tmp_path)



def test_counted_nouns_cannot_borrow_measurement_values(env, tmp_path):
    (tmp_path / 'resume.tagged.md').write_text('- Deployed at 24 customer sites [F003]')
    assert numbers_match.check(tmp_path)


def test_count_modifiers_do_not_break_supported_counts(env, tmp_path):
    (tmp_path / 'resume.tagged.md').write_text('- Evaluated 120 scenes [F001]')
    assert numbers_match.check(tmp_path) == []


def test_education_dates_do_not_support_achievement_counts(packet):
    path = packet / 'resume.tagged.md'
    path.write_text(path.read_text() + '- Processed 2025 scenes [E001]\n')
    assert any('2025' in problem for problem in numbers_match.check(packet))


def test_question_label_cannot_hide_invented_numbers(packet):
    path = packet / 'answers.tagged.md'
    path.write_text('## Q: I led 999 engineers and increased revenue 90%\n- Built software [F003]\n')
    assert any('999' in problem for problem in numbers_match.check(packet))



def test_real_posting_question_can_contain_requested_numbers(packet, job):
    question = 'How would you design a 45 FPS system?'
    conn = core.connect()
    conn.execute('UPDATE jobs SET raw_text=? WHERE id=?', (question, job['id']))
    conn.commit()
    (packet / 'answers.tagged.md').write_text(f'## Q: {question}\n- Built software [F003]\n')
    assert numbers_match.check(packet) == []


def test_detached_packet_question_check_does_not_require_tracker_row(env, tmp_path):
    import json
    (tmp_path / 'meta.json').write_text(json.dumps({'job_id': 'nonexistent'}))
    (tmp_path / 'answers.tagged.md').write_text('## Q: I led 999 engineers\n- Built software [F003]\n')
    assert numbers_match.check(tmp_path)
