# README animation

`jobbot-workflow.gif` is an illustrated workflow with synthetic example content. It contains no screenshots, candidate information, credentials, model scores, or claims of a successful application.

The four scenes show verified evidence, job fit, document drafting, and human review. The main README also describes these steps in text.

To regenerate it, install Pillow in a development environment and run:

```bash
python scripts/make_readme_demo.py
```

The generator uses system DejaVu fonts. Pillow is a documentation-build dependency; it is not required to run jobbot. Submit animation rendering through the scheduler on shared clusters.
