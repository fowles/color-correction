# 03 · Fitting `hue-shift` to app-corrected pairs

*2026-08-15 (US Eastern; raw timestamps are UTC, 2026-08-16T02:55–03:25Z).*

## Question

The photo library held about 1,700 photos that had also been corrected by the
Dive+ phone app. Its algorithm is not published. Can a small closed-form
transform reproduce those corrections, and if so, what is it? The answer
became [`hue-shift`](../methods/hue-shift.md).

## Data

Original → Dive+ pairs from the library, matched by perceptual hash when the
Dive+ exports were imported (every correction sat at Hamming distance ≤ 4 of
64 from its original, the runner-up always ≥ 10 away, on the one dive where
this was checked). At the time of the fit the glob matched 1,687 corrected
files.

- **Fit set:** 100 pairs, `random.seed(0); random.sample(pairs, 100)` over the
  sorted file list.
- **Held-out set:** 60 further pairs drawn after the fit set, disjoint from it.
- Every image EXIF-transposed and downscaled to 480 px wide.

The pairs are 160 photos in total; **the fitted parameters saw only the 100.**
Some of the library's own documentation said "fitted to 160 pairs", which was
wrong and has been corrected. The pair lists were not saved; the seeds and
sampling code are in the raw scripts, but the library has gained files since,
so re-running them now would draw different pairs.

## Method and results

RMSE is per pixel over all three channels, in 8-bit levels, at 480 px.

**1. Which model class fits Dive+?** (`diveplus_re.py`, 100 pairs)

| model of the correction | median RMSE |
| --- | ---: |
| none (original vs corrected) | 42.2 |
| per-channel affine (gain + offset) | 8.9 |
| 256-entry per-channel curve | 8.2 |
| **global 3×3 matrix + offset** | **1.1** |
| curve + matrix | 1.1 |

The residual of the matrix fit had no spatial structure: its median
correlation with local contrast, neighborhood brightness, and radial position
was 0.00–0.02, and lag-8 autocorrelation 0.05. So Dive+ applies one global
color matrix per photo, not a local operator.

**2. Its shape.** In the fitted matrices the green and blue rows are almost
diagonal (off-diagonal medians 0.003–0.014); essentially all mixing is in the
red row, where red is rebuilt from green (median weight 1.466) with blue
subtracted (−0.728). That is the shape of the red row of a hue rotation, so
the red row was refit constrained to that family — an angle, a gain and an
offset, with an optional 1.2× on the blue term (chosen for 32% of photos) —
at median RMSE 1.93 (`diveplus_dcc.py`). This recovered an angle *h* per
photo: median 80°, p10 22.8°, p90 91°. The same script ran the open-source
[dive-color-corrector](https://github.com/bornfree/dive-color-corrector),
which also rebuilds red with a hue-rotation row, on the same pairs: median
RMSE 20.7 from Dive+, with its angle rule correlating 0.61 with the fitted
angles. *h* fell
as the photo's mean red rose (correlation −0.75), from a median 90° for mean
red in (0, 5] to 65.5° above 70.

**3. A closed form.** Angle from mean red by piecewise-linear lookup (anchors
at the bucket medians, extended by hand at 0, 90 and 140), then a
per-channel percentile stretch, with the percentiles chosen from seven
settings on the fit set:

| rule (`diveplus_rules.py`) | fit, n=100: median / p90 | held out, n=60: median / p90 |
| --- | ---: | ---: |
| per-photo best angle ("oracle"), stretch 0.4/99.9 | 4.9 / 23.7 | — |
| **angle lookup, stretch 0.4/99.9 (shipped)** | **5.2 / 23.7** | **4.2 / 11.2** |
| angle from red/green ratio, 0.4/99.9 | 5.0 / 23.7 | 4.4 / 10.7 |
| fixed 80°, 0.4/99.9 | 5.3 / 21.7 | 5.9 / 9.3 |
| no rotation (pure stretch, ≈ `channel-stretch`) | 23.5 / 45.0 | 30.2 / 46.9 |

Other stretch settings on the fit set: 0.1/99.9 → 6.1, 0.5/99.9 → 5.5,
1.0/99.9 → 7.9, 0.4/99.5 → 6.8, 0.4/99.95 → 6.3, 0.4/100 → 14.1.

**4. Checks of the implementation** (`diveplus_check.py`, 40 pairs drawn from
the whole library, seeds 0 and 1): `hue-shift` median 6.1 and 6.7, against
21.2 and 13.8 for `channel-stretch`. Clipping the rebuilt red before the
stretch, as ffmpeg's `colorchannelmixer` does, left the median unchanged
(6.06) and improved p90 from 22.0 to 19.4 (80 pairs), so the library clips.

## Decision

Ship the lookup + 0.4/99.9 stretch as `hue-shift`. Its accuracy against Dive+
is close to the per-photo best angle, and far better than a per-channel
stretch.

## Caveats

- **This measures resemblance to Dive+, not quality.** Whether people prefer
  the result is [experiment 05](05-label-round-2.md), where `hue-shift` tied
  Dive+ (15–11 among photos where exactly one was approved).
- The p90 is high (≈ 24 on the fit set): a tail of photos Dive+ treats
  differently, not examined further.
- The angle table's anchors at 0, 90 and 140 were extrapolated by hand, and
  the percentiles were picked on the fit set; only the final choice was run
  on the held-out set, so the held-out number is not a fully blind estimate
  of the whole selection process.
- Whether the Dive+ exports were adjusted by hand in the app, or are its
  automatic output, was not recorded.
- The earlier "free linear fit" (step 1) and the constrained red-row fit
  (step 2) used the same 100 pairs.

## Provenance

Raw output and the recovered scripts: [`raw/03-hue-shift-fit/`](raw/03-hue-shift-fit/).
`modelclass.txt` holds only the last rows of the per-photo table and the
summary; the command piped through `tail -25`.
