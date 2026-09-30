# hue-shift

One global 3×3 color matrix followed by a stretch. It changes each pixel on
its own, with no spatial filtering, so it is fast and has a clip-wide closed
form for video.

## What it does

1. **Rebuild red.** Replace red with `R' = clip(a·R + b·G + c·B)`, leaving
   green and blue untouched. `(a, b, c)` is the red row of a hue rotation by
   angle `h`: the chroma plane of
   [YIQ](https://en.wikipedia.org/wiki/YIQ) (luma weights 0.299 / 0.587 /
   0.114 from [ITU-R BT.601](https://www.itu.int/rec/R-REC-BT.601)) rotated
   by `h`, with luma held fixed:

       a = 0.299 + 0.701·cos h + 0.168·sin h
       b = 0.587 − 0.587·cos h + 0.330·sin h
       c = 0.114 − 0.114·cos h − 0.497·sin h

   At `h = 0` this is the identity. At large `h`, green feeds red and blue is
   subtracted.
2. **Pick the angle from the photo.** `h` is interpolated from the frame's
   mean red (`HUE_SHIFT_MEAN_RED` → `HUE_SHIFT_ANGLES`): about 90° for a
   red-starved frame, down to about 20° for one that already has red.
3. **Stretch.** Map each channel's 0.4th / 99.9th percentile (measured after
   step 1) to 0 / 255.

Red is *synthesised* from green and blue rather than amplified, so unlike
[channel-stretch](channel-stretch.md) it needs no gain cap and stays much
cleaner on red-starved frames.

## Source

The hue-rotation matrix is the standard YIQ construction above. The angle
table and stretch percentiles are this library's own: they were fitted to 160
hand-corrected original→corrected pairs, which a free linear fit showed to be
one global matrix plus offset. On those pairs this form reaches a median RMSE
of 5.2, and 4.2 on 60 held-out pairs. A pure per-channel stretch scores 23–30.

## Code

[`hue_shift` / `hue_shift_params` in `underwater_color/correct.py`](../../underwater_color/correct.py);
the video form is `hue_shift_filter` in [`video.py`](../../underwater_color/video.py).
