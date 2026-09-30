# 05 · Round 2: a fixed menu instead of a scorer

*Labels 2026-08-16/17 (22:34Z–01:29Z); analysis 2026-08-16 (US Eastern).*

## Question

`hue-shift` ([03](03-hue-shift-fit.md)) and
[`hue-shift-clarity`](../methods/hue-shift-clarity.md) were new and had no
labels. The automatic scorer could not judge them fairly ([04](04-scorer-and-removal.md)). Do people prefer
them, and does picking per photo with a scorer beat simply always showing
the same method?

## Data

Round 2 of [`data/variant-approvals.jsonl`](data/variant-approvals.jsonl):
**198 photos, one labeler each** (`labeler-4` 95, `labeler-6` 51,
`labeler-5` 50, `labeler-1` 2), **without pre-approval**
([02](02-labeling-protocol.md)). Each grid showed `original`,
`channel-stretch`, `hue-shift`, `hue-shift-clarity`, `ancuti-fusion`,
`dicam`, and Dive+ where the photo had one (91 photos). 7 photos had every
tile rejected.

## Results

Recomputed from the committed data by
[`analysis/approvals.py`](analysis/approvals.py); full tables, including by
stratum, in [results](results/approvals.md#round-2-2026-081617-not-pre-filled).

| method | shown | approved | rate (95% CI) | favorite |
| --- | ---: | ---: | --- | ---: |
| hue-shift-clarity | 198 | 153 | 77% (71–83%) | 24 |
| dive-plus (app-corrected) | 91 | 70 | 77% (67–84%) | 2 |
| hue-shift | 198 | 145 | 73% (67–79%) | 4 |
| channel-stretch | 198 | 113 | 57% (50–64%) | 3 |
| dicam | 198 | 113 | 57% (50–64%) | 4 |
| ancuti-fusion | 198 | 44 | 22% (17–29%) | 6 |
| original | 198 | 11 | 6% (3–10%) | 0 |

**Head to head**, counting photos where exactly one of the two was approved:

| A vs B | only A | only B |
| --- | ---: | ---: |
| hue-shift-clarity vs hue-shift | 28 | 20 |
| hue-shift vs dive-plus | 11 | 15 |
| hue-shift vs dicam | 62 | 30 |
| hue-shift vs channel-stretch | 62 | 30 |
| hue-shift-clarity vs dicam | 66 | 26 |

**By stratum**, the gap widens on hard photos: on the 24 noise-risk photos
`dicam` was approved 3 times (12%) and `channel-stretch` 9 (38%), against 18
and 19 for the two hue-shift methods.

**Fixed rules against the scorer.** On the 191 photos with at least one
approved tile:

| rule | top-1 |
| --- | ---: |
| photogen's scorer (`contrast-nr`, Dive+ first) | 77.5% |
| always `hue-shift` | 75.9% |
| **always `hue-shift-clarity`** | **80.1%** (153/191) |
| Dive+ if present, else `hue-shift-clarity` | 81.2% (155/191) |

The scorer's figure needs its per-photo scores, which are not part of the
committed data; it is from `raw/05-label-round-2/round2_scorer.txt`.

## Decision

photogen deleted its scorer — `contrast-nr`, UCIQE, CLIP-IQA and the
per-photo "best" — for a fixed menu, ordered by precedence:
`hue-shift-clarity`, then `hue-shift`. That is this library's
`DEFAULT_VARIANTS` today (with `hue-shift-clarity-near`, added later and never
labeled, between them).

## Caveats

- **Clarity over plain `hue-shift` is not established.** 28–20 is well within
  chance for 48 discordant photos (two-sided sign test p ≈ 0.31). The
  favorite count (24 vs 4) points the same way and is the stronger evidence,
  but a favorite is a single star per photo with no interval.
- **`hue-shift` vs Dive+ is a tie** (11–15, sign test p ≈ 0.56), which is
  the claim that matters for `hue-shift` as a stand-in for the app.
- The fixed rule was chosen after seeing these labels and is scored on them;
  the scorer, by contrast, was fitted on round 1. The comparison favors the
  rule. The scorer's 77.5% also lies inside the fixed rule's 95% interval
  (73.9–85.1%): the claim is "no better than a fixed rule", not "worse".
- "The scorer" here is the one photogen used, not the best possible scorer;
  only this one was run on round 2.
- One labeler per photo; 196 of the 198 from three volunteers who had not
  labeled in round 1.

## Provenance

[`raw/05-label-round-2/`](raw/05-label-round-2/): `round2_inline.txt` is the
first tabulation of these rows and matches the committed analysis exactly;
`round2_scorer.txt` scores photogen's scorer and the fixed rules;
`eval348.txt` is the old scorer evaluator's last run over both rounds, and
`eval_menu.txt` its replacement's first; `favorites.txt` counts favorites,
used to carry each photo's favorite over as an extra shown version.
