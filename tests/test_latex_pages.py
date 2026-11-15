import json

from agents import core, latex, tailor


def test_escape_specials_and_bold_percentages():
    assert latex.escape("R&D at 50% on C# _x_") == r"R\&D at \textbf{50\%} on C\# \_x\_"
    assert latex.escape("11×11 mask → depth") == r"11$\times$11 mask $\rightarrow$ depth"
    assert latex.escape(latex.Raw(r"\href{u}{x}")) == r"\href{u}{x}"
    assert latex.escape("2025–2027 — present") == r"2025\textendash{}2027 \textemdash{} present"


def test_measurement_units_stay_with_their_values():
    assert latex.escape('12 g sensor; 0.25 m error; 30 Hz; 3 s history') == '12~g sensor; 0.25~m error; 30~Hz; 3~s history'
    assert latex.escape('3 methods and 2 scenes') == '3 methods and 2 scenes'
    assert latex.escape('ROS 2 and ROS 1') == 'ROS~2 and ROS~1'
    assert latex.escape('0.120 px reprojection; 25.795 dB PSNR') == '0.120~px reprojection; 25.795~dB PSNR'


RESUME = {
    "person": {"name": "Alex Example", "email": "a@x.com", "phone": "", "location": "Boston, MA",
               "links": {"github": "https://github.com/alex", "scholar": ""}},
    "summary": "Built things & measured them.",
    "education": [{"school": "WPI", "degree": "M.S. Robotics", "dates": "Aug 2025 – May 2027",
                   "gpa": "4.0", "location": "", "details": []}],
    "skills": [{"category": "Project tools", "items": ["ROS 2", "C++"]}],
    "courses": ["Computer Vision"],
    "experience": [{"title": "Student Researcher", "org": "Example Lab", "dates": "Jan 2026 – Present",
                    "focus": "Stereo depth", "bullets": ["Cut error by 30%"],
                    "heading": "", "location": "", "links": {}, "tools": []}],
    "projects": [{"heading": "Stereo VIO", "dates": "", "bullets": ["Sliding-window BA"],
                  "tools": ["C++", "Eigen"], "links": {"repo": "https://github.com/alex/vio_#1"}}],
}


def test_tex_has_their_structure_and_escapes(tmp_path):
    tex = latex.render_tex(RESUME, tmp_path / "resume.tex").read_text()
    assert r"\usepackage{charter}" in tex and r"\newcommand{\place}" in tex
    assert r"\section{RESEARCH EXPERIENCE}" in tex          # every role is a research role
    assert r"\place{Research Focus: Stereo depth}" in tex
    assert r"\textbf{Tools: C++, Eigen.}" in tex                 # per-project tools line
    assert r"\textbf{Tools:} ROS~2, C++" in tex             # "Project tools" -> "Tools"
    assert r"\href{https://github.com/alex}{GitHub}" in tex
    assert r"vio\_\#1" not in tex and r"vio_\#1" in tex       # URL keeps '_', escapes '#'
    assert r"Cut error by \textbf{30\%}" in tex
    assert r"\section{SUMMARY}" not in tex                   # main.tex style has no summary
    assert tex.count("{") == tex.count("}")


class Job(dict):
    pass


def job(title, text=""):
    return {"title": title, "raw_text": text}


def test_page_rule():
    auto = {"preferences": {"resume_pages": "auto"}}
    assert tailor.decide_pages(job("Perception Engineer"), {}, auto)[0] == 1
    assert tailor.decide_pages(job("AI Researcher - Robot Learning"), {}, auto)[0] == 2
    assert tailor.decide_pages(job("World Model Research Scientist"), {}, auto)[0] == 2
    assert tailor.decide_pages(job("ML Engineer", "Strong publication record is a plus"), {}, auto)[0] == 2
    assert tailor.decide_pages(job("AI Researcher"), {}, {"preferences": {"resume_pages": 1}})[0] == 1


def test_length_limit_follows_packet_pages(packet):  # noqa: D103
    from checks import length_limits
    meta = json.loads((packet / "meta.json").read_text())
    meta["pages"] = 2
    (packet / "meta.json").write_text(json.dumps(meta))
    assert not any("resume is" in p for p in length_limits.check(packet))


def test_compiler_rejects_silent_font_substitution(tmp_path, monkeypatch):
    import subprocess
    import pytest
    tex = tmp_path / 'resume.tex'
    tex.write_text('source')
    monkeypatch.setattr(latex, 'engine', lambda: '/tools/tectonic')
    def compile_with_missing_font(*args, **kwargs):
        tex.with_suffix('.pdf').write_bytes(b'pdf')
        tex.with_suffix('.log').write_text("LaTeX Font Warning: Font shape `TU/bch/b/n' undefined")
        return subprocess.CompletedProcess(args[0], 0, stdout='', stderr='')
    monkeypatch.setattr(latex.subprocess, 'run', compile_with_missing_font)
    with pytest.raises(core.JobbotError, match='substituted a font'):
        latex.compile_pdf(tex)


def test_optional_summary_matches_pdf_metadata(packet, monkeypatch):
    import typst
    data_path = packet / 'resume.json'
    data = json.loads(data_path.read_text())
    meta_path = packet / 'meta.json'
    meta = json.loads(meta_path.read_text())
    meta.update(format='latex', show_summary=True)
    meta_path.write_text(json.dumps(meta))
    def compile_pdf(tex):
        path = tex.with_suffix('.pdf')
        typst.compile(b'= SUMMARY\nReal summary\n= EDUCATION\nSchool\n= SKILLS\nSkills', output=str(path))
        return path
    monkeypatch.setattr(latex, 'compile_pdf', compile_pdf)
    tailor.render(packet)
    rendered = json.loads(data_path.read_text())
    assert rendered['summary'] == data['summary']
    assert rendered['sections'][0] == 'summary'


def test_industry_layout_keeps_experience_before_skills_and_uses_unicode_sans(tmp_path):
    import copy
    data=copy.deepcopy(RESUME)
    data['layout']={'font_family':'sans','skills_last':True}
    tex=latex.render_tex(data,tmp_path/'resume.tex').read_text()
    assert tex.index(r'\section{RESEARCH EXPERIENCE}') < tex.index(r'\section{PROJECTS}') < tex.index(r'\section{SKILLS}')
    assert r'\setmainfont{texgyreheros}' in tex
    assert r'\usepackage{charter}' not in tex


def test_skill_selection_can_avoid_automatic_keyword_additions(env):
    profile=core.load_profile()
    profile['preferences']['resume_auto_add_skills']=False
    chosen=tailor.select_skills(['Python'],profile,[],posting_text='Python, ROS 2, PyTorch')
    assert [s['skill'] for s in chosen]==['Python']


def test_display_skill_groups_preserve_selected_skills_and_source_categories(job):
    from tests.test_checks import good_packet
    profile = core.load_profile()
    original_categories = [s.get('category') for s in profile['skills']]
    profile['preferences']['resume_skill_groups'] = {'Learning': ['PyTorch', 'Fortran'], 'Robotics': ['ROS 2']}
    content = tailor.enforce(good_packet(), profile, job['id'], ['ROS 2'])
    out = tailor.write_packet(job, content, profile, version=1)
    groups = json.loads((out / 'resume.json').read_text())['skills']
    assert next(g for g in groups if g['category'] == 'Learning')['items'] == ['PyTorch']
    assert not any('Fortran' in g['items'] for g in groups)
    assert [s.get('category') for s in profile['skills']] == original_categories


def test_employer_grouping_preserves_distinct_team_titles_and_dates(tmp_path):
    import copy
    data=copy.deepcopy(RESUME)
    first=data['experience'][0]
    first.update(employer='Example University',team='Perception Lab',org='Example University, Perception Lab')
    second=copy.deepcopy(first)
    second.update(team='Grasping Lab',org='Example University, Grasping Lab',dates='Aug 2025 – Dec 2025')
    data['experience'].append(second)
    tex=latex.render_tex(data,tmp_path/'resume.tex').read_text()
    assert tex.count(r'\textbf{Example University}')==1
    assert r'\textbf{Perception Lab}' in tex and r'\textbf{Grasping Lab}' in tex
    assert tex.count(r'\textit{Student Researcher}')==2
    assert r'Aug 2025 \textendash{} Dec 2025' in tex


def test_distinct_employers_are_not_grouped_by_similar_names(tmp_path):
    import copy
    data=copy.deepcopy(RESUME)
    second=copy.deepcopy(data['experience'][0])
    second['org']='Example Labs Incorporated'
    data['experience'].append(second)
    ctx=latex.context(data)
    assert all(entry['show_employer'] for entry in ctx['experience'])


def test_research_presentation_keeps_complete_education_and_project_links(tmp_path):
    import copy
    data = copy.deepcopy(RESUME)
    data['layout'] = {'presentation': 'research', 'font_family': 'charter', 'skills_last': True}
    tex = latex.render_tex(data, tmp_path / 'resume.tex').read_text()
    assert r'\section{Education}' in tex and r'\section{Selected Projects}' in tex
    assert r'\section{Technical Skills}' in tex
    assert r'WPI}\hfill Aug 2025' in tex
    assert r'M.S. Robotics\hfill GPA: 4.0' in tex
    assert r'\textbf{Stereo VIO}\enspace' in tex
    assert r'\documentclass[11pt' in tex and r'\linespread{1.0}' in tex
    assert 'github.com/alex/vio_' in tex


def test_unknown_presentation_fails_explicitly():
    import copy
    import pytest
    data = copy.deepcopy(RESUME)
    data['layout'] = {'presentation': 'unknown'}
    with pytest.raises(core.JobbotError, match='resume_presentation'):
        latex.context(data)


def test_research_pdf_renders_with_correct_reading_order(packet):
    import pytest
    from checks import ats_parse, length_limits
    if not latex.engine():
        pytest.skip('LaTeX compiler not installed')
    path = packet / 'resume.json'
    data = json.loads(path.read_text())
    data['layout'] = {'presentation': 'research', 'font_family': 'charter', 'skills_last': True,
                      'compact_education': True, 'coursework_in_education': True}
    data['courses'] = ['Computer Vision']
    path.write_text(core.dumps(data))
    meta = json.loads((packet / 'meta.json').read_text())
    meta.update(format='latex', show_summary=False)
    (packet / 'meta.json').write_text(core.dumps(meta))
    tailor.render(packet)
    assert not (packet / 'LATEX_NOTE.md').exists()
    assert not ats_parse.check(packet)
    assert not length_limits.check(packet)
    assert json.loads(path.read_text())['section_headings']['projects'] == 'Selected Projects'
    # The check must reject an education/course mismatch in the actual PDF.
    data = json.loads(path.read_text())
    data['courses'].append('Missing Course')
    path.write_text(core.dumps(data))
    assert any('coursework missing from education' in p for p in ats_parse.check(packet))
