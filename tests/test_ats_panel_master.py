import json

import yaml

from agents import ats, core, master, panel
from agents.schemas import InterviewDecision, PersonaReview, RevisionPlan, ScreenDecision


# ------------------------------------------------------------------ ats

def test_mentions_handles_symbols_and_variants():
    assert ats.mentions("C++", "Strong C++17 and Python")          is False  # C++17 is a different token
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
