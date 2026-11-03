---
name: master
description: Rewrite the whole CV into a master bullet bank, tagged by role family, that tailors instantly.
---

Build an evidence-backed bullet bank for robotics, perception, machine-learning and
reinforcement-learning roles. Preserve research problems, candidate contributions,
distinctive engineering constraints and supported results. The bank is source material
for later selection, not an instruction to print every fact or maximize a keyword score.

## Keywords, honestly
Use conventional terminology where it explains supported work. Every method, tool,
scope and outcome must be supported by cited facts. Keyword diagnostics do not establish
an employer's screening rules or justify adding repetitive labels. Do not claim unsupported skills.

## Bullets
- Cover useful evidence under the entry whose `facts` list contains it. Related facts
  can support one coherent contribution; do not force each fact into a separate chore.
  `fact_ids` must come from that entry. Selection for a one-page resume happens later.
- Explain the problem or delivered capability, owned component and method, with a
  result when supported. Usually one or two rendered lines; do not sacrifice meaning
  to an arbitrary word count. Preserve useful payload, hardware and environment context.
- Lead with the strongest relevant evidence, which may be a capability or difficult
  constraint rather than a number. Distinguish coverage counts from outcomes. Copy
  numbers exactly; a null metric means no number. Preserve measurement boundaries,
  baselines and material evaluation limits.
- Preserve team credit. Planned submissions are not publications, and confidential
  results remain private. Respect the profile's disclosure constraints.
- No "responsible for", "worked on", "helped", "various", "cutting-edge".
- Write alternates when a fact serves two role families differently (e.g. the PPO work
  framed for RL vs for robotics software).
- `families`: perception, rl (reinforcement / robot learning), robotics_swe (robotics
  software, planning, manipulation, autonomy), ml (ML engineering / deployment).
- `priority`: 1 for the bullet that should lead that entry, then 2, 3...

## Summaries (one per family)
Only include summaries when enabled by the candidate's preferences; otherwise return
an empty summaries list. A useful summary adds specific context beyond the entries,
not a formulaic collection of keywords and numbers. Cite every claim.

## Families
For each family give a label, the experience and project IDs to show in order (most
relevant first, at most 3 projects), and the skill categories to print.
