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
import hashlib
import io
import json
import os
import subprocess
import shlex
import sys
from pathlib import Path
from urllib.parse import urlsplit

from . import core

MIN_LEN = 5          # shorter fragments ("MIT", "Lab") would match ordinary words
MAX_BYTES = 2_000_000
HOOK = """#!/bin/sh
# Installed by `python jobbot.py privacy --install-hook`.
cd "$(git rev-parse --show-toplevel)" || exit 1
__PYTHON__ jobbot.py privacy --push || {
  echo "push refused: privacy check failed (see above)" >&2
  exit 1
}
"""
ASSET_MANIFEST = 'docs/assets/public-assets.json'
PRIVATE_PATHS = ('.env', 'data/profile.yaml', 'data/answers_bank.yaml', 'data/credentials.json',
                 'data/token.json', 'data/tracker.db', 'data/master_resume.yaml',
                 'data/approved_bullets.yaml', 'data/decisions.tsv', 'data/daily_log.md',
                 'data/weekly_review.md', 'data/run.log', 'data/applications.xlsx',
                 '.streamlit/secrets.toml', 'my_resume/', 'data/uploads/', 'out/')


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


def _git_bytes(root: Path, *args: str) -> bytes:
    result = subprocess.run(['git', *args], cwd=root, capture_output=True)
    if result.returncode:
        raise core.JobbotError('Cannot read the Git objects needed for the privacy scan')
    return result.stdout


def approved_assets(root: Path, commit: str | None = None) -> dict:
    if commit:
        try:
            raw = _git_bytes(root, 'show', f'{commit}:{ASSET_MANIFEST}')
        except core.JobbotError:
            return {}
    else:
        path = root / ASSET_MANIFEST
        raw = path.read_bytes() if path.exists() else b'{}'
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError('expected mapping')
        return data
    except (ValueError, UnicodeError) as e:
        raise core.JobbotError('Public asset manifest is invalid') from e


def public_repository(root: Path) -> str:
    try:
        remote = _git(root, 'config', '--get', 'remote.origin.url').strip()
    except core.JobbotError:
        return ''
    match = re.fullmatch(r'(?:git@github\.com:|https://github\.com/)([\w.-]+/[\w.-]+?)(?:\.git)?', remote)
    return 'https://github.com/' + match[1] if match else ''


def configured_secrets() -> list[bytes]:
    path = core.DATA.parent / '.env'
    values = []
    if path.exists():
        for line in path.read_text().splitlines():
            key, sep, value = line.partition('=')
            if sep and any(word in key.upper() for word in ('TOKEN', 'SECRET', 'API_KEY', 'WEBHOOK')):
                value = value.strip().strip('\"\'')
                if len(value) >= 16:
                    values.append(value.encode())
    for key, value in os.environ.items():
        if any(word in key.upper() for word in ('API_KEY', 'WEBHOOK', 'SECRET', 'TOKEN')) and len(value) >= 16:
            values.append(value.encode())
    return values


def inspect_blob(data: bytes, path: str, ids: dict[str, str], assets: dict,
                 secrets: list[bytes], repository: str = '') -> list[str]:
    """Report categories only. Unknown binary assets require explicit review."""
    if path.startswith(PRIVATE_PATHS):
        return [f'{path}: private file must not be tracked']
    if any(secret in data for secret in secrets):
        return [f'{path}: contains a configured secret']
    approved = assets.get(path, {}).get('sha256', []) if isinstance(assets.get(path), dict) else []
    if Path(path).suffix.lower() in ('.png', '.jpg', '.jpeg', '.gif', '.webp') and hashlib.sha256(data).hexdigest() in approved:
        return []
    if len(data) > MAX_BYTES:
        return [f'{path}: exceeds privacy scan size limit; review required']
    try:
        pdf_without_text = False
        if Path(path).suffix.lower() == '.pdf':
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            text = '\n'.join(page.extract_text() or '' for page in reader.pages)
            pdf_without_text = not text.strip()
            text += '\n' + str(reader.metadata or '')
        else:
            text = data.decode('utf-8')
            if '\x00' in text:
                raise ValueError('binary data')
    except Exception:
        return [f'{path}: cannot inspect binary or document; review required']
    problems = []
    if pdf_without_text:
        problems.append(f'{path}: PDF has no extractable text; review required')
    for number, line in enumerate(text.splitlines(), 1):
        # The configured public repository URL is intentional project attribution.
        folded = (re.sub(re.escape(repository) + r'''(?=$|[/\s?#)"'])''',
                         '<public-repository>', line, flags=re.I) if repository else line).casefold()
        labels = sorted({label for needle, label in ids.items() if needle in folded})
        for needle, label in ids.items():
            if label != 'phone':
                continue
            digits = re.sub(r'\D', '', needle)
            if len(digits) >= 7 and re.search(
                    r'(?<!\d)' + r'[\s().+\-]*'.join(digits) + r'(?!\d)', folded):
                labels = sorted(set(labels) | {'phone'})
        if labels:
            problems.append(f"{path}:{number} contains your {', '.join(labels)}")
    return problems


def scan(files: list[Path], ids: dict[str, str], root: Path | None = None) -> list[str]:
    """One line per hit: file:line and what kind of detail it is (the value is not echoed)."""
    problems = []
    assets = approved_assets(root) if root else {}
    repository = public_repository(root) if root else ''
    secrets = configured_secrets()
    for path in files:
        try:
            if not path.is_file():
                continue
            if path.stat().st_size > MAX_BYTES:
                problems.append(f'{path.name}: exceeds privacy scan size limit; review required')
                continue
            data = path.read_bytes()
        except OSError:
            problems.append(f'{path.name}: unreadable file; review required')
            continue
        shown = path.relative_to(root) if root and path.is_relative_to(root) else path
        problems.extend(inspect_blob(data, str(shown), ids, assets, secrets, repository))
    return problems


def run(root: Path | None = None) -> list[str]:
    root = root or core.ROOT
    ids = identifiers(core.load_profile()) if (core.DATA / 'profile.yaml').exists() else {}
    return scan(tracked_files(root), ids, root)


def scan_push(updates: str, root: Path | None = None) -> list[str]:
    """Inspect committed blobs in every outgoing commit, independent of worktree."""
    root = root or core.ROOT
    ids = identifiers(core.load_profile()) if (core.DATA / 'profile.yaml').exists() else {}
    commits = set()
    for line in updates.splitlines():
        fields = line.split()
        if len(fields) != 4:
            raise core.JobbotError('Invalid pre-push ref update')
        _, local, _, remote = fields
        if not all(re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', sha) for sha in (local, remote)):
            raise core.JobbotError('Invalid pre-push object ID')
        if set(local) == {'0'}:
            continue  # deleting a ref introduces no objects
        args = ['rev-list', local]
        if set(remote) != {'0'}:
            try:
                _git_bytes(root, 'cat-file', '-e', remote)
            except core.JobbotError:
                pass  # unknown remote ancestor: conservatively scan all local commits
            else:
                args += ['--not', remote]
        commits.update(_git(root, *args).splitlines())
    seen, problems = set(), []
    repository, secrets = public_repository(root), configured_secrets()
    for commit in sorted(commits):
        assets = approved_assets(root, commit)
        paths = _git(root, 'diff-tree', '--root', '-r', '-m', '--no-commit-id',
                     '--diff-filter=ACMRT', '--name-only', '-z', commit).split('\0')
        for path in filter(None, paths):
            oid = _git(root, 'rev-parse', f'{commit}:{path}').strip()
            key = (oid, path, json.dumps(assets, sort_keys=True))
            if key in seen:
                continue
            seen.add(key)
            if _git(root, 'cat-file', '-t', oid).strip() != 'blob':
                continue
            if int(_git(root, 'cat-file', '-s', oid)) > MAX_BYTES:
                problems.append(f'{commit[:12]} {path}: exceeds privacy scan size limit; review required')
                continue
            findings = inspect_blob(_git_bytes(root, 'cat-file', 'blob', oid), path, ids,
                                    assets, secrets, repository)
            problems.extend(f'{commit[:12]} {finding}' for finding in findings)
    return problems


def install_hook(root: Path | None = None) -> Path:
    root = root or core.ROOT
    hook = (root / _git(root, "rev-parse", "--git-path", "hooks/pre-push").strip()).resolve()
    if hook.exists() and "jobbot.py privacy" not in hook.read_text():
        raise core.JobbotError(f"{hook} already exists; add `python3 jobbot.py privacy` to it by hand")
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(HOOK.replace('__PYTHON__', shlex.quote(sys.executable)))
    hook.chmod(0o755)
    return hook
