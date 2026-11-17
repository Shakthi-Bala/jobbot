"""Extract annual USD base pay, classifying each range independently.

Component labels and currencies belong to the range beside them. A benefit
mentioned elsewhere in the posting cannot suppress or widen the base range.
"""
from __future__ import annotations
import re

_CODES = r'USD|CAD|AUD|NZD|SGD|HKD|EUR|GBP|CHF|JPY|CNY|INR'
_CURRENCY = rf'(?:US\$|CA\$|C\$|AU\$|A\$|NZ\$|SG\$|HK\$|(?:{_CODES})\s*\$?|[$£€])'
_MONEY = r'(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?'
_RANGE = re.compile(
    rf'(?<![\w.,])(?P<c1>{_CURRENCY})?\s*(?P<lo>{_MONEY})\s*(?P<lk>[kK])?'
    rf'\s*(?P<middle>{_CODES})?\s*(?:-|–|—|to)\s*'
    rf'(?P<c2>{_CURRENCY})?\s*(?P<hi>{_MONEY})(?:[ \t]*(?P<hk>[kK]))?'
    rf'[ \t]*(?:[\[(][ \t]*(?P<bracket>{_CODES})[ \t]*[\])]|(?P<end>{_CODES})\b)?', re.I)
_CLAUSE = re.compile(r'[;,+\n]|\.(?!\d)')
_BASE = re.compile(r'\b(?:base(?:\s+(?:salary|pay|compensation))?|salary|wages?)\b', re.I)
_TOTAL = re.compile(r'\b(?:total\s+compensation|ote|on[- ]target\s+earnings)\b', re.I)
_NONBASE = re.compile(
    r'\b(?:bonus(?:es)?|stipends?|allowances?|reimbursements?|rsus?|equity|stock|'
    r'ote|on[- ]target(?:\s+earnings)?|total\s+compensation)\b', re.I)
_CURRENCY_WORD = re.compile(rf'(?<!\w)({_CODES}|Canadian dollars?|Australian dollars?)(?!\w)', re.I)


def _currency(tag: str, default: str) -> str:
    tag = tag.upper().replace(' ', '')
    if tag == '$':
        return default.upper()
    return 'USD' if tag.startswith(('US$', 'USD')) else tag


def _component(prefix: str, suffix: str) -> tuple[str, str]:
    before = _CLAUSE.split(prefix)[-1]
    after = _CLAUSE.split(suffix)[0]
    after = re.split(r'\b(?:plus|and|with|alongside)\b', after, maxsplit=1, flags=re.I)[0]
    return before, after


def _is_base(prefix: str, suffix: str) -> bool:
    # Excluded benefits do not own the preceding amount. A total-compensation
    # label, however, stays total even if its explanation mentions base pay.
    suffix = re.split(r'\b(?:excluding|exclusive\s+of|not\s+including|without)\b',
                      suffix, maxsplit=1, flags=re.I)[0]
    if _TOTAL.search(prefix):
        return False
    if _BASE.search(prefix):
        return True
    if _TOTAL.search(suffix):
        return False
    if _BASE.search(suffix):
        return True
    # "bonus eligible" describes benefits, not the ownership of an amount.
    suffix = re.sub(r'\bbonus\s+eligible\b', '', suffix, flags=re.I)
    return not (_NONBASE.search(prefix) or _NONBASE.search(suffix))


def _usd(match, prefix: str, suffix: str, default: str) -> bool:
    tags = [match[name] for name in ('c1', 'c2', 'middle', 'bracket', 'end')]
    # Explicit markers beside a bare-dollar range override its default currency.
    before = list(_CURRENCY_WORD.finditer(prefix))
    if before and re.fullmatch(r'[\s:)\]]*', _BASE.sub('', prefix[before[-1].end():])):
        tags.append(before[-1][1])
    after = _CURRENCY_WORD.match(suffix.lstrip(' \t\r\n(['))
    if after:
        tags.append(after[1])
    explicit = [tag for tag in tags if tag and tag != '$']
    if explicit:
        return all(_currency(tag, default) == 'USD' for tag in explicit)
    return _currency(match['c1'] or '$', default) == 'USD'


def _ranges(text: str):
    """Reject unanchored candidates without consuming a later real pay range."""
    offset = 0
    while (match := _RANGE.search(text, offset)) is not None:
        has_code = any(match[name] for name in ('middle', 'bracket', 'end')) or re.search(
            r'[A-Za-z]', match['c2'] or '')
        if not match['c1'] and not has_code:
            offset = match.start() + 1
            continue
        if not match['c1'] and match['c2']:
            # In "Level 2 - $150k USD - $180k USD", the second endpoint
            # starts the salary range; the leading 2 is a table label.
            anchored = _RANGE.match(text, match.start('c2'))
            if anchored and anchored['c1'] and anchored.end() > match.end():
                match = anchored
        yield match
        offset = match.end()


def parse_pay_text(text: str, *, hours_per_year: int = 2080, default_currency: str = 'USD') -> tuple[int, int] | None:
    # Bare numerical ranges are not salary evidence. A marker can occur at
    # either endpoint, including a trailing-only or bracketed currency code.
    matches = list(_ranges(text or ''))
    lows, highs = [], []
    for i, match in enumerate(matches):
        raw_after = text[match.end():]
        if re.match(r'\s*(?:mm|mil|million|billion|[mb])\b(?![-/.&])', raw_after, re.I):
            continue
        left = matches[i - 1].end() if i else 0
        right = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        prefix, suffix = _component(text[left:match.start()], text[match.end():right])
        if not _usd(match, prefix, suffix, default_currency) or not _is_base(prefix, suffix):
            continue
        lo = float(match['lo'].replace(',', '')) * (1000 if match['lk'] else 1)
        hi = float(match['hi'].replace(',', '')) * (1000 if match['hk'] else 1)
        if match['hk'] and not match['lk'] and lo < 1000:
            lo *= 1000
        elif match['lk'] and not match['hk'] and hi < 1000:
            hi *= 1000
        monthly = (re.match(r'(?:USD\s*)?(?:per\s+month\b|/\s*(?:month|mo)\b|monthly\b)', suffix.strip(), re.I)
                   or re.search(r'monthly(?:\s+base)?(?:\s+(?:salary|pay))?\s*:?\s*$', prefix, re.I))
        if monthly and hi <= 30000:
            lo, hi = lo * 12, hi * 12
        elif hi < 1000 and (re.search(r'hour|/hr', prefix + suffix, re.I) or hi < 300):
            lo, hi = lo * hours_per_year, hi * hours_per_year
        if 20000 <= lo <= hi <= 2000000:
            lows.append(lo)
            highs.append(hi)
    return (int(min(lows)), int(max(highs))) if lows else None
