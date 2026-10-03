// Single-column, ATS-safe resume. Data comes from resume.json next to this file,
// written by agents/tailor.py. No tables, columns, icons or images: parsers read
// this top to bottom exactly as a human does.
#let d = json("resume.json")

#set document(title: d.person.name + " - Resume", author: d.person.name)
#set page(paper: "us-letter", margin: (x: 0.6in, y: 0.5in))
#set text(size: 10.5pt, lang: "en", ligatures: false)
#set par(justify: false, leading: 0.55em, spacing: 0.6em)
#set list(indent: 0.6em, body-indent: 0.5em, spacing: 0.45em)

#show heading.where(level: 1): it => block(above: 1em, below: 0.5em)[
  #text(size: 11pt, weight: "bold", upper(it.body))
  #v(-0.7em)
  #line(length: 100%, stroke: 0.5pt)
]

#let entry(left, right, sub: "") = block(above: 0.7em, below: 0.35em)[
  #strong(left) #h(1fr) #right
  #if sub != "" [ \ #emph(sub) ]
]

// ---- header -------------------------------------------------------------
#align(center)[
  #text(size: 17pt, weight: "bold", d.person.name)
  #v(-0.4em)
  #let contact = (d.person.location, d.person.email, d.person.phone)
    .filter(x => x != "")
  #let links = d.person.links.values().filter(x => x != "" and x != none)
  #(contact + links).join("  |  ")
]

// ---- education ----------------------------------------------------------
#if d.education.len() > 0 [
  = Education
  #for e in d.education [
    #entry(e.school, e.dates, sub: e.degree + if e.gpa != "" { ", GPA " + e.gpa } else { "" })
    #if e.details.len() > 0 { list(..e.details) }
  ]
]

// ---- experience ---------------------------------------------------------
#if d.experience.len() > 0 [
  = Experience
  #for x in d.experience [
    #entry(x.title, x.dates, sub: x.org + if x.location != "" { ", " + x.location } else { "" })
    #list(..x.bullets)
  ]
]

// ---- projects -----------------------------------------------------------
#if d.projects.len() > 0 [
  = Projects
  #for p in d.projects [
    #entry(p.heading, p.dates, sub: p.links.values().filter(x => x != "" and x != none).join("  |  ", default: ""))
    #list(..p.bullets)
  ]
]

// ---- skills -------------------------------------------------------------
#if d.skills.len() > 0 [
  = Skills
  #d.skills.join(", ")
]
