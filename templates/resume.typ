// One-page, single-column, ATS-safe resume. Data: resume.json (written by agents/tailor.py
// or agents/master.py). Text only: no tables, columns, icons or images, so parsers read it
// top to bottom exactly as a person does. Section order is fixed and mirrored in
// resume.json "sections" so checks/ats_parse.py can verify reading order.
#let d = json("resume.json")
#let accent = rgb("#1F3864")
#let muted = rgb("#404040")

#set document(title: d.person.name + " - Resume", author: d.person.name)
#set page(paper: "us-letter", margin: (x: 0.55in, top: 0.45in, bottom: 0.4in))
#set text(font: ("Lato", "DejaVu Sans"), size: 11pt, lang: "en", ligatures: false)
#set par(justify: false, leading: 0.48em, spacing: 0.5em)
#set list(indent: 0.35em, body-indent: 0.45em, spacing: 0.36em, marker: [•])

#show heading.where(level: 1): it => block(above: 0.8em, below: 0.42em, width: 100%)[
  #text(size: 10.5pt, weight: "bold", fill: accent, tracking: 0.05em, upper(it.body))
  #v(-0.62em)
  #line(length: 100%, stroke: 0.6pt + accent)
]

#let is-url(x) = type(x) == str and x.starts-with("http")
#let short(u) = u.replace("https://", "").replace("http://", "").replace("www.", "").trim("/", at: end)
#let sep = [ #h(0.25em)#text(fill: muted)[|]#h(0.25em) ]

#let entry(left, right, sub: "", subright: "") = block(above: 0.6em, below: 0.32em, breakable: false)[
  #text(weight: "bold", left) #h(1fr) #text(size: 9pt, fill: muted, right)
  #if sub != "" or subright != "" [
    \ #text(style: "italic", sub) #h(1fr) #text(size: 9pt, fill: muted, subright)
  ]
]

// ---- header ---------------------------------------------------------------
#align(center)[
  #text(size: 20pt, weight: "bold", fill: accent, d.person.name)
  #v(-0.45em)
  #let plain = (d.person.location, d.person.email, d.person.phone).filter(x => x != "" and x != none)
  #let links = d.person.links.values().filter(is-url).map(u => link(u, short(u)))
  #text(size: 9pt)[#(plain.map(x => [#x]) + links).join(sep)]
]

// ---- summary --------------------------------------------------------------
#if d.summary != "" [
  = Summary
  #d.summary
]

// ---- skills ---------------------------------------------------------------
#if d.skills.len() > 0 [
  = Skills
  #for g in d.skills [
    #block(above: 0.28em, below: 0.28em)[#text(weight: "bold", g.category + ": ")#g.items.join(", ")]
  ]
]

// ---- experience -------------------------------------------------------------
#if d.experience.len() > 0 [
  = Experience
  #for x in d.experience [
    #entry(x.title, x.dates, sub: x.org, subright: x.location)
    #list(..x.bullets)
  ]
]

// ---- projects ---------------------------------------------------------------
#if d.projects.len() > 0 [
  = Projects
  #for p in d.projects [
    #let urls = p.links.values().filter(is-url)
    #entry(
      [#p.heading#if urls.len() > 0 [ #h(0.4em)#text(size: 8.5pt, weight: "regular", fill: muted)[#urls.map(u => link(u, short(u))).join(sep)]]],
      p.dates)
    #list(..p.bullets)
  ]
]

// ---- education --------------------------------------------------------------
#if d.education.len() > 0 [
  = Education
  #for e in d.education [
    #entry(e.school, e.dates,
      sub: e.degree + if e.gpa != "" { ", GPA " + e.gpa } else { "" },
      subright: e.location)
    #if e.details.len() > 0 { list(..e.details) }
  ]
]
