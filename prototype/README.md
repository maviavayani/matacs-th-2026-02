# Prototype (optional)

Two small scripts that follow the design: AI extracts, code decides.

| File | Purpose |
|---|---|
| [criteria.json](criteria.json) | What the admin screens would save: fields to extract, mandatory gates, weights, formulas. Nothing about solar is hard-coded in the scripts. |
| [extract.py](extract.py) | **AI step.** Builds the prompt from `criteria.json`, sends one call per proposal, caches the result by document hash. |
| [score.py](score.py) | **Rules step.** Verifies quotes, scans for manipulation, applies gates, scores, ranks, writes `ranking.json` plus a full run record. No AI calls. |
| [extracted_sample.json](extracted_sample.json) | Expected extraction for A–E, so scoring can run offline. Quotes are left empty because the brief asks not to copy proposal text into the repo. |

## Run the scoring offline (no API key needed)

```bash
cd prototype
python score.py --criteria criteria.json --extracted extracted_sample.json --as-of 2026-10-30
```

Expected output:

```
Prop Status      Rank  Score  Reason
A    ranked      1     98.8   Passes all mandatory checks; full marks on experience, price, timeline, team; weakest on warranty (13.75/15)
E    ranked      2     92.4   Passes all mandatory checks; full marks on warranty, team; weakest on experience (24.0/30)
C    flagged     -     85.5   Document contains text addressed to the review system (possible manipulation). | merit score 85.5 held for human review
D    flagged     -     -      Cannot confirm: Completion within 16 weeks of award
B    ineligible  -     -      Fails mandatory: Ontario electrical contractor licence held by bidder
  [E] note: Price scope not stated; confirm it covers the same items as other bids (permits, utility connection).
  [C] note: Price scope not stated; confirm it covers the same items as other bids (permits, utility connection).
  [C] note: Relevant experience: count covers 2020 onward; some work may fall outside the 5-year window (2021 onward).
  [D] note: Price scope not stated; confirm it covers the same items as other bids (permits, utility connection).
```

Try changing a weight in `criteria.json` (keeping the total at 100) and re-run: scores change with no AI call. If the weights don't total 100, the script refuses to run.

## Run the full pipeline with AI extraction

1. `pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and add your API key. `.env` is git-ignored.
3. Put each proposal's extracted text in `samples/A.txt` … `samples/E.txt`. This folder is git-ignored, so proposal text never enters the repo.
4. Run:

```bash
python extract.py --criteria criteria.json --sources samples --out output/extracted.json
python score.py   --criteria criteria.json --extracted output/extracted.json --sources samples
```

With `--sources`, `score.py` also checks that every evidence quote exists in the document and runs the manipulation pattern scan. Re-running `extract.py` uses the cache, so results are identical and cost nothing.
