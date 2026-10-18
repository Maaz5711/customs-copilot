# Where we stand: aims, competitors, published research, next steps (2026-10-18)

## 1. Did we build what SPEC.md aimed for?
| SPEC aim (section 4 and 9) | Status |
|---|---|
| Product words to top-3 codes with clarifying questions | Built and measured. |
| Full duty stack by date (CD, RD, ACD, sales tax incl. further tax and the 3% tax, income tax incl. non-filer, FED) | Built. 88% of real plain-rate lines match what Customs charged on every tax. 95.8% of China FTA lines match. |
| Concessions (Fifth Schedule, China FTA) | Built, offered, never applied silently. |
| Citation for every figure | Built (tariff page, SRO clause, rate card). |
| "Not sure" mode | Built. The agent asks or refuses more often when it is wrong: it is right first on 62% of the cases it answers and 30% of the cases where it pauses to ask. |
| Date picker | Built (two fiscal years). |
| Ablation (plain / search / full agent) | Published: 11% / 24% / 42% exact line on 150 real cleared lines; full agent 43.6% on 960. |
| FastAPI endpoint and simple web page | **Not built yet.** This is the main gap against the success criteria (a cold reader cannot run it yet). |
| Talk to real clearing agents / FBR permission | **Not done.** No reply from FBR yet. |

## 2. Against the existing free tools (their public pages, checked 2026-10-18; I did not test their calculators for correctness)
| | ClearAgent HS lookup | TaxToday lookup | Ours |
|---|---|---|---|
| Finds a code from a plain description | Keyword search | Keyword search | Describes in words, asks questions, shows top 3 |
| Duties and taxes | CD, RD, ACD, sales tax, income tax (filer or not) in a calculator | Basic CD estimate only (says no ACD, RD, sales tax, income tax) | CD, RD, ACD, ST, further tax, 3% tax, IT, FED |
| Source for each figure | Not stated | General source list | Page and clause per figure |
| Dates | Results stamped with capture date | FY2026-27 only | "As of" date for FY2025-26 and FY2026-27, with the rule history |
| Concessions | Not stated | Not stated | Fifth Schedule and China FTA offered with conditions |
| Says "I'm not sure" | No | No | Yes |
| Polished, live, free | Yes | Yes | **Not yet** |
Their job is "look up a code you already know or can name"; ours is "I have a product, tell me the code and the bill, and show why". We should also offer their job (code lookup) so we are never worse than them.

## 3. Published reference points (not the same data, so not directly comparable)
* HSCodeComp (ACL 2026): the best agent reaches 46.8% at 10 digits against 95% for human experts; Gemini-2.5-Pro agents reach about 58% at 6 digits and 44% at 8 digits.
* ATLAS (2025): a fine-tuned 70B model gets 40% exact at 10 digits and 57.5% at 6 digits, 15 points above GPT-5-Thinking, by training on past customs rulings.
* A 2026 consensus (several-agent voting) framework reports about 41% exact match.
* Vendor claims of about 89% exist but come without a public benchmark, so treat them as marketing.
Our 43.6% at 8 digits (51.8% at 6, 72.5% at 4) on real cleared declarations with noisy labels sits inside this range. We are not an outlier in either direction.

## 4. What it takes to finish, and my recommendation
1. **Build the API and UI now** (the biggest missing success criterion). Include: description to candidates with the questions to answer; the bill with sources and the with/without concession views; a code-lookup mode; the date picker; the "not FBR, verify with Customs" notice; a privacy note that the text goes to the model provider.
2. **Keep an "I answered" flag in the results** so we report accuracy for answered and asked cases separately.
3. **Add a one-click "was this the right line?" with the user's consent.** Real answers to our questions plus real final codes are the data that every published method needs and that we cannot get any other way.
4. **Then improve in small steps** from that data: the ten headings with most misses (8536, 8517, 8501, 8511, 8539, 8544, 8516, 8512, 8515, 8523), better questions per heading, and (research-backed, later) training on rulings and declared codes.
5. **Documents:** ask the owner to download the three automotive and E&P SRO sets only if the target users include them (SRO 655, 656, 678); keep the 11% ACD question open.
