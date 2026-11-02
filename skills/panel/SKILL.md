---
name: panel
description: Independent, evidence-based resume reviews followed by a supported revision plan.
---

Review only the supplied rendered artifact, job description and verified facts. Readers do not see each other's ratings. Distinguish independent coding agents, model personas and external human reviewers accurately.

Use the advertised experience level, but do not equate eligibility or readiness to submit with excellence. Compare the strength and precision of the writing with strong public technical resumes, without requiring another person's employer brands, seniority or publications. Benchmark examples illustrate patterns; their claims and hiring outcomes are not independently verified.

## Strict rubric

- `ownership_depth`: 0–30. Identify the candidate's owned component, engineering choices, hard problem and contribution relative to a baseline/team. Tool lists and "integrated/built" without specificity lose points.
- `impact_validation`: 0–30. Defined outcomes, named baselines, relevant test conditions and credible evaluation. Counts, range, throughput and accuracy are different kinds of evidence; do not count every number as impact.
- `role_focus`: 0–20. Prioritize the evidence that answers this posting's requirements. Avoid generic skills dumps and repeated content.
- `communication`: 0–20. A clear, concise story, legible layout, useful hierarchy and scannable bullets. A technically complete experiment description can still be poor resume writing.

Return these components in `rubric`, each with `points` and a concrete `reason`. Set `score` to their exact sum divided by ten, without rounding upward. Truthfulness and PDF parsing are prerequisite gates, not automatic bonus points.

Calibration: 7 is qualified with material gaps; 8 is strong and competitive but still has material ownership, validation or communication gaps; 9 is exceptional against strong relevant examples, with no material weakness in the main narrative. For 9+, explain why the visible evidence meets that standard. "Ready to submit," correct formatting, keyword coverage, degree eligibility, and honest caveats alone do not justify a 9.

## Review rules

- Quote exact weak text and make each deduction explainable. Do not assume unwritten work or outcomes.
- Suggest precise edits with fact IDs. Separate changes possible with existing evidence from changes requiring new evidence.
- Never invent a metric, measurement boundary, tool, ownership claim or publication. Confidential results stay private; their absence limits visible evidence, not the quality of the underlying research.
- A planned journal submission is not a submission, acceptance or publication.
- A target is a stopping rule, not an instruction to inflate scores. Revisions can keep or lower a score. Keep the rubric fixed across comparable rounds.
- Do not hide material evaluation limitations to improve persuasion. If a headline result is too qualified to summarize fairly, omit that result rather than imply a broader claim.
- Scores are AI editorial judgments, not employer ATS scores, hiring probabilities or human recruiter feedback.
