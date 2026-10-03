---
name: unslop
description: Remove filler and AI-sounding phrasing from prose without changing its claims.
---

Rewrite each paragraph so it sounds like a specific person wrote it. Return the same
number of paragraphs, in order, each with the same `fact_ids` (you may drop IDs, never add).

Remove:
- Banned phrases and their variants.
- Openers like "I am writing to express my interest", "I am excited to apply".
- Inflated adjectives: passionate, cutting-edge, innovative, seamless, robust (unless technical),
  dynamic, results-driven, world-class.
- Hedged filler: "I believe", "I feel that", "it is worth noting".
- Triplets of vague nouns, and em-dash chains.
- Closing clichés: "I look forward to the opportunity to contribute".

Keep every concrete fact, number and name exactly as written. Do not add claims. Prefer
shorter sentences and active verbs. If a paragraph is already plain, return it unchanged.
