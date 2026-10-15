"""Post a short update to Discord. The webhook URL lives in .env (gitignored):

    DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

    python -m agents.notify "Title" "Body text" [--field "Name=Value" ...]

Never post contact details, the profile, or anything from data/.
"""
from __future__ import annotations

import argparse
import os

import httpx

from . import core


def webhook_url() -> str | None:
    if os.environ.get("DISCORD_WEBHOOK_URL"):
        return os.environ["DISCORD_WEBHOOK_URL"]
    env = core.ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            key, _, value = line.partition("=")
            if key.strip() == "DISCORD_WEBHOOK_URL":
                return value.strip()
    return None


def post(title: str, body: str = "", fields: dict[str, str] | None = None,
         color: int = 0x3B82F6) -> bool:
    url = webhook_url()
    if not url:
        core.warn("DISCORD_WEBHOOK_URL not set; skipping Discord update")
        return False
    embed = {"title": title[:256], "description": body[:4000], "color": color,
             "fields": [{"name": k[:256], "value": v[:1024], "inline": False}
                        for k, v in (fields or {}).items()][:25]}
    r = httpx.post(url + "?wait=true", json={"username": "jobbot", "embeds": [embed]},
                   timeout=20)
    if r.status_code >= 300:
        core.warn(f"Discord post failed: {r.status_code} {r.text[:200]}")
        return False
    return True


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("title")
    p.add_argument("body", nargs="?", default="")
    p.add_argument("--field", action="append", default=[], help="Name=Value")
    a = p.parse_args()
    fields = dict(f.split("=", 1) for f in a.field)
    raise SystemExit(0 if post(a.title, a.body, fields) else 1)


if __name__ == "__main__":
    main()
