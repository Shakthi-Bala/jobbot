import json

from agents import core, latex, tailor


def test_escape_specials_and_bold_percentages():
    assert latex.escape("R&D at 50% on C# _x_") == r"R\&D at \textbf{50\%} on C\# \_x\_"
    assert latex.escape("11×11 mask → depth") == r"11$\times$11 mask $\rightarrow$ depth"
    assert latex.escape(latex.Raw(r"\href{u}{x}")) == r"\href{u}{x}"


RESUME = {
    "person": {"name": "Alex Example", "email": "a@x.com", "phone": "", "location": "Boston, MA",
               "links": {"github": "https://github.com/alex", "scholar": ""}},
    "summary": "Built things & measured them.",
    "education": [{"school": "WPI", "degree": "M.S. Robotics", "dates": "Aug 2025 – May 2027",
                   "gpa": "4.0", "location": "", "details": []}],
    "skills": [{"category": "Project tools", "items": ["ROS 2", "C++"]}],
    "courses": ["Computer Vision"],
    "experience": [{"title": "Student Researcher", "org": "Example Lab", "dates": "Jan 2026 – Present",
                    "focus": "Thermal + ultrasound depth", "bullets": ["Cut error by 30%"],
                    "heading": "", "location": "", "links": {}, "tools": []}],
    "projects": [{"heading": "Stereo VIO", "dates": "", "bullets": ["Sliding-window BA"],
                  "tools": ["C++", "Eigen"], "links": {"repo": "https://github.com/alex/vio_#1"}}],
}


def test_tex_has_their_structure_and_escapes(tmp_path):
    tex = latex.render_tex(RESUME, tmp_path / "resume.tex").read_text()
    assert r"\usepackage{charter}" in tex and r"\newcommand{\place}" in tex
    assert r"\section{RESEARCH EXPERIENCE}" in tex          # every role is a research role
    assert r"\place{Research Focus: Thermal + ultrasound depth}" in tex
    assert r"\textbf{Tools: C++, Eigen.}" in tex                 # per-project tools line
    assert r"\textbf{Tools:} ROS 2, C++" in tex             # "Project tools" -> "Tools"
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
