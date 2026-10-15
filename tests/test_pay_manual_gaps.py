import json

import pytest

from agents import core, discover, gaps
from agents.schemas import GapReport, Rewrite


# ---------------------------------------------------------------- pay

@pytest.mark.parametrize("text,expected", [
    ("The base pay range is $136,000—$174,000 USD.", (136_000, 174_000)),
    ("Salary: $190K – $230K • Offers Equity", (190_000, 230_000)),
    ("Hourly pay $60 — $75 USD per hour", (60 * 2080, 75 * 2080)),
    ("CA: $150,000 - $200,000; WA: $140,000 to $190,000", (140_000, 200_000)),
    ("We raised $250,000,000 - $300,000,000 in funding", None),
    ("No pay listed here.", None),
])
def test_parse_pay_text(text, expected):
    assert core.parse_pay_text(text) == expected


def test_pay_bands_start_at_top():
    assert core.pay_band(250_000) == "$200K+"
    assert core.pay_band(175_000) == "$150-200K"
    assert core.pay_band(85_000) == "$80-100K"
    assert core.pay_band(None) == "pay not listed"


def test_ashby_and_lever_structured_pay():
    a = discover._ashby_job("x", {
        "id": "1", "title": "Robot Learning Engineer", "location": "SF",
        "descriptionPlain": "text", "compensation": {
            "compensationTierSummary": "$190K – $230K",
            "summaryComponents": [{"compensationType": "Salary", "interval": "1 YEAR",
                                   "currencyCode": "USD", "minValue": 190000, "maxValue": 230000}]}})
    assert (a["comp_min"], a["comp_max"], a["comp_source"]) == (190_000, 230_000, "ats")
    lv = discover._lever_job("x", {"id": "2", "text": "RL Engineer", "categories": {},
                                   "salaryRange": {"currency": "USD", "interval": "per-year-salary",
                                                   "min": 115000, "max": 175000}})
    assert (lv["comp_min"], lv["comp_max"]) == (115_000, 175_000)


def test_pay_floor_and_ordering(env):
    conn = core.connect()
    base = {"company": "A", "location": "Boston, MA", "source": "ashby", "raw_text": "x",
            "raw_html": ""}
    jobs = [base | {"title": "Perception Engineer", "comp_min": 60_000, "comp_max": 75_000},
            base | {"title": "Robotics Engineer", "comp_min": 120_000, "comp_max": 150_000},
            base | {"title": "Robot Learning Engineer", "comp_min": 200_000, "comp_max": 260_000},
            base | {"title": "Autonomy Engineer"}]
    ids = discover.upsert_jobs(conn, jobs, {}, parse=False, min_pay=80_000)
    titles = [core.get_job(conn, i)["title"] for i in discover.sort_by_pay(conn, ids)]
    assert titles == ["Robot Learning Engineer", "Robotics Engineer", "Autonomy Engineer"]


def test_keywords_match_whole_words():
    t = {"titles": ["Perception Engineer", "Robotics Engineer"],
         "include_keywords": ["RL", "ML", "perception"], "exclude_keywords": ["Intern"]}
    ok = lambda title: discover.matches_targets({"title": title, "location": ""}, t)[0]
    assert ok("RL Engineer, Humanoids")
    assert not ok("Real World Data Specialist")      # 'rl' inside 'world'
    assert not ok("Perception Intern")
    assert ok("Perception Engineer, Internal Tools")  # 'Intern' inside 'Internal'
    assert not ok("Mechanical Engineer, Robotics")    # extra words count against a title match
    assert ok("Robotics Engineer II")


# ------------------------------------------------------------- manual mode

def test_manual_mode_round_trip(env, monkeypatch):
    monkeypatch.setenv("JOBBOT_MODE", "manual")
    with pytest.raises(core.ManualTaskPending) as e:
        core.llm_json("writing", "sys", "user prompt", Rewrite)
    task = e.value.path
    assert task.exists() and "Rewrite" in task.read_text()
    assert core.pending_tasks() == [task]
    (task.parent / f"{e.value.key}.answer.json").write_text('{"text": "hello"}')
    assert core.llm_json("writing", "sys", "user prompt", Rewrite).text == "hello"
    assert core.pending_tasks() == []


def test_manual_mode_rejects_bad_answer(env, monkeypatch):
    monkeypatch.setenv("JOBBOT_MODE", "manual")
    with pytest.raises(core.ManualTaskPending) as e:
        core.llm_json("writing", "sys", "other", Rewrite)
    (e.value.path.parent / f"{e.value.key}.answer.json").write_text('{"wrong": 1}')
    with pytest.raises(core.JobbotError, match="does not match"):
        core.llm_json("writing", "sys", "other", Rewrite)


def test_manual_parse_is_deferred_to_fit(env, monkeypatch):
    monkeypatch.setenv("JOBBOT_MODE", "manual")
    conn = core.connect()
    j = {"company": "A", "title": "Perception Engineer", "location": "Boston, MA",
         "source": "ashby", "raw_text": "posting", "raw_html": ""}
    [jid] = discover.upsert_jobs(conn, [j], {}, parse=True)
    assert core.get_job(conn, jid)["parsed_json"] is None
    assert len(core.pending_tasks()) == 1


# --------------------------------------------------------------- gaps

def report(**kw) -> GapReport:
    base = {
        "verdict": "stretch", "readiness": 55, "summary": "Strong perception, thin on RL.",
        "requirements": [
            {"requirement": "Reinforcement learning for manipulation", "kind": "must_have",
             "status": "met", "fact_ids": [], "note": "claimed without evidence"},
            {"requirement": "PyTorch", "kind": "must_have", "status": "met",
             "fact_ids": ["F001", "F999"], "note": ""},
            {"requirement": "C++", "kind": "must_have", "status": "missing", "fact_ids": [],
             "note": ""}],
        "resume_improvements": [], "gaps": [
            {"gap": "No C++", "importance": "critical", "how_to_close": "Port X", "weeks": 3}],
        "projects": [{"title": "Sim-to-real PPO reaching with domain randomization",
                      "closes": ["Reinforcement learning for manipulation"],
                      "description": "d", "builds_on": ["F002", "F999"], "stack": ["Isaac Lab"],
                      "deliverables": ["repo"], "success_metric": "real success rate", "weeks": 6}],
        "how_to_get_it": ["Referral via alumni"], "interview_topics": ["PPO"]}
    return GapReport.model_validate(base | kw)


def test_gap_enforce_requires_evidence(env):
    r = gaps.enforce(report(), core.load_profile(), "j1")
    assert r.requirements[0].status == "missing"          # 'met' with no IDs
    assert r.requirements[1].fact_ids == ["F001"]          # unknown ID dropped
    assert r.projects[0].builds_on == ["F002"]


def test_gap_summary_orders_by_pay(env):
    conn = core.connect()
    base = {"location": "Boston, MA", "source": "ashby", "raw_text": "x", "raw_html": ""}
    ids = discover.upsert_jobs(conn, [
        base | {"company": "Lo", "title": "Robotics Engineer", "comp_min": 90_000, "comp_max": 110_000},
        base | {"company": "Hi", "title": "Robot Learning Engineer", "comp_min": 210_000, "comp_max": 250_000},
    ], {}, parse=False)
    for jid in ids:
        gaps.write(core.get_job(conn, jid), gaps.enforce(report(), core.load_profile(), jid))
    text = gaps.summary()
    assert text.index("$200K+") < text.index("$100-120K")
    assert "helps 2 job(s)" in text
    assert json.loads((core.OUT / ids[0] / "gaps.json").read_text())["verdict"] == "stretch"
    assert (core.OUT / ids[1] / "gaps.md").read_text().startswith("# Gaps: Robot Learning Engineer")
