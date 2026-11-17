"""Each outreach contact has >=2 independent public sources that agree on name and
company. Re-fetches the pages: the model's say-so is not evidence."""
import json
import ipaddress
import socket
import sys
import re
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import httpx  # noqa: E402
import tldextract  # noqa: E402

from checks._lib import cli, core, diagnostic  # noqa: E402

# Use the bundled Public Suffix List only; never fetch arbitrary suffix URLs.
_DOMAIN_EXTRACTOR = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None, include_psl_private_domains=True)

DISALLOWED = ("linkedin.com", "glassdoor.com", "dice.com")


def domain(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    parts = host.split(".")
    # Independent tenants publish on these shared hosting suffixes.
    if host.endswith(('.github.io', '.gitlab.io', '.pages.dev', '.netlify.app', '.vercel.app')):
        return '.'.join(parts[-3:])
    extracted = _DOMAIN_EXTRACTOR(host.rstrip('.'))
    return f'{extracted.domain}.{extracted.suffix}' if extracted.domain and extracted.suffix else host.rstrip('.')


def public_target(url: str) -> tuple[httpx.URL, str]:
    """Resolve once and pin requests to a validated public address."""
    target = httpx.URL(url)
    host = target.host
    if target.scheme not in ('http', 'https') or not host or target.userinfo:
        raise ValueError('Source must be a public HTTP(S) URL without credentials')
    if any(host == name or host.endswith('.' + name) for name in DISALLOWED):
        raise ValueError('Source domain is not permitted')
    addresses = socket.getaddrinfo(host, target.port or (443 if target.scheme == 'https' else 80),
                                   type=socket.SOCK_STREAM)
    ips = [ipaddress.ip_address(row[4][0]) for row in addresses]
    if not ips or any(not address.is_global or address.is_multicast for address in ips):
        raise ValueError('Source resolves to a non-public address')
    return target.copy_with(host=str(ips[0])), host


def public_page(url: str) -> tuple[str, str]:
    """Fetch bounded content, validating each redirect and bypassing env proxies.

    Pinning the connection's URL to the validated IP avoids resolving the host
    a second time. Preserve the original Host and TLS server name for HTTPS.
    """
    from agents.discover import UA
    with httpx.Client(timeout=20, trust_env=False, follow_redirects=False) as client:
        for _ in range(6):
            pinned, hostname = public_target(url)
            original = httpx.URL(url)
            host_header = original.netloc.decode('ascii')
            with client.stream('GET', pinned, headers={**UA, 'Host': host_header},
                               extensions={'sni_hostname': hostname}) as response:
                if response.is_redirect:
                    location = response.headers.get('location')
                    if not location:
                        raise ValueError('Redirect has no target')
                    url = str(original.join(location))
                    continue
                response.raise_for_status()
                chunks, size = [], 0
                for chunk in response.iter_bytes(chunk_size=65536):
                    size += len(chunk)
                    if size > 2_000_000:
                        raise ValueError('Source page exceeds size limit')
                    chunks.append(chunk)
                return b''.join(chunks).decode(response.encoding or 'utf-8', errors='replace'), url
    raise ValueError('Too many source redirects')


def confirmed_source(url: str, name: str, company: str) -> str | None:
    from agents.discover import html_to_text
    try:
        body, final_url = public_page(url)
    except (httpx.HTTPError, httpx.InvalidURL, ValueError, OSError):
        return None
    text = core.normalize(html_to_text(body))
    person, employer = core.normalize(name), core.normalize(company)
    def mentions(phrase):
        return bool(phrase) and re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text)
    return final_url if mentions(person) and mentions(employer) else None


def page_confirms(url: str, name: str, company: str) -> bool:
    return confirmed_source(url, name, company) is not None


def verified_sources(sources: list[str], name: str, company: str) -> list[str]:
    """Sources that are allowed, on distinct domains, and actually mention the person."""
    seen, ok = set(), []
    for url in sources:
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https") or not parsed.hostname:
                continue
            parsed.port  # validate malformed ports too
            dom = domain(url)
        except (ValueError, TypeError):
            continue
        if dom in seen or dom in DISALLOWED:
            continue
        final = confirmed_source(url, name, company)
        if final and domain(final) not in seen:
            seen.add(domain(final))
            ok.append(final)
    return ok


def check(d: Path) -> list[str]:
    bad = []
    for p in sorted(d.glob("outreach/*.json")):
        if p.name == "checks.json":
            continue
        c = json.loads(p.read_text())
        ok = verified_sources(c.get("sources", []), c["name"], c["company"])
        if len(ok) < 2:
            bad.append(diagnostic(f"only {len(ok)} independent source(s) confirm the contact",
                                  contact=c['name'], company=c['company'], file=p.stem))
    return bad


if __name__ == "__main__":
    cli(check, "contact_sources")
