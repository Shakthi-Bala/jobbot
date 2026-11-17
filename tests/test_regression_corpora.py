"""Permanent acceptance and rejection corpora, independent of parser heuristics."""
import json
from pathlib import Path
import pytest
from agents import core
from checks import numbers_match

CORPORA = Path(__file__).parent / 'corpora'
def cases(name):
    return json.loads((CORPORA / name).read_text())


@pytest.fixture
def corpus_profile(env, monkeypatch):
    profile = core.load_profile()
    profile['facts'] += [
        {'id': 'F090', 'text': 'Used Python 3.10, OpenCV 4, CUDA 12, PyTorch 2.1, ROS 2, TensorRT 8, NumPy 1.26, Ubuntu 22.04, C++17 and TensorFlow 2.15.'},
        {'id': 'F091', 'text': 'Worked in a team of four, mentored four interns and finished in the Top 5%; won second place.'},
        {'id': 'F092', 'text': 'Programmed a 6-DOF arm.'},
        {'id': 'F093', 'text': 'Finished 4th of 60 teams.'},
        {'id': 'F094', 'text': 'Built a two-stage pipeline for 60 teams.'}]
    monkeypatch.setattr(core, 'load_profile', lambda: profile)
    return profile


@pytest.mark.parametrize('case', cases('honest_sentences.json'), ids=lambda c: c['id'])
def test_honest_sentence_corpus(corpus_profile, tmp_path, case):
    (tmp_path / 'resume.tagged.md').write_text(f"- {case['text']} [{case['cite']}]\n")
    assert numbers_match.check(tmp_path) == [], case['text']


@pytest.mark.parametrize('case', cases('invented_sentences.json'), ids=lambda c: c['id'])
def test_invented_sentence_corpus(corpus_profile, tmp_path, case):
    if case.get('metadata'):
        (tmp_path / 'meta.json').write_text(json.dumps(case['metadata']))
    tags = ''.join(f'[{tag}]' for tag in case['cite'].split())
    (tmp_path / 'resume.tagged.md').write_text(f"- {case['text']} {tags}\n")
    assert numbers_match.check(tmp_path), case['text']


@pytest.mark.parametrize('case', cases('pay_strings.json'), ids=lambda c: c['id'])
def test_pay_string_corpus(case):
    expected = tuple(case['expected']) if case['expected'] else None
    assert core.parse_pay_text(case['text']) == expected, case['text']


@pytest.mark.parametrize('case', cases('public_pay_excerpts.json'), ids=lambda c: c['id'])
def test_public_pay_excerpt_corpus(case):
    assert core.parse_pay_text(case['text']) == tuple(case['expected']), case['source']


@pytest.mark.parametrize('name,minimum', [('honest_sentences.json', 55), ('invented_sentences.json', 34),
    ('pay_strings.json', 50), ('public_pay_excerpts.json', 50)])
def test_corpora_remain_complete_and_case_ids_unique(name, minimum):
    data = cases(name)
    assert len(data) >= minimum
    assert len({item['id'] for item in data}) == len(data)
