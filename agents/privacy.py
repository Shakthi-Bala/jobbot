"""Keep personal details out of git.

    python jobbot.py privacy                  scan every file git tracks
    python jobbot.py privacy --install-hook   run the scan before each `git push`

The private profile (data/profile.yaml, gitignored) is the list of what must never be
committed: name, email, phone, city, profile links and handles, schools, thesis titles,
labs, employers and referees. Examples and tests use invented people; if a real detail
is pasted into one, the scan names the file and line and the push is refused.
Plain software: no AI, no network.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

from . import core

MIN_LEN = 5          # shorter fragments ("MIT", "Lab") would match ordinary words
MAX_BYTES = 2_000_000
HOOK = """#!/bin/sh
# Installed by `python jobbot.py privacy --install-hook`.
cd "$(git rev-parse --show-toplevel)" || exit 1
python3 jobbot.py privacy || {
  echo "push refused: personal details found in tracked files (see above)" >&2
  exit 1
}
"""


def _clean(value) -> str:
    return re.sub(r"\s*\(.*?\)\s*", " ", str(value or "")).strip()


def identifiers(profile: dict) -> dict[str, str]:
    """{lower-cased text to look for: what it is}. Derived only from the profile."""
    found: dict[str, str] = {}

    def add(value, label: str) -> None:
        text = _clean(value)
        if len(text) >= MIN_LEN:
            found.setdefault(text.casefold(), label)

    person = profile.get("person", {}) or {}
    add(person.get("name"), "name")
    for part in str(person.get("name") or "").split():
        add(part, "name")
    email = str(person.get("email") or "")
    add(email, "email")
    add(email.split("@")[0], "email user name")
    phone = str(person.get("phone") or "")
    add(phone, "phone")
    digits = re.sub(r"\D", "", phone)
    if len(digits) >= 7:
        add(digits[-7:], "phone")
        add(f"{digits[-7:-4]}-{digits[-4:]}", "phone")
    add(person.get("location"), "home location")
    urls = list((person.get("links") or {}).values())
    for entry in profile.get("projects", []) or []:
        urls += list((entry.get("links") or {}).values())
    for url in urls:
        url = str(url or "")
        if not url:
            continue
        bare = re.sub(r"^https?://(www\.)?", "", url).rstrip("/")
        add(bare, "profile link")
        parsed = urlsplit(url if "://" in url else "https://" + url)
        host = (parsed.hostname or "").lower().removeprefix("www.")
        parts = [part for part in parsed.path.split("/") if part]
        # Arbitrary portfolio routes such as /projects/... are not identities.
        # Extract handles only from services whose account URL structure is known.
        if host in ("github.com", "gitlab.com") and parts:
            add(parts[0], "account handle")
        elif host == "linkedin.com" and len(parts) >= 2 and parts[0] == "in":
            add(parts[1], "account handle")
        elif host.endswith(".github.io"):
            add(host.removesuffix(".github.io"), "account handle")
    for entry in profile.get("education", []) or []:
        add(entry.get("school"), "school")
        add((entry.get("thesis") or {}).get("title"), "thesis title")
    for entry in profile.get("experience", []) or []:
        for key, label in (("org", "employer or lab"), ("employer", "employer"),
                           ("team", "lab or team"), ("verifier", "referee")):
            add(entry.get(key), label)
    return found


def _git(root: Path, *args: str) -> str:
    try:
        out = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    except FileNotFoundError as e:
        raise core.JobbotError("git is not installed on this machine; run the privacy scan "
                               "where you run `git push`") from e
    if out.returncode != 0:
        raise core.JobbotError("privacy scan needs a git repository")
    return out.stdout


def tracked_files(root: Path) -> list[Path]:
    out = _git(root, "ls-files", "-z")
    return [root / name for name in out.split("\0") if name]


def scan(files: list[Path], ids: dict[str, str], root: Path | None = None) -> list[str]:
    """One line per hit: file:line and what kind of detail it is (the value is not echoed)."""
    problems = []
    for path in files:
        try:
            if not path.is_file() or path.stat().st_size > MAX_BYTES:
                continue
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue  # binary or unreadable: nothing typed by hand in there
        shown = path.relative_to(root) if root and path.is_relative_to(root) else path
        for number, line in enumerate(text.splitlines(), 1):
            folded = line.casefold()
            labels = sorted({label for needle, label in ids.items() if needle in folded})
            if labels:
                problems.append(f"{shown}:{number} contains your {', '.join(labels)}")
    return problems


def run(root: Path | None = None) -> list[str]:
    root = root or core.ROOT
    if not (core.DATA / "profile.yaml").exists():
        return []  # no private profile on this machine, so nothing to compare against
    return scan(tracked_files(root), identifiers(core.load_profile()), root)


def install_hook(root: Path | None = None) -> Path:
    root = root or core.ROOT
    hook = (root / _git(root, "rev-parse", "--git-path", "hooks/pre-push").strip()).resolve()
    if hook.exists() and "jobbot.py privacy" not in hook.read_text():
        raise core.JobbotError(f"{hook} already exists; add `python3 jobbot.py privacy` to it by hand")
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(HOOK)
    hook.chmod(0o755)
    return hook
