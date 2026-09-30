# Experiments

The evaluations behind this library's methods and its default menu, written
up with their data, raw outputs and known weaknesses. They were run between
2026-08-05 and 2026-09-30, first inside
[photogen](https://github.com/fowles/photogen), the photo-site generator this
library was extracted from, and are recorded here so that every claim in the
code and [method docs](../methods/) can be traced to its evidence.

These are engineering evaluations, not yet a study: small, often one rater,
with decisions sometimes made on the same data that justifies them. Each
page says where that applies.

## Index

| # | experiment | what it decided | evidence |
| --- | --- | --- | --- |
| [01](01-automatic-scorers.md) | automatic no-reference scorers (CLIP-IQA, UCIQE, `uciqe-nr`) | scorers could not be trusted without labels | reported |
| [02](02-labeling-protocol.md) | the human labeling protocol | how 04–05 were judged | method |
| [03](03-hue-shift-fit.md) | fitting a closed form to app-corrected pairs | `hue-shift` and its constants | raw |
| [04](04-scorer-and-removal.md) | scorers against round-1 labels | removing `gray-world` / `white-patch` | raw + data |
| [05](05-label-round-2.md) | round-2 labels | the fixed menu, `DEFAULT_VARIANTS` | **reproducible** |

**Evidence tiers.** *Reproducible:* recomputed from committed data by a
committed script, and checked by the test suite. *Raw:* the original tool
output and scripts are committed verbatim, but re-running them needs the
photo library. *Reported:* only the numbers quoted in photogen's commit
messages or design notes survive.

## Layout

- [`data/`](data/): the approval-vote labels, pseudonymized, with a
  description of every field.
- [`analysis/approvals.py`](analysis/approvals.py): recomputes every table
  in [`results/approvals.md`](results/approvals.md) from `data/`. Standard
  library only:

  ```bash
  uv run python docs/experiments/analysis/approvals.py > docs/experiments/results/approvals.md
  ```

  `tests/test_experiments.py` fails if the committed results differ from
  what the script prints.
- [`raw/`](raw/): per experiment, tool output copied verbatim from the
  sessions that ran it, and the scripts that produced it. See
  [`raw/README.md`](raw/README.md) for how they were recovered.

## What the evidence supports

- People almost never accepted the uncorrected photo (4–6%), so correcting
  by default is right.
- `hue-shift` reproduces the Dive+ app closely (median RMSE 4.2 on held-out
  pairs, against 30.2 for a per-channel stretch) and people rated it level
  with the app (11–15 head to head).
- The hue-shift family was approved more often than `channel-stretch`,
  `dicam` or `ancuti-fusion` (73–77% against 57%, 57% and 22%), and by a
  wide margin on noise-prone photos.
- Always showing `hue-shift-clarity` did at least as well as photogen's
  best automatic scorer (80.1% against 77.5% top-1).

## What it does not yet support

- That `hue-shift-clarity` beats plain `hue-shift` (28–20, p ≈ 0.31).
- Anything about `hue-shift-clarity-near`, which has never been labeled.
- Anything about the current linear-light `gray-world` and `white-patch`:
  the labels judged earlier sRGB versions.
- Agreement between people: no photo was labeled twice.

## Threats to validity

These apply across experiments; each page adds its own.

1. **One labeler per photo.** 350 labels cover 350 photos. Inter-rater
   agreement is unknown, and individual taste is confounded with photo
   content.
2. **Pre-approval in round 1.** The first 152 labels were collected with the
   automatic scorer's choice already approved ([02](02-labeling-protocol.md)).
3. **Selection on the evaluation data.** Several parameters were chosen on
   the same photos used to report them: the stretch percentiles, the scorer
   weights, the menu rule.
4. **The author as rater.** The author supplied 94 of the 350 labels.
5. **One photographer, one library.** Every photo comes from the author's
   own dives, mostly shot on one phone. Nothing here is known to generalize
   to other cameras, depths, water or lighting.
6. **Dive+ as a reference.** It is a commercial app's output, used both as a
   fitting target (03) and as a labeled candidate (04, 05). Whether its
   exports were adjusted by hand was not recorded.
7. **Unrecorded viewing conditions.** Screens, calibration and surroundings
   were not controlled.

## Toward a publishable study

What these results suggest running next, roughly in order of value:

1. **A multi-rater round** on a fixed, pre-registered photo set, with every
   photo seen by several labelers, to measure agreement and to test
   `hue-shift-clarity` against `hue-shift` with adequate power (the round-2
   split would need several hundred discordant photos).
2. **Held-out photos** for every tuned parameter, chosen before tuning.
3. **Label `hue-shift-clarity-near`** and the linear-light classical
   baselines.
4. **Other photographers' images**, and public benchmarks (for example
   UIEB, whose reference images are themselves chosen by human preference),
   so the results can be compared with published methods.
