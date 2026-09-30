# hue-shift-clarity

[hue-shift](hue-shift.md) for color, then a local-contrast ("clarity") pass
that changes brightness only and skips flat open water. It leads the default
menu: in 198 blinded labels it was approved 77% of the times it was shown and
picked as favorite 24 times, ahead of hue-shift's 73% and 4.

## What it does

1. Run [hue-shift](hue-shift.md).
2. Convert to [CIELAB](https://en.wikipedia.org/wiki/CIELAB_color_space).
   The rest of the method touches only lightness **L**; a\* and b\* pass
   through, so the color is exactly hue-shift's.
3. **Clarity.** An unsharp mask on L with a wide Gaussian (σ = 1/60 of the
   long side, about 20 px at 1200 px) at strength 0.35:
   `L' = L + 0.35 · gate · (L − blur(L))`.
4. **Texture gate.** Measure fine-detail energy (|L − a σ ≈ 1/600 blur of
   L|, pooled over the same wide window) and ramp the gate from 0 at 0.4 to 1
   at 1.2. Flat water, faint 8-bit banding and backscatter get no clarity,
   which keeps them from sharpening into visible contour rings. Textured reef
   and subjects get the full amount.

## Source

This method is original to this library. It borrows one idea from
[ancuti-fusion](ancuti-fusion.md): Ancuti et al.'s σ = 20 sharpening input
really works as a clarity pass, and it was what labelers liked about that
method. Its white balance and gamma input, which labelers disliked, are not
borrowed. The unsharp mask is the standard one; see Gonzalez and Woods,
*Digital Image Processing*, 4th ed., §3.6 ("Unsharp Masking and Highboost
Filtering", p. 206).

## Code

[`hue_shift_clarity` / `_ClarityPrep` in `underwater_color/correct.py`](../../underwater_color/correct.py)
