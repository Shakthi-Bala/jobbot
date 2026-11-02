# Independent resume review loop

Use the advertised job and a fixed rubric, rather than adjusting the rubric to reach a requested score. Keep all candidate facts and output artifacts in ignored local directories.

1. Render the resume, extract its text, and run document checks. On shared clusters, use `sbatch` for rendering and tests.
2. Give each independent reviewer the same PDF, actual page preview, text, job description, and verified facts. Keep other reviewers' reports and scores hidden until the round is complete.
3. Use the panel rubric: ownership/engineering depth 30, visible impact/validation 30, role focus 20, communication 20. Review at the advertised experience level. A score is an AI editorial judgment, not an employer ATS result or hiring probability.
4. Preserve each raw review. Record the exact PDF hash with the round, scores, rubric components, and technical check results.
5. Merge supported edits, resolving conflicts without inventing evidence. Version the content and rendered artifact. Commit reusable source changes after their relevant checks pass; do not commit private resume files to satisfy a request for frequent commits.
6. Have reviewers inspect and rescore the new rendered artifact. They may keep or lower their scores. Do not reuse ratings from a different PDF or round up a sub-threshold rating.
7. Stop when each required reviewer meets the requested score and document checks pass. If the remaining barrier requires new evidence, retain the honest scores and identify that evidence rather than manufacture a passing rating.

In the built-in panel, set `preferences.panel_min_score: 9.0` to require every registered reader to reach 9.0, with a passing ATS persona and an interview verdict from the hiring-manager persona. An editor flag or high average cannot bypass an individual failure. The built-in panel has a bounded revision loop; after its limit, unresolved issues require attention instead of being labeled ready.

Separately tasked coding agents can serve as independent reviewers during an interactive editing session. Identify those reviewers accurately and distinguish them from the built-in model personas and external human reviewers. Fractional ratings are supported. Retain the round history and publish a score table alongside the final PDF.

## Strict calibration and external examples

Enable `preferences.panel_strict_rubric: true` to require explained component scores whose exact sum agrees with the overall score. Correctness and parseability are gates rather than free points. Seven means qualified with material gaps; eight is competitive with material evidence or communication gaps; nine requires an exceptional main narrative, not simply eligibility or readiness. Preserve earlier reviews under their original rubric instead of comparing scores across changed scales as if they were equivalent.

Public examples to inspect, not copy: [Ruijie Fu’s perception resume](https://ruijiefu.com/pdfs/matic_most_recent_resume_RF.docx.pdf) makes component ownership, performance comparators and regression testing concrete; [Jason Liu’s robotics CV](https://jasonjzliu.com/data/main_page/Jason%20Liu%20Resume%202024-05-01.pdf) names owned software components and their validation. Their experience levels and document lengths differ; neither establishes a required employer brand, publication count or seniority for another candidate. These are self-published claims, not verified hiring outcomes.

[MIT CAPD](https://capd.mit.edu/resources/resumes/) emphasizes specific methods and accomplishments. [CMU’s graduate resume guide](https://www.cmu.edu/career/documents/sample-resumes-cover-letters/graduate_student_resume_guide_2026.pdf) supports concise, relevant, one-column graduate resumes. Borrow communication patterns only. Never import another person’s achievements or disclose confidential results to raise a rating.
