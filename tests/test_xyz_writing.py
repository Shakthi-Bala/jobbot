"""The actual drafting paths receive XYZ even when an approved bank exists."""
import copy

import pytest

from agents import bank, core, master, tailor
from agents.schemas import MasterResume
from tests.test_checks import good_packet


@pytest.mark.parametrize("has_approved_wording", [False, True])
def test_tailored_draft_receives_xyz_without_changing_evidence(job, monkeypatch,
                                                            has_approved_wording):
    approved = {"X001": [{"text": "Built a ROS 2 perception pipeline running at 24 FPS",
                           "fact_ids": ["F003"]}]} if has_approved_wording else {}
    original = copy.deepcopy(approved)
    monkeypatch.setattr(bank, "load", lambda profile: approved)
    monkeypatch.setattr(master, "load", lambda: None)
    seen = {}

    def model(role, system, user, schema, **kwargs):
        seen.update(system=system, user=user)
        return good_packet()

    monkeypatch.setattr(core, "llm_json", model)
    result = tailor.draft(core.connect(), job["id"])

    assert tailor.XYZ_GUIDANCE in seen["user"]
    assert "verified measurement" in seen["system"]
    assert "never invent a metric" in seen["user"]
    assert "no publishable measurement" in seen["user"]
    assert "physical versus simulated boundaries" in seen["user"]
    if has_approved_wording:
        assert original["X001"][0]["text"] in seen["user"]
        assert "rephrase or combine supported wording into XYZ" in seen["user"]
        assert "not automatically approved wording" in seen["user"]
    assert approved == original
    assert result.experience[0].bullets[0].fact_ids == ["F003"]


def test_master_draft_receives_the_same_xyz_policy(env, monkeypatch):
    seen = {}

    def model(role, system, user, schema, **kwargs):
        seen.update(system=system, user=user)
        return MasterResume(entries=[], summaries=[], families=[])

    monkeypatch.setattr(core, "llm_json", model)
    output = master.draft()

    assert tailor.XYZ_GUIDANCE in seen["user"]
    assert "XYZ" in seen["system"]
    assert "confidential results" in seen["user"]
    assert output.parent == core.DATA
    assert master.load()["entries"] == {}
