# 01 · Automatic no-reference scorers

*2026-08-05 to 2026-08-13.*

Before any human labels existed, photogen chose which correction to show
for each photo with an automatic no-reference quality score over the
candidates. This page records what each scorer did and how it failed. It
explains why this library has **no scorer and no per-photo "best"**: a
fixed rule beat the last scorer on labels collected without pre-approval
([05](05-label-round-2.md)).

**Evidence tier: reported only.** These runs predate every surviving
session transcript. Their numbers survive in photogen's design notes and
commit messages (a private repository), quoted below. No raw output or
script was kept.

## CLIP-IQA (2026-08-05/06)

A CLIP ViT-B/32 model scored each candidate by the softmax of its similarity
to "a natural, well color-balanced underwater photo" against "an unnatural,
color-distorted underwater photo", after Wang et al. (2023).

> Across all 169 scored photos × 5 variants, every score lands in
> 0.4887–0.5095, mean best-vs-worst spread 0.003. Selection is effectively
> noise; `original` wins 131/169 times. […] in 5 of 6 hand-labelled
> ground-truth photos the raw metric ranks `original` at or above the
> variant a human prefers.

The softmax was missing CLIP's logit scale, which explains the compressed
range but not the wrong ordering. CLIP-IQA was never re-run with the scale
fixed.

## UCIQE (2026-08-06 to 2026-08-09)

UCIQE (Yang & Sowmya, 2015) is a published underwater quality metric: a
weighted sum of chroma spread, luminance contrast (p99 − p1 of L), and mean
saturation in CIELAB.

- On the same 6 hand-labelled photos it ranked the wanted correction first
  on all 6, by 10–25 points.
- On all 3,899 cached photos it picked `channel-stretch` 54.4%, `dicam`
  27.3%, Dive+ 16.4%, `white-patch` 1.1%, `ancuti-fusion` 0.7%, and never
  `gray-world` or `original`.

A decomposition then showed why that was not trustworthy:

> UCIQE is ~93% one term. Decomposing the score over 150 sampled photos,
> the luminance 1–99 percentile spread contributes 93.2% of the total,
> chroma standard deviation 5.9%, saturation 1.0%. […] `original` never
> wins, on any photo, and ranks a median 6th of 8 candidates. […] 34% of
> photos have a winner-vs-runner-up margin below 1.0 UCIQE point.

The implementation also had a unit error: it read PIL's CIELAB with L in
0–255 and a*/b* offset incorrectly. Fixing it changed the shown correction
on 696 of 4,279 photos (16.3%), always between two corrected versions.
After the fix the luminance term was about 83% of the score rather than 93%.

**The failure that mattered:** a percentile stretch widens exactly what
UCIQE mostly measures. On a photo whose red channel spanned 14 levels,
`channel-stretch` applied an 18.2× gain that turned sensor noise into
magenta speckle, and UCIQE rated the result 42.11 against 5.96 for the
original. This led directly to capping `channel-stretch`'s gain at 6×
and to building the labeling protocol ([02](02-labeling-protocol.md)), so
that a scorer could be tested at all.

## `uciqe-nr`: a noise penalty (2026-08-13)

UCIQE minus 4 × a chroma-speckle term (the median absolute Laplacian of
CIELAB a*). On the first 41 labeled photos, with pre-approval
([02](02-labeling-protocol.md)), top-1 rose from 51.2% (±14.6) to 70.7%
(±13.4), and on noise-risk photos from 27.8% to 55.6% (n = 18). Weights
from 2.5 to 7 gave the same top-1.

The label-based scorer work that followed, `contrast-nr`, is
[04](04-scorer-and-removal.md).

## Sources

- CLIP-IQA: J. Wang, K. C. K. Chan and C. C. Loy, "Exploring CLIP for
  Assessing the Look and Feel of Images," *AAAI* 2023.
  [doi:10.1609/aaai.v37i2.25353](https://doi.org/10.1609/aaai.v37i2.25353)
- UCIQE: M. Yang and A. Sowmya, "An Underwater Color Image Quality
  Evaluation Metric," *IEEE Transactions on Image Processing*
  24(12):6062–6071, 2015.
  [doi:10.1109/TIP.2015.2491020](https://doi.org/10.1109/TIP.2015.2491020)
- photogen `docs/superpowers/specs/2026-08-06-uciqe-variant-selection-design.md`
  and `2026-08-08-variant-selection-ground-truth-design.md`; commits
  `8468f09d` (LAB fix) and `4b269436` (`uciqe-nr`).
