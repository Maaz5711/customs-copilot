# Getting a better answer key (cases with a trusted 8-digit code)

Why: right now accuracy is measured on 79 real cases from public rulings and 60 cases written by Claude. Nobody has checked the Claude-written labels, and many ruling cases were disputes. A set of **real imports with the code Customs finally accepted** is the most valuable thing that can be added to this project. With 40 to 60 such cases, differences of a few points become measurable and the "tested on real Pakistani imports" claim becomes strong.

## What to ask for (one row per product)
Use `cases_template.csv` (columns below). One product per row. **No company names, no personal data, no GD numbers**, nothing that identifies the importer. Product words as they would appear on the invoice or packing list, plus anything a clearing agent would need to classify it.

| Column | Meaning |
|---|---|
| `description` | The product as the importer would describe it (material, use, size, power, type; English is fine) |
| `import_date` | Date of the Goods Declaration (YYYY-MM-DD). Must be 1 Jul 2025 or later |
| `final_code` | The 8-digit PCT code that was **finally assessed and accepted** (after any dispute or appeal) |
| `declared_code` | The code first declared, if different (this shows where mistakes happen) |
| `how_sure` | `assessed_and_accepted`, `ruling_or_order`, or `my_best_knowledge` |
| `notes` | Anything unusual: disputed, changed after audit, special regime, CKD/CBU, etc. |

Rows with `my_best_knowledge` are still useful but will be kept separate.

## Who can help
1. **Your friend (textile and electronics importer from China).** The best source: real invoices, real codes, and the exact words used. Textiles and electronics are the heaviest import categories, so a few dozen products already cover a lot. Ask for the products he imports regularly, including ones where the code was changed by Customs or by his clearing agent.
2. **His clearing agent.** The person who actually files the GD usually knows the final code and the reason. A clearing agent can also tell which products are commonly misclassified.
3. **Customs agents' associations and chambers.** Karachi Customs Agents Association, the chambers of commerce (KCCI, FPCCI, LCCI). They appear in the distribution list of every classification notice, so they handle these questions.
4. **FBR / Pakistan Customs official channels.** Use the contact details published on fbr.gov.pk (the Customs section and the "Public Notice (Classification)" page name the issuing Collectorate and Directorate). I can draft the email. I will not look up private or personal email addresses of individual officers; use the official contact page or ask your friend's clearing agent to introduce you.

## What we promise in return
Cases are used only to test and improve this open student project; no company or person is named; they will be reported as "N real imports from a clearing agent". Mention that the tool refuses to help with misdeclaration and cites its sources.

See `email_draft.md` for a message you can send.
