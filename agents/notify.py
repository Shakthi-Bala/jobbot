"""Explicit Discord updates, optionally with a demo GIF/video attachment.

The webhook lives in DISCORD_WEBHOOK_URL or the gitignored .env file.
Never include the profile, resume, contact details, or credentials in updates.

    python -m agents.notify "Title" "Body" [--field "Name=Value"] [--file demo.gif]
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import time
from contextlib import ExitStack
from pathlib import Path

import httpx

from . import core

MAX_ATTACHMENT_BYTES = 8 * 1024 * 1024
WEBHOOK_PATH = re.compile(r"/api(?:/v\d+)?/webhooks/\d+/[\w.-]+$")


def webhook_url() -> str | None:
    if os.environ.get("DISCORD_WEBHOOK_URL"):
        return os.environ["DISCORD_WEBHOOK_URL"].strip()
    env = core.ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            key, _, value = line.partition("=")
            if key.strip() in ("DISCORD_WEBHOOK_URL", "export DISCORD_WEBHOOK_URL"):
                return value.strip().strip("\"'")
    return None


def _embed(title: str, body: str, fields: dict[str, str], color: int) -> dict:
    # Discord limits both each component and the total characters across embeds.
    title, body = title[:256], body[:4000]
    remaining = 6000 - len(title) - len(body)
    items = []
    for key, value in list(fields.items())[:25]:
        key = str(key)[:min(256, remaining)]
        remaining -= len(key)
        value = str(value)[:min(1024, remaining)]
        remaining -= len(value)
        if key and value:
            items.append({"name": key, "value": value, "inline": False})
    return {"title": title, "description": body, "color": color, "fields": items}


def post(title: str, body: str = "", fields: dict[str, str] | None = None,
         color: int = 0x3B82F6, attachment: Path | str | None = None) -> bool:
    url = webhook_url()
    if not url:
        core.warn("DISCORD_WEBHOOK_URL not set; skipping Discord update")
        return False
    try:
        target = httpx.URL(url)
        if (target.scheme != "https" or target.host != "discord.com"
                or target.userinfo or not WEBHOOK_PATH.fullmatch(target.path)):
            core.warn("Invalid Discord webhook URL; update skipped")
            return False
        target = target.copy_set_param("wait", "true")
    except httpx.InvalidURL:
        core.warn("Invalid Discord webhook URL; update skipped")
        return False
    path = Path(attachment) if attachment is not None else None
    if path and (path.suffix.lower() not in (".gif", ".mp4", ".webm", ".mov", ".png", ".jpg", ".jpeg")
                 or not path.is_file() or path.stat().st_size > MAX_ATTACHMENT_BYTES):
        core.warn("Discord attachment must be an existing media file within the 8 MiB local limit")
        return False
    payload = {"username": "jobbot", "allowed_mentions": {"parse": []},
               "embeds": [_embed(title, body, fields or {}, color)]}
    for attempt in range(3):
        try:
            with ExitStack() as stack:
                if path:
                    files = {"files[0]": (path.name, stack.enter_context(path.open("rb")),
                                         mimetypes.guess_type(path.name)[0] or "application/octet-stream")}
                    r = httpx.post(target, data={"payload_json": json.dumps(payload)},
                                   files=files, timeout=20)
                else:
                    r = httpx.post(target, json=payload, timeout=20)
        except (httpx.HTTPError, OSError) as e:
            # Exception messages may contain the secret URL. Log only their type.
            core.warn(f"Discord delivery failed ({type(e).__name__})")
            return False
        if r.status_code == 429 and attempt < 2:
            try:
                delay = float(r.json().get("retry_after", 1))
            except (ValueError, TypeError, AttributeError):
                delay = 1
            if not 0 <= delay <= 10:
                break
            time.sleep(delay)
            continue
        if 200 <= r.status_code < 300:
            return True
        break
    core.warn(f"Discord post failed (HTTP {r.status_code})")
    return False


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("title")
    p.add_argument("body", nargs="?", default="")
    p.add_argument("--field", action="append", default=[], help="Name=Value")
    p.add_argument("--file", type=Path, help="Explicit attachment: demo GIF, video, or image")
    a = p.parse_args()
    if any("=" not in f for f in a.field):
        p.error("--field must be Name=Value")
    fields = dict(f.split("=", 1) for f in a.field)
    raise SystemExit(0 if post(a.title, a.body, fields, attachment=a.file) else 1)


if __name__ == "__main__":
    main()
