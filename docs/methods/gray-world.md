# gray-world

The textbook white balance: assume the scene averages to gray, and gain each
channel until it does. It is here as a classical baseline to compare against,
not as a recommendation.

## What it does

1. Decode the sRGB values to linear light.
2. Take the mean of R, G and B over the whole frame.
3. Take the target gray as the mean of those three means.
4. Multiply each channel by `gray / mean(channel)`, clip, and re-encode to
   sRGB.

The gains are measured and applied in linear light because the model is about
light, and sRGB-encoded values are not proportional to it. Balancing the
encoded values instead would leave a cast: about 7% too much red on a strong
blue-green scene.

It is a pure per-channel gain: no offset and no gain cap. Underwater, red is
the channel with the smallest mean, so it gets the largest gain. On a
red-starved frame that gain can be large, and it amplifies the red channel's
noise into speckle. `channel-stretch` caps its gain to prevent this, and
`hue-shift` avoids it by rebuilding red from green and blue. A frame
dominated by open blue water also breaks the gray-world assumption itself,
and the result is often pushed toward magenta.

It is photo-only and never in `DEFAULT_VARIANTS`. When photogen used it, it
was approved in 9% of the photos where it was shown (0% on noise-prone
frames) across 141 consensus labels, and it was the only approved variant on
just one photo. It was removed on that evidence and later restored as an
opt-in comparison. Those labels judged the earlier version, which balanced the
sRGB-encoded values; the linear-light version here has not been relabeled.

## Source

G. Buchsbaum, "A spatial processor model for object colour perception,"
*Journal of the Franklin Institute* 310(1):1–26, 1980.
[doi:10.1016/0016-0032(80)90058-7](https://doi.org/10.1016/0016-0032(80)90058-7)

Buchsbaum estimates the illuminant from the spatial average of the
photoreceptor responses, assuming the scene's average reflectance is gray.
This version is the common computational form of that model: the estimate is
taken in linear camera RGB rather than cone space, and the correction is one
gain per channel (a von Kries-style diagonal transform). The target gray is
the mean of the three channel means, which keeps overall brightness about
where it was. `ancuti-fusion` uses a percentile-trimmed version of the same
estimate.

## Code

[`gray_world` in `underwater_color/correct.py`](../../underwater_color/correct.py)
