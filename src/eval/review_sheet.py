"""A review page for the importer who shared the GD extract: for every case where the agent's first code differs from the declared code, who is right?

    python -m src.eval.review_sheet            ->  data/raw/importer_data/review_sheet.html   (PRIVATE, gitignored; it holds descriptions from his own shipments)

The page is one self-contained HTML file (no internet needed). For each case: the product words, the code declared on the cleared GD with its full tariff wording,
the agent's first code with its wording, and the agent's other candidates. Four buttons: declared is right / agent is right / both acceptable / neither (type the code).
Answers are kept in the browser and saved with "Save CSV". Nothing here is verified until he answers; the answers become an expert-checked part of the answer key.
"""
from __future__ import annotations

import html
import json
from pathlib import Path

from .cases import load_importer_cases

RESULTS = Path("data/processed/eval/deepseek_importer/results_full_graph.jsonl")
TARIFF_DOCS = Path("data/processed/search_index/tariff/docs.jsonl")
OUT = Path("data/raw/importer_data/review_sheet.html")


def tariff_wording() -> dict[str, str]:
    """code (8 digits) -> full wording 'Heading > sub-heading > line', FY2025-26 documents preferred (the GD month is February 2026)."""
    words: dict[str, str] = {}
    for line in TARIFF_DOCS.read_text(encoding="utf-8").splitlines():
        d = json.loads(line)
        code = d.get("code") or ""
        if d.get("kind") == "line" and len(code) == 8 and (code not in words or d.get("fy", "").startswith("2025")):
            words[code] = d["text"].split(" ", 1)[1] if " " in d["text"] else d["text"]
    return words


def misses() -> list[dict]:
    cases = {c.id: c for c in load_importer_cases()}
    words = tariff_wording()
    out = []
    for line in RESULTS.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        codes = r["pred"]["codes"]
        if not codes or codes[0] == r["expected"]:
            continue
        c = cases[r["case_id"]]
        fmt = lambda x: f"{x[:4]}.{x[4:]}"      # noqa: E731
        out.append({"id": r["case_id"], "desc": c.description, "declared": fmt(r["expected"]), "declared_text": words.get(r["expected"], "(not in the tariff text)"),
                    "agent": fmt(codes[0]), "agent_text": words.get(codes[0], ""), "others": [f"{fmt(x)}  {words.get(x, '')[:90]}" for x in codes[1:3]]})
    return out


PAGE = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Which code is right?</title><style>
body{font:16px/1.45 system-ui,sans-serif;max-width:880px;margin:0 auto;padding:16px;background:#fafafa;color:#222}
.card{background:#fff;border:1px solid #ddd;border-radius:10px;padding:14px;margin:14px 0}
.d{font-weight:600}.code{font-family:ui-monospace,monospace;background:#eef;padding:1px 6px;border-radius:4px}
button{margin:4px 6px 0 0;padding:8px 12px;border:1px solid #888;border-radius:8px;background:#fff;cursor:pointer}
button.sel{background:#1b5e20;color:#fff;border-color:#1b5e20}.small{color:#666;font-size:14px}
input{padding:6px;border:1px solid #aaa;border-radius:6px;width:140px}
#bar{position:sticky;top:0;background:#fafafa;padding:8px 0;border-bottom:1px solid #ddd}
</style></head><body>
<h2>Which code is right?</h2>
<p>For each product below, two codes are shown: the one declared on the cleared Goods Declaration, and the one our tool picked. Please tell us which one is right for that product. If you are not sure, leave it blank. No company names are shown. Your answers only help us measure and improve the tool.</p>
<div id="bar"><span id="count"></span> <button onclick="save()">Save CSV</button></div>
<div id="cards"></div>
<script>
const ITEMS = __ITEMS__;
let ans = {}; try { ans = JSON.parse(localStorage.getItem("review_ans") || "{}"); } catch(e) {}
function persist(){ try { localStorage.setItem("review_ans", JSON.stringify(ans)); } catch(e) {} }
function set(id, v){ ans[id] = Object.assign({}, ans[id], {v:v}); persist(); render(); }
function typed(id, t){ ans[id] = Object.assign({}, ans[id], {t:t}); persist(); }
function esc(s){ return String(s).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }
function render(){
  document.getElementById("cards").innerHTML = ITEMS.map(d => {
    const a = ans[d.id] || {}; const b = (v, label) => `<button class="${a.v==v?'sel':''}" onclick="set('${d.id}','${v}')">${label}</button>`;
    return `<div class="card"><div class="d">${esc(d.desc)}</div>
      <div>Declared: <span class="code">${esc(d.declared)}</span> ${esc(d.declared_text)}</div>
      <div>Our tool: <span class="code">${esc(d.agent)}</span> ${esc(d.agent_text)}</div>
      ${d.others.length ? `<div class="small">Other candidates: ${d.others.map(esc).join(' | ')}</div>` : ''}
      ${b('declared','Declared is right')}${b('agent','Our tool is right')}${b('both','Both are acceptable')}${b('neither','Neither')}
      <input placeholder="right code if neither" value="${esc(a.t||'')}" onchange="typed('${d.id}', this.value)"></div>`; }).join("");
  document.getElementById("count").textContent = Object.values(ans).filter(x => x.v).length + " of " + ITEMS.length + " answered";
}
function save(){
  const rows = [["id","answer","right_code_if_neither"]].concat(ITEMS.map(d => [d.id, (ans[d.id]||{}).v||"", (ans[d.id]||{}).t||""]));
  const blob = new Blob([rows.map(r => r.join(",")).join("\\n")], {type:"text/csv"});
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "code_review_answers.csv"; a.click();
}
render();
</script></body></html>"""


def build() -> Path:
    items = misses()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(PAGE.replace("__ITEMS__", json.dumps(items, ensure_ascii=False)), encoding="utf-8")
    print(f"{len(items)} disagreement cases -> {OUT}")
    return OUT


if __name__ == "__main__":
    build()
