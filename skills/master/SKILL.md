---
name: master
description: Rewrite the whole CV into a master bullet bank, tagged by role family, that tailors instantly.
---

1. Act as a senior technical recruiter for robotics, perception, machine-learning and
   reinforcement-learning roles, and add the exact keywords ATS systems match on, so a
   tailored resume can score 90+ on keyword coverage.
2. Rewrite the CV into a master template the candidate can tailor instantly.

## Keywords, honestly
Use the exact industry spellings ATS systems search for ("Reinforcement Learning",
"PPO", "Sim-to-Real Transfer", "ROS 2", "MoveIt", "NVIDIA Isaac Lab", "Computer Vision",
"Monocular Depth Estimation", "ONNX Runtime"...), but **only for things a cited fact
proves**. A keyword the profile can't back is a gap, never a bullet. A 90+ score built on
claims that fail the interview is worth nothing.

## Bullets
- Every fact in the profile gets at least one bullet, under the entry whose `facts` list
  contains it. `fact_ids` must come from that entry.
- Form: strong verb + what + how (tools, as keywords) + result (number from the fact).
  One line where possible, two at most (about 25 words).
- Lead with the result when there is a number. Copy numbers exactly; a null metric
  means no number.
- No "responsible for", "worked on", "helped", "various", "cutting-edge".
- Write alternates when a fact serves two role families differently (e.g. the PPO work
  framed for RL vs for robotics software).
- `families`: perception, rl (reinforcement / robot learning), robotics_swe (robotics
  software, planning, manipulation, autonomy), ml (ML engineering / deployment).
- `priority`: 1 for the bullet that should lead that entry, then 2, 3...

## Summaries (one per family)
Two lines, about 40 words: degree + school + graduation (from education), the 3-4
strongest keywords that family hires for, and one or two hard numbers. Cite everything.

## Families
For each family give a label, the experience and project IDs to show in order (most
relevant first, at most 3 projects), and the skill categories to print.
