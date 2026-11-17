"""Publish a real offline-demo recording and PDF previews (Pillow + PDFium/Poppler).

Run `python jobbot.py demo`, then `python scripts/make_readme_demo.py`.
Only the explicitly synthetic demo workspace is accepted as input.
"""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import textwrap

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'docs/assets'
FONTS = Path('/usr/share/fonts/truetype/dejavu')
BG, PANEL, BORDER = '#0b1120', '#121e32', '#29374e'
WHITE, MUTED, ACCENT = '#edf3ff', '#a6b5c9', '#63e6be'
WIDTH, HEIGHT = 840, 600


def font(size, mono=False, bold=False):
    name = 'DejaVuSansMono' if mono else 'DejaVuSans'
    return ImageFont.truetype(str(FONTS / (name + ('-Bold' if bold else '') + '.ttf')), size)


def canvas(title):
    image = Image.new('RGB', (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    draw.text((26, 19), 'jobbot', font=font(29, bold=True), fill=WHITE)
    label = 'OFFLINE WALKTHROUGH'
    label_font = font(14, mono=True)
    x = WIDTH - 26 - draw.textlength(label, font=label_font)
    draw.text((x, 31), label, font=label_font, fill=ACCENT)
    draw.text((26, 65), title, font=font(18), fill=WHITE)
    draw.text((26, 570), 'Synthetic data  /  Recorded fixture answers  /  No API calls',
              font=font(15), fill=MUTED)
    return image


def terminal(event, typed, output_lines):
    image = canvas('A real CLI run, from job description to review queue')
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((26, 108, 814, 548), radius=14, fill=PANEL, outline=BORDER)
    for x, color in ((46, '#ff8389'), (64, '#ffd37d'), (82, ACCENT)):
        draw.ellipse((x, 127, x + 8, 135), fill=color)
    draw.text((110, 121), 'terminal  /  jobbot.py', font=font(14, mono=True), fill=MUTED)
    draw.line((27, 153, 813, 153), fill=BORDER)
    command = '$ ' + event['command'][:typed]
    lines = [(line, ACCENT) for line in textwrap.wrap(command, width=81)]
    outputs = event['output'].strip().splitlines()[:output_lines]
    for line in outputs:
        lines += [(part, WHITE) for part in (textwrap.wrap(line, width=81) or [''])]
    for i, (line, color) in enumerate(lines[-15:]):
        draw.text((45, 174 + i * 23), line, font=font(15, mono=True), fill=color)
    return image


def pdf_frame(page, bottom=False):
    image = canvas('The actual rendered resume  /  ' + ('lower page' if bottom else 'upper page'))
    scaled = page.resize((788, round(page.height * 788 / page.width)), Image.Resampling.LANCZOS)
    ink = scaled.convert('L').point(lambda pixel: 255 if pixel < 225 else 0).getbbox()
    content_end = ink[3] if ink else scaled.height
    offset = max(0, content_end - 418) if bottom else 0
    image.paste(scaled.crop((0, offset, 788, offset + 438)), (26, 108))
    return image


def panel_frame(panel, checks):
    image = canvas(f"Final panel report  /  round {panel['round']}  /  fixture scores")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((26, 108, 814, 548), radius=14, fill=PANEL, outline=BORDER)
    draw.text((47, 128), f"Checks: {len(checks)} passed  |  Hiring manager: {panel['hiring_manager']}",
              font=font(19, bold=True), fill=ACCENT)
    labels = {'team_lead': 'Team lead', 'competing_applicant': 'Competing applicant',
              'ceo': 'CEO', 'senior_engineer': 'Senior engineer', 'recruiter': 'Recruiter'}
    for i, (key, label) in enumerate(labels.items()):
        y = 187 + i * 47
        draw.text((48, y), label, font=font(20), fill=WHITE)
        draw.text((676, y), f"{panel['reviews'][key]['score']:.1f}/10", font=font(20, mono=True), fill=WHITE)
    draw.text((48, 455), 'Evidence gap: validation on a real robot', font=font(18), fill=MUTED)
    draw.text((48, 498), 'You inspect the PDF and decide whether to apply.', font=font(17), fill=WHITE)
    return image


def revision_frame(revision, after=False):
    title = 'Round 2: writer applies the supported edit' if after else 'Round 1: reviewer flags vague ownership'
    image = canvas(title)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((26, 108, 814, 548), radius=14, fill=PANEL, outline=BORDER)
    label = 'AFTER / explicit implementation' if after else 'BEFORE / vague contribution'
    draw.text((47, 131), label, font=font(20, bold=True), fill=ACCENT)
    bullet = revision['after' if after else 'before']
    for i, line in enumerate(textwrap.wrap(bullet['text'], width=61)):
        draw.text((47, 183 + i * 29), line, font=font(20), fill=WHITE)
    draw.text((47, 294), 'Supported revision' if after else 'Reviewer feedback',
              font=font(18, bold=True), fill=ACCENT)
    note = revision['instruction'] if after else revision['critique']['why'].removeprefix('DEMO FIXTURE: ')
    for i, line in enumerate(textwrap.wrap(note, width=73)):
        draw.text((47, 333 + i * 27), line, font=font(17), fill=WHITE)
    draw.text((47, 490), 'Same F001 evidence and synthetic evaluation scope.',
              font=font(17), fill=MUTED)
    return image


def main():
    latest = json.loads((ROOT / 'out/demo/latest.json').read_text())
    if not latest.get('synthetic_data') or latest.get('network_calls') is not False:
        raise SystemExit('Only an offline synthetic demo can be published')
    workspace, packet = Path(latest['workspace']), Path(latest['packet'])
    if not workspace.resolve().is_relative_to((ROOT / 'out/demo').resolve()):
        raise SystemExit('Demo workspace must be inside out/demo')
    recording = json.loads((workspace / 'demo-recording.json').read_text())
    checks = json.loads((packet / 'checks.json').read_text())
    rounds = json.loads((packet / 'panel.json').read_text())
    panel = rounds[-1]
    revision = recording['revision']
    assert revision and revision['rounds'] == [1, 2] and len(rounds) == 2
    assert rounds[0]['revisions'] and not rounds[1]['revisions']
    assert revision['critique'] == rounds[0]['reviews']['senior_engineer']['lines_that_hurt'][0]
    assert revision['after']['text'] in json.loads((packet / 'resume.json').read_text())['projects'][0]['bullets']
    assert revision['after_sha256'] == hashlib.sha256((packet / 'resume.pdf').read_bytes()).hexdigest()
    assert checks and all(not errors for errors in checks.values())
    assert 'DEMO FIXTURE' in panel['reviews']['ats_gate']['reason']
    from pypdf import PdfReader
    assert len(PdfReader(packet / 'resume.pdf').pages) == 1
    ASSETS.mkdir(parents=True, exist_ok=True)
    shutil.copy(packet / 'resume.pdf', ASSETS / 'example-resume.pdf')
    shutil.copy(packet / 'checks.json', ASSETS / 'example-checks.json')
    (ASSETS / 'example-panel.md').write_text(
        '# Recorded demo panel\n\nThese are stored fixture responses, not actual model, human, or employer ratings. '
        'The CLI produced this report while running the synthetic offline example.\n\n'
        + (packet / 'panel.md').read_text())
    (ASSETS / 'demo-recording.json').write_text(json.dumps(recording, indent=2) + '\n')
    staging = ROOT / 'out/readme_recording'
    staging.mkdir(parents=True, exist_ok=True)
    if shutil.which('pdftoppm'):
        subprocess.run(['pdftoppm', '-f', '1', '-singlefile', '-scale-to', '1100', '-png',
                        str(packet / 'resume.pdf'), str(staging / 'resume')], check=True, capture_output=True)
    else:
        import pypdfium2
        document = pypdfium2.PdfDocument(packet / 'resume.pdf')
        page = document[0]
        bitmap = page.render(scale=1100 / max(page.get_size()))
        bitmap.to_pil().save(staging / 'resume.png')
        bitmap.close()
        page.close()
        document.close()
    shutil.copy(staging / 'resume.png', ASSETS / 'example-resume.png')
    page = Image.open(staging / 'resume.png').convert('RGB')
    frames, durations = [], []
    # Play actual recorded commands and output. Paused tasks were fulfilled with
    # the committed fixtures by the demo runner; no model session is simulated.
    for name in ('init', 'add-jd', 'packet', 'checks'):
        event = next(e for e in reversed(recording['events'])
                     if f'jobbot.py {name}' in e['command'] and e['exit_code'] == 0)
        for step in range(1, 9):
            frames.append(terminal(event, round(len(event['command']) * step / 8), 0))
            durations.append(70)
        count = len(event['output'].strip().splitlines())
        for line in range(1, count + 1):
            frames.append(terminal(event, len(event['command']), line))
            durations.append(110)
        frames.append(terminal(event, len(event['command']), count))
        durations.append(2200)
        if name == 'packet':
            frames += [revision_frame(revision), revision_frame(revision, after=True)]
            durations += [7500, 6500]
    frames += [pdf_frame(page), pdf_frame(page, bottom=True), panel_frame(panel, checks)]
    durations += [3000, 3000, 4000]
    gif = ASSETS / 'jobbot-workflow.gif'
    frames[0].save(gif, save_all=True, append_images=frames[1:], duration=durations,
                   loop=0, optimize=True, disposal=1)
    frames[-1].save(staging / 'panel-preview.png')
    frames[12].save(staging / 'terminal-preview.png')
    revision_frame(revision).save(staging / 'review-before.png')
    revision_frame(revision, after=True).save(staging / 'review-after.png')
    manifest_path = ASSETS / 'public-assets.json'
    manifest = json.loads(manifest_path.read_text())
    for path in (gif, ASSETS / 'example-resume.png'):
        key = path.relative_to(ROOT).as_posix()
        entry = manifest.setdefault(key, {'sha256': [], 'description': 'Reviewed fictional offline demo output.'})
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest not in entry['sha256']:
            entry['sha256'].append(digest)
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'Recorded {len(frames)} frames, {sum(durations)/1000:.1f}s, {gif.stat().st_size:,} bytes')
    print('Published fictional PDF, preview, check results, panel report, and sanitized transcript.')


if __name__ == '__main__':
    main()
