"""Each outreach contact has >=2 independent public sources that agree on name and
company. Re-fetches the pages: the model's say-so is not evidence."""
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import httpx  # noqa: E402

from checks._lib import cli, core  # noqa: E402

DISALLOWED = ("linkedin.com", "glassdoor.com", "dice.com")


def domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def page_confirms(url: str, name: str, company: str) -> bool:
    from agents.discover import UA, html_to_text
    try:
        r = httpx.get(url, headers=UA, timeout=20, follow_redirects=True)
        r.raise_for_status()
    except httpx.HTTPError:
        return False
    text = core.normalize(html_to_text(r.text))
    last = core.normalize(name).split()[-1] if name.split() else ""
    return core.normalize(name) in text or (last and last in text
                                              and core.normalize(company) in text)


def verified_sources(sources: list[str], name: str, company: str) -> list[str]:
    """Sources that are allowed, on distinct domains, and actually mention the person."""
    seen, ok = set(), []
    for url in sources:
        dom = domain(url)
        if dom in seen or any(dom.endswith(x) for x in DISALLOWED):
            continue
        if page_confirms(url, name, company):
            seen.add(dom)
            ok.append(url)
    return ok


def check(d: Path) -> list[str]:
    bad = []
    for p in sorted(d.glob("outreach/*.json")):
        c = json.loads(p.read_text())
        ok = verified_sources(c.get("sources", []), c["name"], c["company"])
        if len(ok) < 2:
            bad.append(f"{p.stem}: only {len(ok)} independent source(s) confirm "
                       f"{c['name']} at {c['company']}")
    return bad


if __name__ == "__main__":
    cli(check, "contact_sources")
