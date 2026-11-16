# README animation

`jobbot-workflow.gif` plays actual offline CLI output, shows the rendered example résumé, and presents the generated panel report. All candidate data is fictional. Review answers and scores are recorded fixtures, not actual model, human, or employer assessments.

The PDF, PNG preview, check results, and panel Markdown come from the same isolated demo run. `demo-recording.json` contains its captured CLI output with local workspace paths replaced by `<demo>`.

To regenerate the artifacts:

```bash
python -m pip install -r requirements-dev.txt
python jobbot.py demo
python scripts/make_readme_demo.py
```

The generator uses system DejaVu fonts and PDFium, or Poppler when available. These are documentation-build tools; they are not required for the application workflow. Inspect the output before accepting its hashes in `public-assets.json`. Changed or unrecognized binary assets require review during the privacy scan.
