"""Build easy click-to-review web pages (one per CSV) so the owner does not have to edit CSV files.

Each page shows the parsed row next to the original page image, with buttons Correct / Wrong / Not sure.
Answers are kept in the browser and exported with the 'Save results' button as a CSV.

Usage: python -m src.ingest.review_pages
"""
import csv
import html
import json
from pathlib import Path

import pymupdf

P = Path("data/processed")
REV = P / "review"

TEMPLATE = """<!doctype html><html><head><meta charset="utf-8"><title>__TITLE__</title>
<style>
body{font-family:system-ui,Segoe UI,Arial;margin:0;background:#f4f4f6;color:#111}
header{position:sticky;top:0;background:#fff;border-bottom:1px solid #ccc;padding:10px 16px;z-index:5}
h1{font-size:18px;margin:0 0 4px}
.how{font-size:14px;color:#333}
.card{background:#fff;margin:14px auto;max-width:980px;border:1px solid #ccc;border-radius:8px;padding:12px}
.card.done{border-color:#2a9d4a}
.row{font-size:18px;margin-bottom:6px}.row b{background:#fff3b0;padding:1px 6px;border-radius:4px}
.why{font-size:13px;color:#8a4b00;margin:6px 0}
img{max-width:100%;border:1px solid #bbb;cursor:zoom-in}img.big{max-width:none;cursor:zoom-out}
button{font-size:15px;padding:6px 14px;margin:6px 6px 0 0;border:1px solid #888;border-radius:6px;background:#eee;cursor:pointer}
button.sel.ok{background:#2a9d4a;color:#fff}button.sel.bad{background:#d62828;color:#fff}button.sel.unsure{background:#f4a300}
input{font-size:15px;padding:5px;width:260px;display:none}
.top button{background:#1d4ed8;color:#fff}
</style></head><body>
<header><h1>__TITLE__</h1>
<div class="how">__HOW__</div>
<div class="top"><span id="prog"></span> <button onclick="saveCsv()">Save results (downloads a CSV)</button></div></header>
<div id="cards"></div>
<script>
const KEY="review___NAME__", DATA=__DATA__;
let ans={};try{ans=JSON.parse(localStorage.getItem(KEY)||"{}")}catch(e){}
function persist(){try{localStorage.setItem(KEY,JSON.stringify(ans))}catch(e){}}
function set(id,v,val){ans[id]={v:v,val:val!==undefined?val:(ans[id]||{}).val||""};persist();draw()}
function draw(){
 let n=0,h="";
 DATA.forEach(d=>{const a=ans[d.id]||{};if(a.v)n++;
  h+=`<div class="card ${a.v?'done':''}"><div class="row">${d.line}</div>${d.why?`<div class="why">Why flagged: ${d.why}</div>`:''}
  <img src="${d.img}" onclick="this.classList.toggle('big')" loading="lazy"><br>
  <button class="${a.v=='ok'?'sel ok':''}" onclick="set('${d.id}','ok')">&#10003; Matches the page</button>
  <button class="${a.v=='bad'?'sel bad':''}" onclick="set('${d.id}','bad')">&#10007; Wrong</button>
  <button class="${a.v=='unsure'?'sel unsure':''}" onclick="set('${d.id}','unsure')">? Not sure</button>
  <input id="i${d.id}" placeholder="What does the page really say?" value="${(a.val||'').replace(/"/g,'&quot;')}" style="display:${a.v=='bad'?'inline-block':'none'}" onchange="set('${d.id}','bad',this.value)"></div>`});
 document.getElementById("cards").innerHTML=h;document.getElementById("prog").textContent=n+" of "+DATA.length+" done  ";
}
function saveCsv(){
 const q=s=>'"'+String(s).replace(/"/g,'""')+'"';
 const NL=String.fromCharCode(10);let out="id,line,answer,true_value"+NL;
 DATA.forEach(d=>{const a=ans[d.id]||{};out+=[q(d.id),q(d.plain),q(a.v||""),q(a.val||"")].join(",")+NL});
 const b=new Blob([out],{type:"text/csv"}),u=URL.createObjectURL(b),l=document.createElement("a");
 l.href=u;l.download="__NAME__-results.csv";l.click();
}
draw();
</script></body></html>"""


def build(name, title, how, items):
    page = (TEMPLATE.replace("__TITLE__", html.escape(title)).replace("__HOW__", how)
            .replace("__NAME__", name).replace("__DATA__", json.dumps(items)))
    (REV / f"{name}.html").write_text(page, encoding="utf-8")


def sro_items(csv_path, with_issues):
    items = []
    for r in csv.DictReader(open(csv_path, encoding="utf-8")):
        img = "../" + r["page_image"].replace("data/processed/", "")
        line = (f"Page {r['page']}: S.No <b>{html.escape(r['s_no'])}</b>, code <b>{html.escape(r['pct_code'])}</b>, "
                f"rate <b>{html.escape(r['rate'])}</b>")
        plain = f"p{r['page']} S.No {r['s_no']} code {r['pct_code']} rate {r['rate']}"
        items.append({"id": f"p{r['page']}-s{r['s_no']}", "line": line, "plain": plain, "img": img,
                      "why": html.escape(r["issues"]) if with_issues else ""})
    return items


def a3_items(csv_path, failures):
    """A3 sales tax / income tax sheets. Several rows can share a serial number, so ids carry the row number."""
    items = []
    for k, r in enumerate(csv.DictReader(open(csv_path, encoding="utf-8")), 1):
        code = r.get("code_raw") if failures else r.get("pct_code")
        rate = r.get("rate_raw") if failures else r.get("rate")
        img = "../" + r["page_image"].replace("data/processed/", "")
        line = (f"Page {r['page']}: S.No <b>{html.escape(r['s_no'])}</b>, code/goods <b>{html.escape(code or '')}</b>, "
                f"rate/rule <b>{html.escape(rate or '')}</b>")
        plain = f"p{r['page']} S.No {r['s_no']} code {code} rate {rate}"
        items.append({"id": f"r{k}-p{r['page']}-s{r['s_no']}", "line": line, "plain": plain, "img": img,
                      "why": html.escape(r.get("issues", "")) if failures else ""})
    return items


def tariff_items():
    pdf = Path("data/raw/20268251181330180Tariff-2026-27.pdf")
    out_dir = P / "page_images" / "tariff_2026_27"
    out_dir.mkdir(parents=True, exist_ok=True)
    items, doc = [], pymupdf.open(pdf)
    for r in csv.DictReader(open(P / "spotcheck_tariff_2026_27.csv", encoding="utf-8")):
        if r["reason"] != "specific/compound duty":
            continue
        pg = int(r["page"])
        f = out_dir / f"p{pg:03d}.png"
        if not f.exists():
            doc[pg - 1].get_pixmap(dpi=110).save(f)
        line = (f"Page {pg}: code <b>{r['code']}</b> ({html.escape(r['description'][:50])}), "
                f"parsed duty <b>{html.escape(r['parsed_cd'])}</b>")
        items.append({"id": f"{r['code']}", "line": line, "plain": f"{r['code']} parsed {r['parsed_cd']}",
                      "img": f"../page_images/tariff_2026_27/p{pg:03d}.png", "why": "Specific duty: read from rotated text. Is the amount right (no missing digit)?"})
    return items


if __name__ == "__main__":
    REV.mkdir(parents=True, exist_ok=True)
    how_fail = "Find the row on the page image (look for the S.No / code in yellow). If the table value matches the page, click Matches. If not, click Wrong and type what the page says."
    how_spot = how_fail
    for n, t in (("sro_1064_rd", "SRO 1064 (RD 2026-27)"), ("sro_1152_rd", "SRO 1152 (RD 2025-26)")):
        build(f"{n}_failures", f"{t}: flagged rows", how_fail, sro_items(P / f"{n}_failures.csv", True))
        build(f"{n}_spotcheck", f"{t}: 10% spot check", how_spot, sro_items(P / f"spotcheck_{n}.csv", False))
    build("tariff_specific_duties", "Tariff 2026-27: specific duties (Rs. per unit)",
          "Find the code on the page image and check the Rs. amount and unit (the amount is written sideways in a narrow column).",
          tariff_items())
    a3_pages = []
    for f in sorted(P.glob("spotcheck_a3_*.csv")):
        n = f.stem.replace("spotcheck_", "") + "_spotcheck"
        build(n, f"A3 {f.stem.replace('spotcheck_a3_', '')}: 10% spot check (sales tax / income tax)",
              "Find the row on the page image (S.No, code, rate, dates). If it matches the page click Matches; if not click Wrong and type what the page says.",
              a3_items(f, False))
        a3_pages.append(n)
    for f in sorted(P.glob("a3_*_failures.csv")):
        n = f.stem
        build(n, f"A3 {f.stem[3:-9]}: flagged rows", how_fail, a3_items(f, True))
        a3_pages.append(n)
    idx = "<h2>Review pages</h2><p>Open them in this order. Click the buttons, then press Save results.</p><ol>" + "".join(
        f'<li><a href="{f}.html">{f}</a></li>' for f in
        ["sro_1152_rd_failures", "sro_1152_rd_spotcheck", "sro_1064_rd_failures", "sro_1064_rd_spotcheck", "tariff_specific_duties"] + a3_pages) + "</ol>"
    (REV / "index.html").write_text("<!doctype html><meta charset=utf-8><body style='font-family:system-ui;margin:30px'>" + idx, encoding="utf-8")
    print("built", sorted(x.name for x in REV.iterdir()))
