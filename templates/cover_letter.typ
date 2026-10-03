// Plain cover letter. Data comes from cover_letter.json, written by agents/tailor.py.
#let d = json("cover_letter.json")

#set document(title: d.person.name + " - Cover letter", author: d.person.name)
#set page(paper: "us-letter", margin: 1in)
#set text(size: 11pt, lang: "en", ligatures: false)
#set par(justify: false, leading: 0.6em, spacing: 1.1em)

#strong(d.person.name) \
#(d.person.location, d.person.email, d.person.phone).filter(x => x != "").join("  |  ")

#v(1em)
#d.date

Hiring team, #d.company \
Re: #d.title

#for p in d.paragraphs [
  #p

]

Sincerely, \
#d.person.name
