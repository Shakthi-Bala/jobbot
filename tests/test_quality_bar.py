"""Approved wording, per-posting skill rows, required cover letters and page layout."""
import json

import pytest
import yaml

from agents import bank, core, latex, packet, tailor
from agents.schemas import SkillGroup
from checks import length_limits, page_layout, required_content
from tests.test_checks import good_packet


def _set_prefs(**prefs):
    path = core.DATA / "profile.yaml"
    profile = yaml.safe_load(path.read_text())
    profile.setdefault("preferences", {}).update(prefs)
    path.write_text(yaml.safe_dump(profile, sort_keys=False, allow_unicode=True))


def test_approving_a_packet_banks_its_bullets_once(packet, job):
    first = bank.promote(job["id"])
    assert first["added"] == 3 and first["already_present"] == 0
    again = bank.promote(job["id"])
    assert again["added"] == 0 and again["already_present"] == 3
    stored = bank.load(core.load_profile())
    assert stored["X001"][0]["text"].startswith("Built a ROS 2 perception pipeline")
    assert stored["X001"][0]["fact_ids"] == ["F003"]
    assert stored["X001"][0]["approved_from"] == job["id"]


def test_bank_drops_wording_the_profile_no_longer_supports(packet, job):
    bank.promote(job["id"])
    path = core.DATA / "profile.yaml"
    profile = yaml.safe_load(path.read_text())
    for entry in profile["experience"]:
        if entry["id"] == "X001":
            entry["facts"] = [f for f in entry["facts"] if f != "F003"]
    path.write_text(yaml.safe_dump(profile, sort_keys=False))
    assert "X001" not in bank.load(core.load_profile())


def test_writer_sees_approved_wording_and_packet_lists_new_wording(packet, job, monkeypatch):
    bank.promote(job["id"])
    seen = {}

    def fake(role, system, user, schema, max_tokens=0):
        seen["user"] = user
        p = good_packet()
        p.experience[0].bullets[0].text = "Ran a ROS 2 perception pipeline at 30 FPS on a Raspberry Pi 5"
        return p

    monkeypatch.setattr(core, "llm_json", fake)
    drafted = tailor.draft(core.connect(), job["id"])
    assert "## Approved wording" in seen["user"]
    assert "Built a ROS 2 perception pipeline running at 30 FPS" in seen["user"]
    profile = core.load_profile()
    content = tailor.enforce(drafted, profile, job["id"], ["ROS 2"])
    d = tailor.write_packet(job, content, profile, version=2)
    wording = (d / "wording.md").read_text()
    new, reused = wording.split("## Approved wording reused")
    assert "Ran a ROS 2 perception pipeline" in new
    assert "Trained VIO networks" in reused and "Trained VIO networks" not in new


def test_skill_groups_label_and_order_but_never_add(job):
    profile = core.load_profile()
    p = good_packet()
    p.skill_groups = [SkillGroup(category="Robotics", skills=["ROS 2", "Fortran", "CUDA"]),
                      SkillGroup(category="Learning", skills=["PyTorch", "ROS 2"]),
                      SkillGroup(category="Empty", skills=["COBOL"])]
    content = tailor.enforce(p, profile, job["id"], [])
    assert content["skill_groups"] == [{"category": "Robotics", "skills": ["ROS 2"]},
                                       {"category": "Learning", "skills": ["PyTorch"]}]
    d = tailor.write_packet(job, content, profile, version=1)
    rows = json.loads((d / "resume.json").read_text())["skills"]
    assert rows == [{"category": "Robotics", "items": ["ROS 2"]},
                    {"category": "Learning", "items": ["PyTorch"]}]


def test_cover_letter_is_required_when_the_candidate_always_wants_one(packet):
    assert required_content.check(packet) == []
    (packet / "cover_letter.md").unlink()
    assert required_content.check(packet) == []          # posting did not ask
    _set_prefs(cover_letter="always")
    assert any("cover letter is required" in p for p in required_content.check(packet))
    _set_prefs(cover_letter="sometimes")
    with pytest.raises(core.JobbotError):
        tailor.wants_cover_letter({}, core.load_profile())


def test_unwanted_cover_letter_is_not_sent(job, monkeypatch):
    monkeypatch.setattr(core, "llm_json", lambda *a, **k: good_packet())
    monkeypatch.setattr(tailor, "unslop", lambda paragraphs, profile: paragraphs)
    monkeypatch.setattr(tailor, "render", lambda d: [])
    d = tailor.build(core.connect(), job["id"])
    assert not (d / "cover_letter.md").exists()
    _set_prefs(cover_letter="always")
    d = tailor.build(core.connect(), job["id"], version=2)
    assert "Example Robotics" in (d / "cover_letter.md").read_text()


def test_cover_letter_must_name_the_company_and_meet_the_word_floor(packet):
    assert length_limits.check(packet) == []
    _set_prefs(cover_letter_min_words=180)
    assert any("under 180" in p for p in length_limits.check(packet))
    (packet / "cover_letter.md").write_text("I trained VIO networks on an HPC cluster.\n")
    assert any("never names the company" in p for p in required_content.check(packet))


def test_latex_cover_letter_matches_resume_header_without_bold_metrics(tmp_path):
    letter = {"person": {"name": "A B", "email": "a@b.c", "phone": "1", "location": "Boston, MA",
                         "links": {"github": "https://github.com/x"}},
              "company": "R&D Robotics", "title": "Perception Engineer", "location": "Boston, MA",
              "date": "2026-11-14", "layout": {"font_family": "charter"},
              "paragraphs": ["Cut error by 12.5% on 1,200 windows.", "Second_paragraph."]}
    tex = latex.render_cover_tex(letter, tmp_path / "cover_letter.tex").read_text()
    assert r"Dear R\&D Robotics Hiring Team," in tex
    assert "November 14, 2026" in tex and r"\textbf{Re: Perception Engineer}" in tex
    assert r"12.5\%" in tex and r"\textbf{12.5\%}" not in tex
    assert r"Second\_paragraph." in tex and r"\href{https://github.com/x}{GitHub}" in tex
    assert "XCharter" in tex


def test_page_layout_flags_an_underfilled_page_and_typst_fallback(packet):
    assert page_layout.check(packet) == []               # no limit configured
    blank = page_layout.bottom_blank_in(packet / "resume.pdf")
    assert 0.3 < blank < 11
    _set_prefs(resume_max_bottom_blank_in=blank - 0.5)
    assert any("more line(s) fit" in p for p in page_layout.check(packet))
    _set_prefs(resume_max_bottom_blank_in=blank + 0.5)
    assert page_layout.check(packet) == []
    meta = json.loads((packet / "meta.json").read_text()) | {"format": "latex"}
    (packet / "meta.json").write_text(json.dumps(meta))
    (packet / "LATEX_NOTE.md").write_text("fallback")
    assert any("Typst fallback" in p for p in page_layout.check(packet))


def test_force_builds_a_skipped_posting_but_never_a_blocked_one(job, monkeypatch):
    conn = core.connect()
    conn.execute("INSERT INTO fit (job_id, score, decision, strengths_json, gaps_json, "
                 "restrictions_json, unknowns_json, questions_json, created_at) "
                 "VALUES (?,?,?,?,?,?,?,?,?)",
                 (job["id"], 40, "skip", "[]", "[]", "[]", "[]", "[]", core.now()))
    conn.commit()
    assert packet.build(job["id"], offline=True)["status"] == "skipped"
    core.set_status(conn, job["id"], "scored")

    def fake_build(conn, job_id, feedback, version):
        from tests.test_checks import good_packet as gp
        profile = core.load_profile()
        d = tailor.write_packet(job, tailor.enforce(gp(), profile, job_id, ["ROS 2"]), profile, version)
        tailor.render(d)
        return d

    monkeypatch.setattr(tailor, "build", fake_build)
    r = packet.build(job["id"], skip_review=True, offline=True, force=True)
    assert r["status"] == "ready_for_review"
    conn.execute("UPDATE fit SET decision='blocked' WHERE job_id=?", (job["id"],))
    conn.commit()
    core.set_status(conn, job["id"], "scored")
    assert packet.build(job["id"], skip_review=True, offline=True, force=True)["status"] == "blocked"


def test_cover_letter_address_uses_a_clean_city_or_nothing():
    assert latex._city("Onsite- Salem, OR") == "Salem, OR"
    assert latex._city("San Jose, CA") == "San Jose, CA"
    assert latex._city("San Jose, CA; Boston, MA") == ""
    assert latex._city("Remote") == "" and latex._city("") == ""


def test_skill_names_do_not_break_across_lines(tmp_path):
    resume = {"person": {"name": "A B", "email": "a@b.c", "phone": "", "location": "", "links": {}},
              "education": [], "experience": [], "projects": [],
              "skills": [{"category": "Perception", "items": ["Grounding DINO", "ROS 2", "C++17"]}]}
    tex = latex.render_tex(resume, tmp_path / "resume.tex").read_text()
    assert r"\textbf{Perception:} Grounding~DINO, ROS~2, C++17\par" in tex


def test_lone_present_is_not_shown_as_a_project_date():
    assert tailor.dates({"start": None, "end": "present"}) == ""
    assert tailor.dates({"start": "2026-01", "end": "present"}) == "Jan 2026 – Present"
    assert tailor.dates({"start": None, "end": "2025"}) == "2025"
