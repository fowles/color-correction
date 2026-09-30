# white-patch

The other textbook white balance: assume the brightest thing in the frame is
white, and gain each channel until it is. It is here as a classical baseline
to compare against, not as a recommendation.

## What it does

1. Decode the sRGB values to linear light.
2. For each of R, G and B separately, find the 99th percentile value
   (`WHITE_PATCH_PCT`). Using a percentile rather than the maximum keeps a
   few hot pixels from setting the white point.
3. Divide that channel by its 99th percentile, clip, and re-encode to sRGB.

The gains are applied in linear light because the model is about light. The
99th percentile maps to white either way, but sRGB's curve is not a pure
power law, so scaling the encoded values distorts every other level. On a
strong blue-green scene that leaves red about 12% short.

It is a pure per-channel gain: black stays black. Unlike `channel-stretch`,
it does not move the low end, so a hazy frame keeps its haze. There is no
gain cap. A red channel whose 99th percentile is only a few levels above zero
gets a very large gain, and it amplifies that channel's noise into speckle.
When nothing in the frame is actually white, as with a blue-water background
and no bright subject, the result is pushed toward whatever the brightest
region happens to be.

It is photo-only and never in `DEFAULT_VARIANTS`. When photogen used it, it
was approved in 15% of the photos where it was shown (0% on noise-prone
frames) across 141 consensus labels, and it was never the only approved
variant on any photo. It was removed on that evidence and later restored as
an opt-in comparison. Those labels judged the earlier version, which balanced the
sRGB-encoded values; the linear-light version here has not been relabeled.

## Source

E. H. Land and J. J. McCann, "Lightness and Retinex Theory," *Journal of the
Optical Society of America* 61(1):1–11, 1971.
[doi:10.1364/JOSA.61.000001](https://doi.org/10.1364/JOSA.61.000001)

In Retinex, each of the three cone systems computes lightness from ratios
of light across the scene, and the area with the highest lightness in each
waveband is the reference white. This "max-RGB" white patch is the
simplified global form of that idea: it skips the spatial ratio paths and
normalizes each linear channel to its brightest value, which comes to the
same thing when the brightest area sets the white point. The percentile in
place of the maximum is specific to this library.

## Code

[`white_patch` in `underwater_color/correct.py`](../../underwater_color/correct.py)
