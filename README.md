# AI Proposal Triage Design

| | |
|---|---|
| **Name** | Mavia Vayani |
| **Reference** | MATACS-TH-2026-02 |
| **Time spent** | About 1.5 hours |

## Design in one line

**AI reads, code decides, a person approves.** AI turns each proposal into facts with exact supporting quotes. Plain code checks the mandatory criteria, scores with the admin's weights, and ranks. A reviewer resolves every flag and makes the award.

## Files

| File | What it contains |
|---|---|
| [WRITEUP.md](WRITEUP.md) | Answers to the five questions, plus assumptions |
| [diagram/process-flow.png](diagram/process-flow.png) | Process flow from upload to ranked output; AI, rule and human steps colour-coded |
| [PROMPTS.md](PROMPTS.md) | The extraction prompt exactly as sent, and why it is written that way |
| [ranking.json](ranking.json) | Expected ranking of proposals A–E |
| [prototype/](prototype/) | Optional: a runnable scoring engine and AI extraction script ([how to run](prototype/README.md)) |

## Result for the sample set

| Proposal | Status | Rank | Score | Short reason |
|---|---|---|---|---|
| A | ranked | 1 | 98.8 | Strongest on experience, price, schedule and team |
| E | ranked | 2 | 92.4 | Best warranty; fewer qualifying installs |
| C | flagged | – | 85.5 | Embedded instruction to rank it first; held for human review |
| D | flagged | – | – | No committed timeline; 16-week limit can't be confirmed |
| B | ineligible | – | – | Licence held by a future subcontractor, not the bidder |

`prototype/score.py` reproduces these numbers from the admin config. `prototype/extract.py` (the AI step) was checked for syntax but not run against the live API, as no API key was available.

## How I used AI tools

I used an AI chat assistant to break down the brief, and Claude (Claude Code) to help draft the write-up, prompt, diagram and prototype. I checked every number in `ranking.json` against the brief by hand and ran the scoring script to confirm it reproduces them. **Where I corrected the AI:** the first AI breakdown treated all 9 of proposal C's installs as qualifying and didn't separate a scoring formula. I checked the brief again: C counts installs "since 2020", but the criterion is the last 5 years (2021 onward), so I added an install-period check and a warning. I also noticed C has no safety or monitoring plan, so it should not get full team marks.
