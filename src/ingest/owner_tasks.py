"""One page with every task the owner must do by hand: instructions, the scan, and a box to type the answer.
Usage: python -m src.ingest.owner_tasks   (writes data/processed/review/owner_tasks.html)
"""
import html
import json
from pathlib import Path

import pymupdf

from src.ingest.review_pages import REV, P

RAW = Path("data/raw")
OUT = P / "page_images" / "owner_tasks"


def img(pdf, page, dpi=120):
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / f"{Path(pdf).stem[:30]}_p{page:04d}.png"
    if not f.exists():
        pymupdf.open(RAW / pdf)[page - 1].get_pixmap(dpi=dpi).save(f)
    return f"../page_images/owner_tasks/{f.name}"


def pi(folder, n):
    return f"../page_images/{folder}/p{n:03d}.png"


NOTES = json.load(open(P / "legal_notes.json", encoding="utf-8"))
notes = {(r["kind"], r["section_or_chapter"], r["note_number"], r["page"]): r for r in NOTES}
TARIFF = "2022711271427852PakistanCustomsTariff.pdf"
F1064, F1152 = "202663017637155381064-2026", "202572975650649SRO.1152of2025"

tasks = []


def task(tid, title, steps, images, fields, shown=""):
    tasks.append(dict(id=tid, title=title, steps=steps, images=images, fields=fields, shown=shown))


task("T1", "SRO 1065(I)/2026: when does it start?",
     ["Look at the image below (this is the whole SRO).",
      "Find the date printed at the top (the line that says Islamabad, the ... day of ...).",
      "Read the paragraphs. Find any sentence that says when it comes into force or until when it applies "
      "(words like 'with effect from', 'shall come into force', 'up to', 'till')."],
     [pi("202663020651815SRO1065_1", 1)],
     [("date_line", "Date printed at the top (type it exactly, for example 30 June 2026)"),
      ("start_wording", "Copy the sentence about when it starts. If there is none, type: none printed"),
      ("end_wording", "Copy the sentence about when it ends. If none, type: none printed")])
task("T2", "SRO 1898(I)/2025: when does it start?", ["Same three steps as T1, on this SRO."],
     [pi("202510117101711806SRO-18982025", 1)],
     [("date_line", "Date printed at the top"),
      ("start_wording", "Sentence about when it starts (or: none printed)"),
      ("end_wording", "Sentence about when it ends (or: none printed)")])
task("T3", "Income tax: is the code 5403.2010 or 5503.2010?",
     ["Look at the image (Twelfth Schedule, Part II, page 827 of the Ordinance PDF).",
      "Find the row 'Synthetic staple fibres, not carded, combed or otherwise' and read its code in the first column.",
      "Scroll to the footnotes at the bottom of the same page. Find the footnote that mentions this code "
      "and read the code it prints."],
     [pi("2026724177725705IncomeTaxOrdinanace2001", 827)],
     [("code_in_table", "Code printed in the table row"),
      ("code_in_footnote", "Code printed in the footnote (and the footnote number)"),
      ("note", "Optional: anything odd")])
task("T4", "SRO 1064: the 'Respective headings' rows and the dates (pages 29 and 30)",
     ["Image 1 is page 29. Find S.No 686 and S.No 687 near the bottom. In the code column they say 'Respective headings'.",
      "Read the full text next to them (description and any list of headings, chapters or conditions). Copy the wording.",
      "Image 2 is page 30. Find the clause about the date (words like 'with effect from 1st July 2026', "
      "'shall remain in force', 'till').",
      "Copy the date clause. If no end date is printed, type: none printed."],
     [pi(F1064, 29), pi(F1064, 30)],
     [("s686", "Full wording for S.No 686 (which headings or goods does it cover?)"),
      ("s687", "Full wording for S.No 687 (Rs.2400 per minute: which headings or goods?)"),
      ("effective", "Sentence that gives the start date"),
      ("end", "Sentence that gives an end date (or: none printed)")])
task("T5", "SRO 1152: the 'Respective headings' rows and the dates (pages 38 and 39)",
     ["Same four steps as T4. Image 1 is page 38 (S.No 692 and 693), image 2 is page 39 (the date clauses)."],
     [pi(F1152, 38), pi(F1152, 39)],
     [("s692", "Full wording for S.No 692"),
      ("s693", "Full wording for S.No 693 (Rs.3000 per minute)"),
      ("effective", "Sentence that gives the start date"),
      ("end", "Sentence that gives an end date (or: none printed)")])

TABLE_NOTES = [(50, ("chapter_note", "Chapter 11", "2")),
               (231, ("subheading_note", "Chapter 48", "1")), (231, ("subheading_note", "Chapter 48", "2")),
               (365, ("chapter_note", "Chapter 74", "1")), (366, ("subheading_note", "Chapter 74", "1")),
               (376, ("subheading_note", "Chapter 78", "1"))]
for pg, k in TABLE_NOTES:
    r = notes.get(k + (pg,))
    txt = html.escape((r["text"] if r else "(record not found; read the page)")[:900])
    task(f"N{pg}-{k[1].replace(' ', '')}-{k[2]}",
         f"Legal note with a table: {k[1]}, {k[0].replace('_', ' ')} {k[2]} (tariff PDF page {pg})",
         ["Look at the image (the tariff PDF page) and find this note and its table.",
          "The yellow box is what our parser read. The prose is fine; the table numbers got flattened.",
          "Compare the NUMBERS in the table. If they all match, type: ok. If any differs, type what the page says."],
         [img(TARIFF, pg)], [("answer", "ok, or the correct numbers")], shown=txt)

gri = [r for r in NOTES if r["kind"] in ("gri", "gri_pakistan")]
task("G1", "General Rules for the Interpretation (GRI 1 to 6 and Pakistan Rules 1 and 2): are our 8 rows right?",
     ["Image 1 is tariff PDF page 8, image 2 is page 9.",
      "The yellow box lists the 8 rows our parser read. Read each rule on the page and check it matches.",
      "If all 8 match, type: ok. If one differs, type its number and what the page says."],
     [img(TARIFF, 8), img(TARIFF, 9)], [("answer", "ok, or which rule differs and how")],
     shown="<br><br>".join(f"<b>{r['kind']} {r['note_number']}</b> (p{r['page']}): " + html.escape(r["text"][:350])
                           for r in gri))
task("D1", "Two yes/no decisions", ["Type yes or no in each box. My recommendation is in the question."], [],
     [("hs2022", "Label the legal notes 'HS 2022 edition, applicability to FY2025-26 and FY2026-27 assumed, "
                 "not proven'? (recommend: yes)"),
      ("ch99", "Leave Chapter 99 sub-chapter conditions (tariff pp586-602) out for now? (recommend: yes)")])

PAGE = """<!doctype html><html><head><meta charset=utf-8><title>Owner tasks</title><style>
body{font-family:system-ui,Segoe UI,Arial;margin:0;background:#f4f4f6;color:#111}
header{position:sticky;top:0;background:#fff;border-bottom:1px solid #ccc;padding:10px 16px;z-index:5}
.card{background:#fff;margin:14px auto;max-width:1000px;border:1px solid #ccc;border-radius:8px;padding:14px}
h2{font-size:18px;margin:0 0 6px}ol{margin:6px 0 10px 18px}
img{max-width:100%;border:1px solid #bbb;margin:6px 0;cursor:zoom-in}img.big{max-width:none;cursor:zoom-out}
textarea{width:98%;font-size:15px;padding:5px;min-height:34px}
label{display:block;margin-top:8px;font-weight:600;font-size:14px}
.shown{background:#fff8d6;border:1px solid #e0cf80;padding:8px;font-size:13px;margin:6px 0}
button{font-size:15px;padding:6px 14px;background:#1d4ed8;color:#fff;border:0;border-radius:6px;cursor:pointer}
</style></head><body><header><b>Owner tasks</b> - do them top to bottom. Click an image to zoom.
Your typing is saved in the browser. <span id=prog></span>
<button onclick=save()>Save answers (downloads a CSV)</button></header><div id=c></div>
<script>
const T=__T__,KEY="owner_tasks";let A={};
try{A=JSON.parse(localStorage.getItem(KEY)||"{}")}catch(e){}
function set(k,v){A[k]=v;try{localStorage.setItem(KEY,JSON.stringify(A))}catch(e){}prog()}
function prog(){let n=T.filter(t=>t.fields.every(f=>(A[t.id+"|"+f[0]]||"").trim())).length;
document.getElementById("prog").textContent=" "+n+" of "+T.length+" tasks done "}
function esc(s){return (s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;")}
document.getElementById("c").innerHTML=T.map(t=>"<div class=card><h2>"+t.id+": "+t.title+"</h2><ol>"+
t.steps.map(s=>"<li>"+s+"</li>").join("")+"</ol>"+
t.images.map(i=>'<img src="'+i+'" onclick="this.classList.toggle(\\'big\\')" loading=lazy>').join("<br>")+
(t.shown?"<div class=shown><b>What our parser read:</b><br>"+t.shown+"</div>":"")+
t.fields.map(f=>"<label>"+f[1]+"</label><textarea oninput=\\"set('"+t.id+"|"+f[0]+"',this.value)\\">"+esc(A[t.id+"|"+f[0]])+"</textarea>").join("")+
"</div>").join("");prog();
function save(){const q=s=>'"'+String(s).replace(/"/g,'""')+'"';let o="task,field,answer\\n";
T.forEach(t=>t.fields.forEach(f=>{o+=[t.id,f[0],A[t.id+"|"+f[0]]||""].map(q).join(",")+"\\n"}));
const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([o],{type:"text/csv"}));
a.download="owner_tasks-results.csv";a.click()}
</script></body></html>"""

if __name__ == "__main__":
    REV.mkdir(parents=True, exist_ok=True)
    (REV / "owner_tasks.html").write_text(PAGE.replace("__T__", json.dumps(tasks)), encoding="utf-8")
    print(len(tasks), "tasks")
