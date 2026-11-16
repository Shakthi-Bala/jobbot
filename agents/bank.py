"""Approved wording: bullets the candidate accepted on a rendered page.

A resume that survived review should not be re-derived from raw facts for the next
posting. `python jobbot.py approve JOB_ID` (and `mark-applied`) copies a packet's
bullets into data/approved_bullets.yaml. The writer then starts every new draft from
that wording and writes fresh bullets only where a posting needs evidence that no
approved bullet covers. Each packet lists which bullets are approved and which are new
in wording.md, so new claims are the ones you read closely.

The bank holds wording only. Facts stay in profile.yaml, and a bullet is dropped as
soon as its fact IDs stop belonging to its entry.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from . import core

FILENAME = "approved_bullets.yaml"
_ENTRY_RE = re.compile(r"^###\s.*\[([XP]\d{3})\]\s*$")
_BULLET_RE = re.compile(r"^-\s+(.*?)\s*((?:\[[FEXP]\d{3}\])+)\s*$")


def path() -> Path:
    return core.DATA / FILENAME


def _key(text: str) -> str:
    # Punctuation carries meaning: < 5 ms and > 5 ms are different claims.
    return " ".join(text.split())


def load(profile: dict | None = None) -> dict[str, list[dict]]:
    """{entry id: [bullet, ...]}, keeping only bullets the profile still supports."""
    p = path()
    if not p.exists():
        return {}
    raw = (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("entries", {}) or {}
    if profile is None:
        return raw
    entries = {e["id"]: e for e in profile.get("experience", []) + profile.get("projects", [])}
    out = {}
    for ref, bullets in raw.items():
        allowed = set(entries.get(ref, {}).get("facts", []))
        kept = [b for b in bullets or []
                if b.get("text") and b.get("fact_ids") and set(b["fact_ids"]) <= allowed]
        if kept:
            out[ref] = kept
    return out


def parse_tagged(text: str) -> dict[str, list[dict]]:
    """Entry bullets from a packet's resume.tagged.md."""
    out: dict[str, list[dict]] = {}
    current = None
    for line in text.splitlines():
        if line.startswith("## "):
            current = None
        entry = _ENTRY_RE.match(line)
        if entry:
            current = entry.group(1)
            continue
        bullet = _BULLET_RE.match(line)
        if current and bullet:
            out.setdefault(current, []).append(
                {"text": bullet.group(1), "fact_ids": core.FACT_TAG_RE.findall(bullet.group(2))})
    return out


def promote(job_id: str, conn=None) -> dict:
    """Copy the bullets of a packet you approved into the bank. Idempotent."""
    profile = core.load_profile()
    d = core.job_dir(job_id, conn)
    tagged = d / "resume.tagged.md"
    if not tagged.exists():
        raise core.JobbotError(f"No packet for {job_id}: {tagged.name} is missing")
    entries = {e["id"]: e for e in profile.get("experience", []) + profile.get("projects", [])}
    bank = load()
    added = kept = 0
    for ref, bullets in parse_tagged(tagged.read_text(encoding="utf-8")).items():
        allowed = set(entries.get(ref, {}).get("facts", []))
        have = {_key(b["text"]) for b in bank.get(ref, [])}
        for b in bullets:
            if not set(b["fact_ids"]) <= allowed:
                continue  # the profile changed after this packet was written
            if _key(b["text"]) in have:
                kept += 1
                continue
            bank.setdefault(ref, []).append({**b, "approved_from": job_id,
                                             "approved_on": core.today()})
            have.add(_key(b["text"]))
            added += 1
    path().write_text(
        "# Wording you approved on a rendered resume (python jobbot.py approve JOB_ID).\n"
        "# Edit or delete freely. Facts live in profile.yaml; this file holds wording only.\n"
        + yaml.safe_dump({"entries": bank}, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8")
    core.log_decision("bank", job_id, "approved_wording", f"added {added}, already present {kept}")
    return {"added": added, "already_present": kept, "path": path()}


def status(content: dict, bank: dict[str, list[dict]]) -> list[dict]:
    """Per bullet in a drafted packet: is this wording approved, or new?"""
    rows = []
    for item in content.get("experience", []) + content.get("projects", []):
        known = {_key(b["text"]) for b in bank.get(item["ref_id"], [])}
        for b in item["bullets"]:
            rows.append({"ref_id": item["ref_id"], "text": b["text"],
                         "approved": _key(b["text"]) in known})
    return rows


def render_status(rows: list[dict]) -> str:
    new = [r for r in rows if not r["approved"]]
    lines = ["# Wording status", "",
             f"{len(rows) - len(new)} of {len(rows)} bullets reuse wording you already approved. "
             f"{len(new)} are new for this posting; read those against their cited facts first.",
             ""]
    if new:
        lines += ["## New wording (not yet approved)", ""]
        lines += [f"- [{r['ref_id']}] {r['text']}" for r in new]
        lines.append("")
    lines += ["## Approved wording reused", ""]
    lines += [f"- [{r['ref_id']}] {r['text']}" for r in rows if r["approved"]] or ["- none"]
    return "\n".join(lines) + "\n"
