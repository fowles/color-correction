# ancuti-fusion

The classical color-balance-and-fusion method of Ancuti et al.: correct the
color, derive two differently enhanced versions of the photo, and blend them
pixel by pixel wherever each one looks better.

## What it does

1. **Red compensation.** Lift red in proportion to the local green, per
   pixel (channels in 0–1, α = 1):
   `Rc = R + α · (mean(G) − mean(R)) · (1 − R) · G`.
   The `(1 − R) · G` factor matters: dark shadows, whose red is only noise,
   are barely touched instead of being amplified into red speckle.
2. **White balance.** Gray-world illuminant estimate in linear RGB,
   excluding the top and bottom 5% of pixels.
3. **Two inputs.** A sharpened copy (unsharp mask, σ = 20) and a gamma-2
   copy, which darkens and reduces the washed-out look.
4. **Weight maps** for each input: Laplacian contrast + saturation +
   saliency.
5. **Multi-scale fusion.** Blend the inputs using a 5-level Laplacian
   pyramid of each input and a Gaussian pyramid of its normalized weight.

## Source

C. O. Ancuti, C. Ancuti, C. De Vleeschouwer and P. Bekaert, "Color Balance
and Fusion for Underwater Image Enhancement," *IEEE Transactions on Image
Processing* 27(1):379–393, 2018.
[doi:10.1109/TIP.2017.2759252](https://doi.org/10.1109/TIP.2017.2759252)

One deliberate departure: the paper's sharpened input adds a
histogram-equalized detail layer. On a flat region, histogram equalization
turns rounding noise into speckle, so open-water backgrounds came out noisy.
This implementation uses a plain unsharp mask, which leaves flat regions
unchanged.

## Code

[`ancuti_fusion` in `underwater_color/correct.py`](../../underwater_color/correct.py)
