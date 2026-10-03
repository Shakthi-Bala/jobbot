# Eval cases

One folder per saved job description:

    <case>/posting.txt   the full job description text
    <case>/meta.yaml     company, title (location, req_id optional)
    <case>/notes.md      what a good packet looks like for this job

Run before and after a prompt or skill change:

    python jobbot.py eval run baseline
    # ...edit skills/...
    python jobbot.py eval run candidate
    python jobbot.py eval compare baseline candidate

Keep the change only if it wins and all checks still pass.
