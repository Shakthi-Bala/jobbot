import pytest
from agents import core
from checks import numbers_match


@pytest.mark.parametrize('claim', ['Wrote one regression case per category', 'Processed one at a time',
    'Implemented a one-stage detector', 'Two projects show how I work'])
def test_honest_nonmeasurement_wording_passes(env, tmp_path, claim):
    (tmp_path / 'resume.tagged.md').write_text(f'- {claim} [F004]')
    assert numbers_match.check(tmp_path) == []


@pytest.mark.parametrize('tool', ['Python 3', 'OpenCV 4', 'CUDA 12'])
def test_verified_tool_version_is_not_a_measurement(env, tmp_path, monkeypatch, tool):
    profile = core.load_profile()
    profile['facts'].append({'id': 'F099', 'text': 'Ported Python, OpenCV and CUDA workflows'})
    monkeypatch.setattr(core, 'load_profile', lambda: profile)
    (tmp_path / 'resume.tagged.md').write_text(f'- Ported to {tool} [F099]')
    assert numbers_match.check(tmp_path) == []


@pytest.mark.parametrize('claim', ['Finishing my M.S. in May 2027', 'Graduating in 2027', 'Expected 2027'])
def test_cited_education_dates_are_supported_in_prose(env, tmp_path, claim):
    (tmp_path / 'cover_letter.tagged.md').write_text(f'- {claim} [E001]')
    assert numbers_match.check(tmp_path) == []


@pytest.mark.parametrize('claim', ['Led one engineer', 'Processed two scenes', 'Served dozens of labs',
    'Reduced latency by half', 'Improved by an order of magnitude',
    'A one-stage detector ran at 99 FPS', 'Expected 2027 FPS', 'Graduating in June 2027',
    'Graduating in May 2027 after processing 2027 scenes', 'Python 3 delivered 90 percent accuracy',
    'Five projects show how I work'])
def test_context_rules_do_not_allow_invented_measurements(env, tmp_path, claim):
    (tmp_path / 'resume.tagged.md').write_text(f'- {claim} [E001][F004]')
    assert numbers_match.check(tmp_path)
