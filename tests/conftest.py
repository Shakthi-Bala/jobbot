import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agents import core  # noqa: E402


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Isolated data/ and out/ with the example profile, so tests never touch your data."""
    data, out = tmp_path / "data", tmp_path / "out"
    data.mkdir()
    out.mkdir()
    shutil.copy(ROOT / "data/profile.example.yaml", data / "profile.yaml")
    shutil.copy(ROOT / "data/answers_bank.example.yaml", data / "answers_bank.yaml")
    shutil.copy(ROOT / "data/companies.yaml", data / "companies.yaml")
    monkeypatch.setattr(core, "DATA", data)
    monkeypatch.setattr(core, "OUT", out)
    monkeypatch.setattr(core, "DB_PATH", data / "tracker.db")
    monkeypatch.setattr(core, "DECISIONS_PATH", data / "decisions.tsv")
    from agents import master
    monkeypatch.setattr(master, "PATH", data / "master_resume.yaml")
    return tmp_path


POSTING = """Perception Engineer
Required: visual-inertial odometry, PyTorch, ROS 2.
This position requires access to export-controlled information; applicants must be
U.S. persons as defined by ITAR.
Application questions:
Why robotics?
Gender
Describe your FPGA experience"""


@pytest.fixture
def job(env):
    from agents import discover
    conn = core.connect()
    j = {"company": "Example Robotics", "title": "Perception Engineer", "location": "Boston, MA",
         "req_id": "R-1", "url": None, "source": "manual", "raw_text": POSTING, "raw_html": ""}
    jid = discover.upsert_jobs(conn, [j], targets={}, parse=False)[0]
    parsed = {"must_have": ["ROS 2"], "restrictions": [
        {"type": "export_control", "quote": "applicants must be U.S. persons as defined by ITAR"}],
        "keywords": ["ROS 2", "PyTorch"], "injection_flags": [],
        "application_questions": ["Why robotics?", "Gender", "Describe your FPGA experience"]}
    conn.execute("UPDATE jobs SET parsed_json=? WHERE id=?", (core.dumps(parsed), jid))
    conn.commit()
    return core.get_job(conn, jid)


@pytest.fixture
def packet(job):
    from agents import tailor
    from tests.test_checks import good_packet
    profile = core.load_profile()
    content = tailor.enforce(good_packet(), profile, job["id"], ["ROS 2"])
    d = tailor.write_packet(job, content, profile, version=1)
    tailor.render(d)
    return d
