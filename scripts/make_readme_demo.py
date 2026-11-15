"""Render the README's synthetic workflow animation (requires Pillow).

Run from any directory: python scripts/make_readme_demo.py
Uses DejaVu fonts from /usr/share/fonts/truetype/dejavu by default.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONTS = Path('/usr/share/fonts/truetype/dejavu')
BG, PANEL, BORDER = '#0b1120', '#121e32', '#29374e'
WHITE, MUTED, ACCENT = '#edf3ff', '#9cacbf', '#63e6be'

def font(size, mono=False, bold=False):
    name = 'DejaVuSansMono' if mono else 'DejaVuSans'
    return ImageFont.truetype(str(FONTS / (name + ('-Bold' if bold else '') + '.ttf')), size)

SCENES = [
    ('Start with verified experience', 'Your facts are the source material.',
     'profile.yaml', ['facts:', '  - id: F001', '    text: Built a perception pipeline', '    evidence: project report', '', 'skills:', '  - skill: Python', '    evidence: [F001]'],
     '01 / EVIDENCE', ['Record your contribution', 'Keep measured results in context', 'Identify disclosure boundaries']),
    ('Match the work to the role', 'Read the requirements before drafting.',
     'job description', ['Example Robotics', 'Perception Engineer', '', 'Requirements', '  Computer vision', '  Python and robotics software', '', 'Source: example posting'],
     '02 / FIT', ['Identify relevant experience', 'Separate gaps from unknowns', 'Quote explicit restrictions']),
    ('Prepare a tailored packet', 'Select evidence and adapt the wording.',
     'out/example_application/', ['resume.pdf', 'cover_letter.pdf  # when needed', 'answers.md', 'wording.md', 'changes.diff', '', 'Each role gets its own packet.'],
     '03 / DRAFT', ['Reuse approved bullet wording', 'Keep fact references for checks', 'Render readable documents']),
    ('Review before you apply', 'Inspect the documents and the findings.',
     'review artifacts', ['checks.json', 'review.md', 'panel.md', 'ats.json', '', 'Missing evidence stays a gap.', 'You make the final decision.'],
     '04 / REVIEW', ['Read seven reviewer perspectives', 'Inspect the actual PDF layout', 'Submit and record it yourself']),
]

def frame(scene, progress):
    img = Image.new('RGB', (1080, 600), BG)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((40, 30, 92, 82), radius=13, fill=ACCENT)
    d.text((51, 36), 'j', font=font(33, bold=True), fill=BG)
    d.text((108, 35), 'jobbot', font=font(29, bold=True), fill=WHITE)
    d.text((634, 46), 'WORKFLOW PREVIEW  /  SYNTHETIC DATA', font=font(12, mono=True), fill=MUTED)
    for i, label in enumerate(('Evidence', 'Fit', 'Draft', 'Review')):
        x = 40 + i * 255
        d.rounded_rectangle((x, 110, x + 235, 116), radius=3,
                            fill=ACCENT if i <= scene else BORDER)
        d.text((x, 129), f'0{i + 1}  {label}', font=font(14, bold=True),
               fill=WHITE if i == scene else MUTED)
    title, subtitle, file, lines, tag, bullets = SCENES[scene]
    d.text((40, 177), title, font=font(30, bold=True), fill=WHITE)
    d.text((40, 222), subtitle, font=font(17), fill=MUTED)
    d.rounded_rectangle((40, 270, 624, 548), radius=15, fill=PANEL, outline=BORDER)
    for x, color in ((62, '#ff8389'), (80, '#ffd37d'), (98, ACCENT)):
        d.ellipse((x, 287, x + 8, 295), fill=color)
    d.text((124, 281), file, font=font(14, mono=True), fill=MUTED)
    d.line((41, 312, 623, 312), fill=BORDER)
    for i, line in enumerate(lines):
        d.text((61, 328 + i * 25), line, font=font(15, mono=True),
               fill=ACCENT if line.startswith('  -') else WHITE)
    d.text((663, 285), tag, font=font(13, mono=True), fill=ACCENT)
    for i, line in enumerate(bullets):
        y = 338 + i * 54
        d.ellipse((664, y + 6, 670, y + 12), fill=ACCENT)
        d.text((684, y), line, font=font(16), fill=WHITE)
    d.rounded_rectangle((663, 509, 1038, 548), radius=9, outline=BORDER)
    d.text((677, 520), 'Evidence  >  Draft  >  Human decision', font=font(13), fill=MUTED)
    d.text((40, 571), 'Tailored applications. Traceable claims. Your review.', font=font(12), fill=MUTED)
    d.rounded_rectangle((812, 577, 1038, 581), radius=2, fill=BORDER)
    d.rounded_rectangle((812, 577, 812 + int(226 * progress), 581), radius=2, fill=ACCENT)
    return img

def main():
    output = ROOT / 'docs/assets/jobbot-workflow.gif'
    output.parent.mkdir(parents=True, exist_ok=True)
    frames, durations = [], []
    for scene in range(4):
        for step in range(8):
            frames.append(frame(scene, (scene + (step + 1) / 8) / 4))
            durations.append(250 if step < 7 else 1450)
    frames[0].save(output, save_all=True, append_images=frames[1:], duration=durations,
                   loop=0, optimize=True, disposal=1)
    print(f'{output.relative_to(ROOT)}: {output.stat().st_size:,} bytes')

if __name__ == '__main__':
    main()
