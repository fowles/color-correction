# 02 · The labeling protocol

*Built 2026-08-08 to 2026-08-11; used 2026-08-12 to 2026-08-17.*

Experiments [04](04-scorer-and-removal.md) and [05](05-label-round-2.md)
rest on human judgments collected with photogen's labeling server. This
page describes how those judgments were made, including the parts that limit
what they can show. The data is
[`data/variant-approvals.jsonl`](data/variant-approvals.jsonl).

## Task

A labeler sees one photo at a time as a grid of tiles: the uncorrected
`original` plus every correction available for that photo, each rendered at
1200 px on the long side and viewable enlarged. The labeler

- **approves** every tile they would accept as the published version (any
  number, including none),
- optionally **stars** one favorite, and
- submits. Rejecting every tile doubles as a vote to remove the photo.

This is approval voting rather than a forced choice or a ranking. It
replaced a first pairwise A/B design, whose 156 judgments (2026-08-10) were
discarded unanalyzed, for two reasons given in its design note: one screen
bought one comparison, mostly between tiles the labeler had no opinion on;
and pairs were drawn from the incumbent scorer's top two, so the evaluation
set was shaped by the metric being evaluated. An approval set implies every
approved tile beats every rejected one, asserts nothing within either group,
and asks directly the question a default must answer: is this one
acceptable?

## Blinding

- Tiles carry no method names until the verdict is submitted, and the page
  receives none before then.
- Tile order is shuffled per photo and per labeler, seeded from
  `crc32("<dive>|<photo>|<labeler>")`, so position carries no information
  and a labeler sees the same order if they reload.
- Each record stores a hash of every rendition shown (`images`), so a label
  can be tied to the exact pixels judged, and labels on a correction that
  was later regenerated can be detected as stale.

## Pre-approval (round 1 only)

**From 2026-08-11 until 2026-08-16, the grid opened with tiles already
approved:** the automatic scorer's pick (see [01](01-automatic-scorers.md))
plus every tile within 5% of its score. The labeler could un-approve them,
but the default was visible. photogen commits `8d006ede` (added, 2026-08-12
00:49Z) and `41206cfd` (removed, 2026-08-16 13:23Z).

This anchors labels toward the scorer's choice. Every one of the 152 round-1
records falls inside that window; none of the 198 round-2 records does. The
record format does not say which tiles were pre-approved, so the effect
cannot be undone after the fact. **Round-1 results are reported separately
and should be read as upper bounds for any method the scorer tended to pick
(`dive-plus`, `channel-stretch`, `dicam`) and as possibly depressed for the
rest.** This matters most for [04](04-scorer-and-removal.md), whose
comparisons of scorers against labels are the most exposed.

## Who labeled

Six labelers: the library's author (`labeler-1`) and five volunteers
(`labeler-2` … `labeler-6`), friends of the author. Their expertise and
viewing conditions (screen, calibration, ambient light) were not recorded.

| round | records | labelers (records each) |
| --- | ---: | --- |
| 1 · 2026-08-12 → 16, pre-approved | 152 | labeler-1 (92), labeler-2 (44), labeler-3 (16) |
| 2 · 2026-08-16/17, not pre-approved | 198 | labeler-4 (95), labeler-6 (51), labeler-5 (50), labeler-1 (2) |

**Each photo was labeled by exactly one person.** The server assigned photos
coverage-first, so no photo was ever labeled twice. The server's consensus
rule (a tile is approved when at least half the labelers who saw it approve)
therefore never combined anyone's votes, and **agreement between labelers
was never measured.** Per-labeler differences are visible — in round 1,
`labeler-3`'s 16 records disagreed with every scorer
([04](04-scorer-and-removal.md)) — but cannot be separated from differences
between the photos each person happened to get.

## Which photos

Photos were drawn from the author's own recreational dive photos: the 350
labeled photos come from 46 dives dated 2024-03 to 2025-10, and the library
they were drawn from is mostly shot on a phone (camera filenames `PXL_`).
Sampling was stratified so that rare hard cases were not swamped:

| stratum | definition (on the original's 600 px thumbnail) |
| --- | --- |
| `noise-risk` | the largest per-channel p0.5–p99.5 stretch gain is ≥ 8, i.e. some channel spans ≤ 32 of 256 levels |
| `dark` | mean luminance < 79.8, the 5th percentile over 4,167 originals (measured 2026-08-11) |
| `baseline` | everything else |

A photo in both of the first two counts as `noise-risk`. The queue gave
each stratum an even quota, redistributing a short stratum's shortfall, so
hard cases are over-represented relative to the library and pooled rates
are not library-wide estimates; per-stratum rates are in
[results](results/approvals.md). Round 1 came out 85 / 31 / 36 (baseline /
dark / noise-risk). Round 2, served by the same sampler, came out
163 / 11 / 24; why is not recorded (a likely cause is that few `dark` and
`noise-risk` photos yet had the new tiles rendered, and their shortfall went
to `baseline`). Stratified sampling was removed after round 2
(photogen `d28d5c0d`).

## Menus

What was on the grid changed between rounds, because methods were added and
removed between them:

| round | tiles |
| --- | --- |
| 1 | original, channel-stretch, gray-world, white-patch, ancuti-fusion, dicam; dive-plus where the photo had one (73 of 152) |
| 2 | original, channel-stretch, hue-shift, hue-shift-clarity, ancuti-fusion, dicam; dive-plus where present (91 of 198) |

`gray-world` and `white-patch` here are the earlier sRGB-encoded versions,
not the linear-light ones the library now ships. `hue-shift-clarity-near`
was added after round 2 and has never been labeled.

## Analysis conventions

- **Approval rate** = approved / shown, per method, with Wilson 95%
  intervals. Photos where every tile was rejected count as shown.
- **Top-1** of a rule = the share of photos with at least one approved tile
  where the rule's pick was approved.
- **Head to head** of A vs B = over photos showing both, the number where only
  A was approved and only B was (photos approving both or neither carry no
  preference).

[`analysis/approvals.py`](analysis/approvals.py) computes all of these from
the committed data; [`results/approvals.md`](results/approvals.md) is its
output.
