# Offline demonstration fixtures

`answers.json` contains recorded responses for the CLI's structured task schemas.
Every claim refers to the fictional `data/profile.example.yaml` inventory.
Reader scores and verdicts are fixed examples, not model or human assessments.

Run `python jobbot.py demo` from the repository root. The runner creates a fresh
workspace under `out/demo/`, forces manual mode, and runs the real import,
writing, rendering, checks, and panel-report pipeline with these answers.
It does not call a model, fetch a posting, submit an application, or modify an
existing candidate profile or tracker.
