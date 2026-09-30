# 04 · Scorers against round-1 labels, and removing `gray-world` / `white-patch`

*2026-08-15 (US Eastern; raw timestamps 2026-08-16T02:38–04:18Z).*

## Question

At this point photogen still picked each photo's shown correction with an
automatic no-reference score ([01](01-automatic-scorers.md)). With the first
152 approval labels in hand ([02](02-labeling-protocol.md), round 1): how
well do the scorers agree with people, can a better one be built, and which
corrections are not worth generating?

## Data

Round 1 of [`data/variant-approvals.jsonl`](data/variant-approvals.jsonl):
152 records from three labelers. The evaluator dropped labels whose
renditions had since been regenerated or were missing, and photos with every
tile rejected, leaving **141 photos** (84 baseline, 29 noise-risk, 28 dark).
Image features were computed on 600 px thumbnails. **All 152 records were
collected with the scorer's pick pre-approved**, which favors whatever the
scorers already liked; see [02](02-labeling-protocol.md).

## Metrics

- **top-1:** the share of photos where the scorer's highest-scoring tile was
  approved.
- **pairs:** over every (approved, rejected) pair of tiles on a photo, the
  share the scorer orders correctly; 95% interval from a bootstrap over
  photos.
- **Paired bootstrap Δ:** 4,000 resamples of photos (`default_rng(0)`), the
  difference in top-1 between two scorers on the same resample.

## Results

**Approval by method** (`analyze1.txt`; the evaluator's 141 photos):

| method | shown | approved | rate |
| --- | ---: | ---: | ---: |
| dive-plus (app-corrected) | 70 | 64 | 91% |
| dicam | 141 | 79 | 56% |
| channel-stretch | 141 | 76 | 54% |
| ancuti-fusion | 141 | 37 | 26% |
| white-patch | 141 | 21 | 15% |
| gray-world | 141 | 12 | 9% |
| original | 141 | 6 | 4% |

(The same table over all 152 records, without the evaluator's exclusions, is
in [results](results/approvals.md#round-1-2026-08-12-to-2026-08-16-pre-filled).)

**The incumbent scorers** (`eval152.txt`, top-1 / pairs): `uciqe-nr`
74.5% / 83.9%, `uciqe-v2` 61.0% / 80.2%, `clip-iqa` 23.4% / 57.3%. On the
29 noise-risk photos `uciqe-nr` managed 44.8%.

**Which image statistics carry the signal** (`analyze1.txt`, about 45
features, each used alone as a scorer): the luminance spread
`L(p99) − L(p1)` alone reaches 85.4% pairs / 78.7% top-1, more than UCIQE
itself (80.2% / 61.0%), of which it is one term. UCIQE's other two terms,
chroma spread and mean saturation, sit at chance (57.6% and 50.4% pairs).
A logistic model over all features, cross-validated in 10 folds grouped by
photo, peaked at 80.1% top-1 (`analyze2.txt`), no better than the
two-term scorers below.

**Candidate scorers** (`analyze3.txt`), where `lc` is the luminance spread
and `k·spk` subtracts *k* times a chroma-speckle measure (the median
absolute Laplacian of CIELAB a*):

| scorer | top-1 | Δ top-1 vs `uciqe-nr`, 95% CI |
| --- | ---: | --- |
| `lc` | 78.7% | +4.3 [−0.7, +9.2] |
| `lc − 2·spk` | 80.9% | +6.4 [+2.1, +11.3] |
| `lc − 4·spk` | 81.6% | +7.1 [+2.8, +11.3] |
| `uciqe-nr`, but Dive+ first when present | 85.1% | +10.6 [+5.0, +16.3] |
| `lc − 4·spk`, Dive+ first | 86.5% | +12.0 [+6.4, +18.4] |

The largest single gain was not a better score but a rule: **show the
app-corrected version when one exists.** It held for each labeler
separately; the one exception in spirit is `labeler-3`, whose 16 records
disagreed with every scorer (43.8–56.2% top-1).

photogen adopted `contrast-nr = lc − 3·spk` with the Dive+-first rule:
86.5% top-1 / 86.4% pairs in its own evaluator (`eval152.txt`, second run).
The weight 3 was interpolated between 2 and 4; it was never run on its own.

**No image statistic reproduced the Dive+ lift** (`knob.txt`). Shaped
variants of `contrast-nr` (a saturation ceiling, a red/green band) recovered
part of it on the full menu but lost top-1 on a menu without Dive+
(75.9% → 72.2–73.1%).

**Removing methods** (`drop.txt`, `disk.txt`). A method was judged by how
often it was approved, how often it was the *only* approved tile (removing
it would leave that photo with nothing acceptable), and the scorer's top-1
without it:

| removed | photos left with no approved tile | top-1 |
| --- | ---: | ---: |
| nothing | 0 | 86.5% (n=141) |
| gray-world | 1 | 87.1% (n=140) |
| white-patch | 0 | 85.8% (n=141) |
| **gray-world + white-patch** | **1** | **86.4% (n=140)** |
| ancuti-fusion | 3 | 88.4% (n=138) |

`gray-world` and `white-patch` were approved 9% and 15% of the time, 0% on
noise-risk photos, and together cost 15.3 GB of the 46.0 GB of renditions.

## Decision

- photogen's scorer became `contrast-nr` with the Dive+-first rule.
- `gray-world` and `white-patch` were removed. (This library restored both on
  2026-09-30 as opt-in baselines, now computed in linear light — so those
  labels judged a different, sRGB-encoded implementation.)
- `ancuti-fusion` was kept: it was the only acceptable tile on 3 photos,
  though dropping it would have raised top-1.

## Caveats

- **Pre-approval** biases every number here toward the scorer that chose the
  pre-approved tiles; comparisons between scorers are the most exposed.
- Features, weights and the Dive+ rule were all chosen and evaluated on the
  same 141 photos. Only the logistic model was cross-validated. The
  bootstrap intervals describe resampling noise, not selection.
- One labeler per photo; three labelers, 92 of the 152 records from the
  author.
- The scorer approach was abandoned a day later ([05](05-label-round-2.md))
  when a fixed rule beat it on fresh, un-pre-approved labels.

## Provenance

[`raw/04-scorer-and-removal/`](raw/04-scorer-and-removal/): each `.txt` is a
tool output copied verbatim from the analysis session, with labeler names
replaced by the same pseudonyms as the data; each `.py` is the script as
recovered from that session. They import photogen internals of the time
(`photogen.variant_labels`, `photogen.quality`, since deleted) and read the
photo library, so they document the analysis rather than re-run it.
`hue-shift-under-scorer.txt` is a follow-up the same night, after
[`hue-shift`](03-hue-shift-fit.md) was added: across 4,203 photos
`contrast-nr` preferred Dive+ to `hue-shift` on all but 208 of 1,684 photos
that had both (paired median −3.9 points), though the two are close in
pixels (median RMSE 8.7 where Dive+ was approved). `hue-shift` could not be
judged by the scorer, only by labels.
