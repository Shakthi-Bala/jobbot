"""Additional phrasing must retain the quantity and its kind of evidence."""
import pytest
from agents import core
from checks import numbers_match
from checks._lib import numbers, quantities


@pytest.mark.parametrize('text', ['six-degree-of-freedom arm', '6 degrees of freedom',
    'six degrees-of-freedom', '6-DOF arm'])
def test_robotics_freedom_is_not_an_angle(text):
    assert quantities(text, contextual=True) == {(6, 'dof')}


@pytest.mark.parametrize('text', ['half-dozen robots', 'half a dozen robots',
    'half-a-dozen robots', 'half of a dozen robots'])
def test_fractional_dozen(text):
    assert numbers(text, contextual=True) == {6}
    assert quantities(text, contextual=True) == {(6, 'count:robot')}


@pytest.mark.parametrize('text,value', [('top-three finish', 3),
    ('placed first among 400 teams', 1), ('top-twelve finish', 12),
    ('ranked fourth in the competition', 4), ('third-place finish', 3)])
def test_rank_has_a_unit(text, value):
    assert (value, 'rank') in quantities(text, contextual=True)


@pytest.mark.parametrize('text,value', [('ninety-five on the leaderboard', 95),
    ('scored seventy-two overall', 72), ('two hundred and seven overall', 207)])
def test_nounless_cardinal_is_still_a_claim(text, value):
    assert value in numbers(text, contextual=True)


@pytest.mark.parametrize('claim,source', [
    ('Built a six-degree-of-freedom arm', 'Built a 6-DOF arm'),
    ('Led half-a-dozen robots', 'Led 6 robots'),
    ('Achieved a top-three finish', 'Won third place'),
    ('Placed first among 400 teams', 'Won first place among 400 teams'),
    ('Scored ninety-five overall', 'Scored 95 overall')])
def test_supported_paraphrases(env, tmp_path, monkeypatch, claim, source):
    profile = core.load_profile()
    profile['facts'].append({'id': 'F099', 'text': source})
    monkeypatch.setattr(core, 'load_profile', lambda: profile)
    (tmp_path / 'resume.tagged.md').write_text(f'- {claim} [F099]\n')
    assert numbers_match.check(tmp_path) == []


@pytest.mark.parametrize('claim,source', [
    ('Rotated by six degrees', 'Programmed a 6-DOF arm'),
    ('Programmed a 6-DOF arm', 'Rotated by six degrees'),
    ('Achieved a top-three finish', 'Completed 3 projects'),
    ('Placed first among 400 teams', 'Built 1 robot for 400 teams'),
    ('Led half a dozen robots', 'Led 12 robots'),
    ('Scored ninety-five on the leaderboard', 'Built a perception pipeline')])
def test_unrelated_or_missing_evidence_fails(env, tmp_path, monkeypatch, claim, source):
    profile = core.load_profile()
    profile['facts'].append({'id': 'F099', 'text': source})
    monkeypatch.setattr(core, 'load_profile', lambda: profile)
    (tmp_path / 'resume.tagged.md').write_text(f'- {claim} [F099]\n')
    assert numbers_match.check(tmp_path)


@pytest.mark.parametrize('text,value', [('Ranked 2nd of 60 teams', 2),
    ('Placed 4th in the competition', 4), ('Finished fourth of 60 teams', 4),
    ('fourth among 60 teams', 4), ('4th of 60 teams', 4)])
def test_ordinal_rank_context_has_a_rank_unit(text, value):
    assert (value, 'rank') in quantities(text, contextual=True)


def test_cardinal_subset_is_not_a_rank():
    assert (2, 'rank') not in quantities('Completed 2 of 60 tests', contextual=True)
