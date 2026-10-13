# Prompt for Claude in Chrome: finish the click-to-review pages

Copy everything below the line into Claude in Chrome.

---

You are helping me review OCR output for a Pakistan customs-duty project. I have local HTML review pages. Each card shows a parsed row (S.No, tariff code, rate) above a scan image of the original page. Your job is to compare the row text with the image and click one of three buttons.

Open these pages one at a time (Chrome needs "Allow access to file URLs" turned on for the Claude extension):

1. file:///C:/Users/Maaz%20Ahmed/OneDrive/Desktop/customs-copilot/data/processed/review/sro_1152_rd_failures.html
2. file:///C:/Users/Maaz%20Ahmed/OneDrive/Desktop/customs-copilot/data/processed/review/sro_1152_rd_spotcheck.html
3. file:///C:/Users/Maaz%20Ahmed/OneDrive/Desktop/customs-copilot/data/processed/review/sro_1064_rd_failures.html
4. file:///C:/Users/Maaz%20Ahmed/OneDrive/Desktop/customs-copilot/data/processed/review/sro_1064_rd_spotcheck.html
5. file:///C:/Users/Maaz%20Ahmed/OneDrive/Desktop/customs-copilot/data/processed/review/tariff_specific_duties.html

Some cards already have an answer (green border). Skip those. Only do cards that have no answer yet.

For each card:
- Zoom into the image (click it) and find the row with that S.No on the page.
- Read the code and the rate printed on the scan yourself. Do not trust the parsed text.
- Decimal points are the main risk: OCR drops them, so "40" may really be "4.0", and "14.0" may be "1.40" or "14". Check every digit.
- If the code AND rate both match the scan exactly, click "Matches the page".
- If either differs, click "Wrong" and type exactly what the scan says in the text box that appears (code and rate, e.g. `1404.9020 / Rs.320/Kg`).
- If the image is blurry, the row is cut off, you cannot find the S.No, or you are less than sure of a single digit, click "Not sure". Never guess. "Not sure" is a good answer.
- For cards that say "Why flagged: code ... not in tariff", the SRO may genuinely print that code. If the scan prints it exactly as shown, click "Matches the page" and I will handle the rest.
- For "Respective headings" rows, click "Not sure" and type the full wording of the clause in the text box.

When a page is finished, click "Save results (downloads a CSV)". Then move to the next page.

Rules:
- Do not change anything outside these pages. Do not download anything except the CSVs from "Save results". Do not sign in or enter any data into any site.
- Work quickly, but never click "Matches the page" without reading the scan.
- At the end, give me a short list: per page, how many Matches / Wrong / Not sure, plus every "Wrong" card with your reading, and every "Not sure" card with S.No.

If the page images do not load, stop and tell me.
