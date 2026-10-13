"""Second owner task page: the ruling dates and numbers (scans are garbled in the text layer).
Usage: python -m src.ingest.owner_tasks_2   (writes data/processed/review/owner_tasks_2.html)
"""
import json

import src.ingest.owner_tasks as ot
from src.ingest.review_pages import REV

ot.tasks.clear()
PN = "2026991291422532PublicNotice60-2026.pdf"
VR = "202610212101254615VR2110.pdf"
VAL = "2025717157016485ValuationRuling2006-2025.pdf"

ot.task("R1", "Public Notice 60/2026: its date and number",
        ["Look at the image (page 1 of the Public Notice).",
         "Find the number printed at the top (for example 'Public Notice No. 60/2026').",
         "Find the date it was issued (usually near the top or at the signature at the end of the notice).",
         "Find any sentence about when it takes effect (words like 'with immediate effect', 'w.e.f.', 'from')."],
        [ot.img(PN, 1)],
        [("number", "Number printed at the top"),
         ("issue_date", "Issue date (exactly as printed, for example 1 September 2026)"),
         ("effective_wording", "Sentence about when it takes effect (or: none printed)")])
ot.task("R2", "Valuation Ruling 2110: its date and number",
        ["Same steps as R1, on this ruling (page 1)."],
        [ot.img(VR, 1)],
        [("number", "Ruling number printed at the top"),
         ("issue_date", "Issue date (exactly as printed)"),
         ("effective_wording", "Sentence about when it takes effect (or: none printed)")])
ot.task("R3", "Valuation ruling file 2006-2025: its number and date",
        ["Same steps as R1. The file name has no number, so read it from the page."],
        [ot.img(VAL, 1)],
        [("number", "Ruling number printed (or: illegible)"),
         ("issue_date", "Issue date (exactly as printed, or: illegible)"),
         ("what_goods", "In one line, which goods the ruling is about")])

if __name__ == "__main__":
    REV.mkdir(parents=True, exist_ok=True)
    (REV / "owner_tasks_2.html").write_text(ot.PAGE.replace("__T__", json.dumps(ot.tasks)).replace(
        'KEY="owner_tasks"', 'KEY="owner_tasks_2"').replace("owner_tasks-results.csv", "owner_tasks_2-results.csv"),
        encoding="utf-8")
    print(len(ot.tasks), "tasks")
