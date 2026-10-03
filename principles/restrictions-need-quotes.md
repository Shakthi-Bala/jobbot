## restrictions-need-quotes

**Rule:** A restriction exists only if it can be quoted verbatim from the posting.

Citizenship, export control, clearance, sponsorship, location or degree restrictions must come with the exact sentence from the posting. Paraphrases and inferences ("defense company, so probably citizens only") are not restrictions; they are unknowns.

_Enforced by:_ `checks/restriction_quotes.py`; fit and discovery drop any quote not found in `jobs.raw_text`.
