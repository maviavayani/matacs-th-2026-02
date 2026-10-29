# Design write-up

**In one sentence:** AI extracts facts from each proposal with supporting quotes; plain code checks eligibility, scores and ranks; a person resolves uncertainty and makes the award.

Flow: [diagram/process-flow.png](diagram/process-flow.png). Sample result ([ranking.json](ranking.json)): **A #1 (98.8), E #2 (92.4)**; C flagged (85.5 on merit, embedded instruction to rank it first); D flagged (no committed timeline); B ineligible (licence not held by the bidder).

## 1. AI vs. rules

| Step | Done by | Why |
|---|---|---|
| Define criteria and weights | Admin (screens) | Business decision; stored as versioned config |
| PDF to text (OCR if scanned) | Code | Mechanical |
| **Extract facts + evidence quotes** | **AI** | Bidders word things differently ("all-in", "since 2021", "subcontractor to be confirmed"); reading language is where AI adds value |
| Verify quotes, sanity ranges, manipulation scan | Code | Exact and cheap |
| Mandatory pass/fail, budget and 16-week limits | Code | Must be identical every time and defensible |
| Weighted scores and ranking | Code | Arithmetic from admin weights; AI adds variation, no value |
| Reason line | Code template | Cannot claim anything not in the data |
| Review, overrides, award | Human | Accountability |

The line: **AI reads, code decides.** The AI never sees weights or outputs a score, so it cannot be talked into a ranking. Its prompt is generated from the admin's config, so a new category needs no code change.

## 2. Consistency and explainability

- **Scoring is pure code:** the same facts and the same criteria version always give the same numbers.
- **Extraction is the only variable step**, so it is pinned down: the API enforces a JSON schema, the prompt forbids guessing, and results are **cached by a fingerprint of document, prompt version, model and criteria version**. Ranking twice reuses stored extractions, so **yes, the result is identical**. A forced re-extraction is compared field by field, with differences shown before anything changes.
- **Formulas live in the config:** experience = installs ÷ 10 (capped); price and timeline = best eligible value ÷ this proposal's; warranty = half panel (25 years = full), half workmanship compared with the best; team = 4-item checklist (lead, crew, safety plan, monitoring).
- **Reviewers see why:** for each proposal, a table of criterion → extracted value → exact quote → formula → points. Example: E timeline, "13 weeks" → 12 ÷ 13 × 15 = 13.8 points.
- Price and timeline are relative to the eligible set, which is saved with each run.

## 3. Human in the loop

1. **Admin setup:** criteria can't be saved unless weights total 100; every save is a new version.
2. **Review screen:** three lists (Ranked, Flagged, Ineligible). Ineligible proposals stay visible with their reason.
3. **Every flag needs a person:** confirm, correct, or ask the bidder (D's schedule, C's integrity issue). Nothing flagged is ranked automatically.
4. **Overrides:** a reviewer can correct any extracted value or overturn a gate (e.g. after checking a licence on the public register) with a mandatory reason; the batch is re-scored.
5. **Award:** always a human. The tool recommends; it does not choose.

**Audit log (append-only), per run:** user and time; file fingerprints; criteria version; prompt version and model ID; raw AI output; validation results; score breakdowns; every override (old value, new value, user, reason); the final decision and who made it. Replaying a run gives the same numbers.

## 4. Changing criteria

- Criteria are **versioned, never edited in place**. Every result records the version it used.
- **Weights changed:** re-score from stored extractions instantly, with no AI cost.
- **Criterion added or reworded:** only the new or changed fields are extracted, then everything is re-scored.
- Old results are kept, labelled "scored with v1, v2 available"; the reviewer sees how ranks would move before accepting.
- Changing rules after seeing bids is a fairness risk, so mid-evaluation edits need a logged reason, and criteria can be locked once proposals are uploaded.

## 5. Risks

| Risk | Safeguard |
|---|---|
| **Wrong extraction** | Quote must exist in the document; range checks; reviewer sees value beside quote |
| **Made-up facts** | "not stated" is a valid answer; unmatched quotes discard the value. Missing mandatory information is never a pass; it is flagged (D) |
| **Prompt injection** (C) | Document marked as data; AI has no scoring power and must report such text; code pattern scan as backup; proposal flagged |
| **Subtle eligibility** (B) | Prompt asks *who* holds the licence, so "licensed subcontractor to be confirmed" fails "held by the bidder" |
| **Bias** | AI never judges quality; one formula for everyone; criteria fixed before upload. Counting installs favours larger firms, a visible admin choice |
| **Apples-to-oranges prices** | Extract what the price includes; warn when not stated (C, D, E) |
| **Old experience counted** | Code checks the period against the 5-year window; C's "since 2020" is warned |
| **Poor scans** | Low OCR confidence sends the file to manual entry |
| **Cost** | One cached extraction call per proposal; weight changes need no AI call; per-run spending cap |
| **Model change** | Model ID logged; a new model must reproduce a labelled test set (like A–E) first |
| **Confidential bids** | Access control; AI provider under a no-training agreement |

## Assumptions

- The $260,000 ceiling and 16-week limit are hard requirements: exceeding them means ineligible; not stating them means flagged.
- "Last 5 years" is counted from the evaluation date (October 2026, so 2021 onward).
- A manipulation attempt is scored on merit but held for a human, not disqualified automatically; disqualification is a procurement-policy decision.
- If D confirms a schedule within 16 weeks, its $231,000 becomes the lowest eligible price, so **every** price score shifts and the whole batch is re-scored.
