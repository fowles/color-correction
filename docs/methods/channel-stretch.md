# channel-stretch

A per-channel percentile contrast stretch: the simplest correction here, and
the baseline the others are measured against.

## What it does

1. For each of R, G and B separately, find the 0.5th and 99.5th percentile
   values (`LOW_PCT`, `HIGH_PCT`).
2. Map that range linearly onto 0–255, clipping anything outside it.

The per-channel gain is `255 / (high - low)`, capped at `MAX_CHANNEL_GAIN`
(6.0). Underwater, red is often almost gone: a red channel that spans only a
handful of the 256 levels has no signal left to recover. That narrow span is
sensor and compression noise, so stretching it to full range would turn
±1 level of noise into heavy red speckle. The cap stops this, at the cost of
leaving very red-starved photos still somewhat blue.

It has a clip-wide closed form (ffmpeg `colorlevels`), so it is one of the
two methods offered for video.

## Source

Percentile contrast stretching is a standard intensity transformation. See
R. C. Gonzalez and R. E. Woods, *Digital Image Processing*, 4th ed.,
Pearson, 2018, §3.2 ("Contrast Stretching", p. 143). Running it on each
channel independently turns it into a crude white balance. The gain cap is
specific to this library.

## Code

[`channel_stretch` / `channel_gains` in `underwater_color/correct.py`](../../underwater_color/correct.py)
