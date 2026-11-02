import json

import yaml

from agents import ats, core, master, panel
from agents.schemas import InterviewDecision, PersonaReview, RevisionPlan, ScreenDecision


# ------------------------------------------------------------------ ats

def test_mentions_handles_symbols_and_variants():
    assert ats.mentions("C++", "Strong C++17 and Python")
    assert ats.mentions("C++", "Python and C++20")
    assert not ats.mentions("C++", "C++17helper")
    assert ats.mentions("C++", "Python, C++, Rust")
    assert not ats.mentions("C++", "Python and C programming")
    assert ats.mentions("ROS 2", "built ROS2 nodes")
    assert ats.mentions("Sim-to-Real", "sim to real transfer on a UR16e")
    assert ats.mentions("IsaacLab", "trained in NVIDIA Isaac Lab")
    assert not ats.mentions("RL", "real world data")


def test_classify_separates_fixable_from_gaps(env):
    profile = core.load_profile()          # example profile: PyTorch, ROS 2, VIO...
    r = ats.classify(["PyTorch", "ROS 2", "Bazel"], profile, resume_text="Skills: PyTorch")
    assert r["in_resume"] == ["PyTorch"]
    assert r["fixable"] == ["ROS 2"]
    assert r["gap"] == ["Bazel"]
    assert (r["score"], r["max_score"]) == (33, 67)


# ---------------------------------------------------------------- panel

def _reviews(gate="pass_to_human", hm="interview", score=8):
    reader = PersonaReview(verdict="advance", score=score, first_impression="clear", strongest="x",
                           weakest="y", lines_that_hurt=[], edits=[])
    out = {k: reader for k in panel.READERS}
    out["ats_gate"] = ScreenDecision(decision=gate, score=82, knockout_failures=[],
                                     missing_keywords=[], parsing_problems=[], reason="ok")
    out["hiring_manager"] = InterviewDecision(decision=hm, confidence=70, reasons_for=[],
                                              reasons_against=[], what_would_change_my_mind=[],
                                              interview_questions=[])
    return out


def _plan(revisions=1, bulletproof=False):
    return RevisionPlan(keep=["summary"], conflicts_resolved=[], needs_new_evidence=["C++"],
                        bulletproof=bulletproof,
                        revisions=[{"instruction": "Lead with the PPO result", "fact_ids": ["F003"],
                                    "raised_by": ["ceo", "recruiter"]}] * revisions)


def test_panel_stops_when_everyone_says_yes():
    kw = {"score": 92, "max_score": 95}
    assert panel.summarize(_reviews(), _plan(), kw, 1)["done"]
    assert not panel.summarize(_reviews(hm="maybe"), _plan(), kw, 1)["done"]
    assert not panel.summarize(_reviews(score=6), _plan(), kw, 1)["done"]
    assert panel.summarize(_reviews(hm="no"), _plan(bulletproof=True), kw, 1)["done"]
    assert panel.summarize(_reviews(hm="no"), _plan(revisions=0), kw, 1)["done"]


def test_panel_history_and_markdown(tmp_path):
    kw = {"score": 80, "max_score": 93}
    panel.save(tmp_path, panel.summarize(_reviews(hm="maybe"), _plan(), kw, 1))
    panel.save(tmp_path, panel.summarize(_reviews(), _plan(), kw, 2))
    history = json.loads((tmp_path / "panel.json").read_text())
    assert [h["round"] for h in history] == [1, 2]
    md = (tmp_path / "panel.md").read_text()
    assert "| 1 | pass_to_human (82) | 80% (max 93%) | maybe" in md
    assert "Needs new evidence (gap): C++" in md


# --------------------------------------------------------------- master

MASTER = {
    "families": {"rl": {"label": "Robot learning", "experience": ["X001"], "projects": ["P002"],
                        "skill_categories": ["Skills"]}},
    "summaries": {"rl": {"text": "Robotics M.S. student building ROS 2 perception at 30 FPS.",
                         "fact_ids": ["E001", "F003"]}},
    "entries": {
        "X001": [{"text": "Built a ROS 2 perception pipeline running at 30 FPS on a Raspberry Pi 5",
                  "fact_ids": ["F003"], "families": ["rl", "perception"], "priority": 1}],
        "P002": [{"text": "Trained visual-inertial odometry networks on an HPC cluster",
                  "fact_ids": ["F002"], "families": ["rl"], "priority": 1}],
        "P001": [{"text": "Designed a learned 11×11 coded aperture with a CNN depth classifier",
                  "fact_ids": ["F001"], "families": ["perception"], "priority": 1}],
    },
}


def test_master_family_picks_tagged_bullets(env):
    c = master.content_for(MASTER, core.load_profile(), "rl")
    assert [e["ref_id"] for e in c["experience"]] == ["X001"]
    assert [e["ref_id"] for e in c["projects"]] == ["P002"]       # P001 isn't tagged rl
    assert c["summary"]["fact_ids"] == ["E001", "F003"]


def test_master_renders_one_page_and_passes_checks(env, monkeypatch):
    monkeypatch.setattr(master, "PATH", core.DATA / "master_resume.yaml")
    master.PATH.write_text(yaml.safe_dump(MASTER))
    r = master.render("rl")
    assert all(not v for v in r["results"].values()), r["results"]
    data = json.loads((r["dir"] / "resume.json").read_text())
    assert data["summary"].startswith("Robotics M.S.")
    assert data["sections"][0] == "summary"


def test_geometry_and_estimation_are_profile_equivalents_not_literal_resume_matches():
    profile = {'facts': [{'text': 'Visual-inertial odometry with camera geometry and structure from motion'}]}
    keywords = ['state estimation', 'visual odometry', '3D reconstruction', '3D geometry', 'LiDAR']
    result = ats.classify(keywords, profile, resume_text='Visual-inertial odometry and structure from motion')
    assert result['fixable'] == keywords[:4]
    assert result['gap'] == ['LiDAR']
    # Evidence permits precise rewording; it does not pretend an absent literal
    # keyword is already present in the rendered resume.
    assert result['in_resume'] == []


def test_requested_score_cannot_be_waived_by_editor_or_average():
    kw = {'score': 87, 'max_score': 87}
    reviews = _reviews(score=10)
    reviews['recruiter'] = reviews['recruiter'].model_copy(update={'score': 8})
    result = panel.summarize(reviews, _plan(bulletproof=True), kw, 1, min_score=9)
    assert result['reader_avg'] > 9 and result['reader_min'] == 8
    assert not result['done']
    assert not panel.summarize(_reviews(hm='no', score=9), _plan(bulletproof=True), kw, 1, min_score=9)['done']
    assert not panel.summarize(_reviews(gate='reject', score=9), _plan(revisions=0), kw, 1, min_score=9)['done']
    assert panel.summarize(_reviews(score=9), _plan(), kw, 1, min_score=9)['done']
    reviews = _reviews(score=9)
    del reviews['recruiter']
    assert not panel.summarize(reviews, _plan(), kw, 1, min_score=9)['done']


def test_requested_score_must_be_finite_and_on_the_reader_scale():
    import pytest
    for target in ['invalid', float('nan'), float('inf'), 0, 11]:
        with pytest.raises(core.JobbotError, match='panel_min_score'):
            panel.summarize(_reviews(), _plan(), {'score': 87, 'max_score': 87}, 1, min_score=target)


def test_fractional_scores_are_not_rounded_up_to_meet_target():
    reviews = _reviews(score=9.3)
    reviews['recruiter'] = reviews['recruiter'].model_copy(update={'score': 8.9})
    result = panel.summarize(reviews, _plan(bulletproof=True), {'score':87,'max_score':87}, 1, min_score=9.0)
    assert result['reader_min'] == 8.9 and not result['done']
    assert PersonaReview.model_validate(reviews['team_lead'].model_dump()).score == 9.3


def _strict_reviews(score=8.0):
    from agents.schemas import ResumeRubric
    rubric = ResumeRubric.model_validate({
        'ownership_depth': {'points':24, 'reason':'Owned components described, some attribution unclear'},
        'impact_validation': {'points':20, 'reason':'Material validation details not visible'},
        'role_focus': {'points':18, 'reason':'Strong match to the posting'},
        'communication': {'points':18, 'reason':'Readable with minor density issues'}})
    return {k:(v.model_copy(update={'rubric':rubric}) if k in panel.READERS else v)
            for k,v in _reviews(score=score).items()}


def test_strict_rubric_does_not_reward_eligibility_or_editor_approval():
    result=panel.summarize(_strict_reviews(),_plan(bulletproof=True),{'score':87,'max_score':87},1,
                           min_score=9,strict_rubric=True)
    assert result['reader_min']==8 and not result['done'] and result['rubric_version']==2


def test_strict_rubric_rejects_unsubstantiated_scores_and_missing_breakdown():
    import pytest
    with pytest.raises(core.JobbotError,match='rubric components'):
        panel.summarize(_reviews(score=9),_plan(),{'score':87,'max_score':87},1,strict_rubric=True)
    with pytest.raises(core.JobbotError,match='does not match rubric'):
        panel.summarize(_strict_reviews(score=9.3),_plan(),{'score':87,'max_score':87},1,strict_rubric=True)
    reviews=_strict_reviews()
    reviews['recruiter'].rubric.impact_validation.points=31
    with pytest.raises(core.JobbotError,match='rubric component'):
        panel.summarize(reviews,_plan(),{'score':87,'max_score':87},1,strict_rubric=True)
