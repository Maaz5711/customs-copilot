# Why the exact line is missed: error analysis of the 960 importer cases (2026-10-18, free, no new LLM calls)

Source: the full-agent results on all 960 importer cases (docs/gd_findings.md 4c). Labels are the declared codes (noisy). Only counts are written here; no case text.

## 1. The "right code in the top 3 but not first" group (124 cases) is mostly not a ranking failure
* 107 of the 124 are cases where the agent **paused to ask a question** (status paused:classification) and the importer extract cannot answer it; the evaluation then scores the candidate list it showed. Only 17 are cases where the agent committed to a wrong first code.
* Where the right code was in the list but not first it was second in 86 cases and third in 38.
* 87 of the 124 are pairs of sibling lines that are both "Other" (or specific vs "Other") inside the same heading; the words of the importer do not say which sub-line applies (voltage, capacity, vehicle type, new or used, and so on).

## 2. Behaviour against outcome (960 cases)
| Agent behaviour | Cases | Right line first | Right line in top 3, not first | Right line missing |
|---|---|---|---|---|
| Answered | 407 | 253 (62%) | 17 | 137 (34%) |
| Paused to ask | 547 | 166 (30%) | 107 | 274 |
| Refused / crashed | 6 | 0 | 0 | 6 |
So the 43.6% headline mixes two different situations: the agent answering (62% first-line match) and the agent asking a question that the test cannot answer. A real user answers the question.

## 3. Where the confident answers are wrong (137 cases with no right code in the top 3)
Relation of the agent's first code to the declared one: same 6 digits 22, same 4-digit heading 56, same chapter 31, different chapter 28. So 109 of 137 are near neighbours (national sub-lines of the same heading); 28 are other chapters (some of them questionable labels, for example a refrigerant gas declared as an integrated circuit).

## 4. No single rule would fix much
516 cases have a wrong first code, in 434 distinct (agent code, declared code) pairs; only 70 pairs repeat, covering 152 cases, and none repeats more than 3 times. The headings with the most misses: 8536 (34 of 67), 8517 (31 of 47), 8501 (29 of 66), 8511 (27 of 48), 8539 (26 of 40), 8544 (24 of 47), 8516 (22 of 54), 8512, 8515, 8523.

## 5. What this means
* A model swap does not help (docs/gd_findings.md 4e), and re-ranking would help little: the right code is already in the list; the missing information is in the importer's head.
* The measurable lever is to ask the right question and let the user answer. The importer extract cannot test that, so a real measurement needs either real users or an answering oracle that knows the declared line (an upper bound, not real accuracy).
* The evaluation should report "answered" and "asked" separately, as in section 2, so the headline is not read as the real-world accuracy.
