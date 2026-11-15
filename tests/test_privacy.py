"""Personal details from the private profile never reach tracked files."""
import shutil
import subprocess

import pytest

from agents import core, privacy


def test_identifiers_come_from_the_profile_and_skip_short_fragments(env):
    ids = privacy.identifiers(core.load_profile())
    assert ids["alex example"] == "name" and ids["alex@example.com"] == "email"
    assert ids["boston, ma"] == "home location"
    assert ids["example polytechnic institute"] == "school"
    assert ids["example perception lab"] == "employer or lab"
    assert ids["alex-example"] == "account handle"
    assert "555-0100" in ids and "alex" not in ids          # four letters: too short to be safe
    assert "advisor name" in ids                              # the parenthetical note is dropped


def test_scan_reports_file_and_line_without_echoing_the_value(env, tmp_path):
    ids = privacy.identifiers(core.load_profile())
    clean, leaky = tmp_path / "clean.md", tmp_path / "leaky.py"
    clean.write_text("Nothing personal here.\n")
    leaky.write_text("x = 1\ncontact = 'ALEX@example.com'  # Example Perception Lab\n")
    (tmp_path / "image.bin").write_bytes(b"\xff\xfe\x00alex@example.com")
    problems = privacy.scan([clean, leaky, tmp_path / "image.bin"], ids, tmp_path)
    assert problems == ["leaky.py:2 contains your email, employer or lab, name"]
    assert "alex@example.com" not in problems[0].lower()


def test_portfolio_routes_are_not_account_handles():
    profile = {
        "person": {"links": {"site": "https://alex-robotics.github.io/",
                               "linkedin": "https://www.linkedin.com/in/alex-robotics/"}},
        "projects": [{"links": {"writeup": "https://alex-robotics.github.io/projects/vio/",
                                   "repo": "https://github.com/alex-robotics/vio/tree/main"}}],
    }
    ids = privacy.identifiers(profile)
    assert ids["alex-robotics"] == "account handle"
    assert "projects" not in ids and "tree" not in ids
    assert "alex-robotics.github.io/projects/vio" in ids


def test_custom_portfolio_paths_remain_protected_as_full_links():
    ids = privacy.identifiers({"person": {"links": {"site": "https://example.org/research/"}}})
    assert "research" not in ids
    assert "example.org/research" in ids


def test_missing_git_is_a_clear_error(env, tmp_path, monkeypatch):
    def no_git(*args, **kwargs):
        raise FileNotFoundError("git")
    monkeypatch.setattr(privacy.subprocess, "run", no_git)
    with pytest.raises(core.JobbotError, match="git is not installed"):
        privacy.tracked_files(tmp_path)


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed here")
def test_scan_runs_on_tracked_files_only_and_hook_installs(env, tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    for cmd in (["git", "init", "-q"], ["git", "config", "user.email", "t@t.t"],
                ["git", "config", "user.name", "t"]):
        subprocess.run(cmd, cwd=repo, check=True)
    (repo / "tracked.md").write_text("Written by Alex Example\n")
    (repo / "untracked.md").write_text("alex@example.com\n")
    subprocess.run(["git", "add", "tracked.md"], cwd=repo, check=True)
    assert privacy.run(repo) == ["tracked.md:1 contains your name"]
    hook = privacy.install_hook(repo)
    assert "jobbot.py privacy" in hook.read_text() and hook.stat().st_mode & 0o111
    assert privacy.install_hook(repo) == hook                # idempotent
    hook.write_text("#!/bin/sh\necho mine\n")
    with pytest.raises(core.JobbotError):
        privacy.install_hook(repo)                           # never overwrite someone else's hook
