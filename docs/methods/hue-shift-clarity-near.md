# hue-shift-clarity-near

[hue-shift-clarity](hue-shift-clarity.md) with the clarity also limited to
regions the color correction actually warmed up. In practice that means near
subjects, while distant blue water and haze are left alone.

## What it does

Everything in hue-shift-clarity, with one extra factor on the gate: the
CIELAB **b\*** (blue↔yellow) of the hue-shifted frame, pooled over the same
wide window, ramps from 0 at b\* = −25 (still blue) to 1 at b\* = 0 (neutral
or warm).

The global matrix in [hue-shift](hue-shift.md) can only rebuild red where
some signal survives. A near subject comes out neutral or warm. The water
column and distant scenery have lost their red entirely, so they stay blue
whatever the matrix does. "Still blue after correction" is therefore a free
proxy for distance. It lets the gate ask whether the correction succeeded at
each spot: if so, add local contrast; if not, leave the haze unsharpened.

## Source

This method is original to this library. On real frames the texture gate in
hue-shift-clarity turned out to be effectively on/off. In a blinded 12-photo
comparison of alternative gates (dark-channel transmission, warmth, Weber
contrast), warmth was preferred on 5 photos and the plain gate on 1. The
building blocks are the same as hue-shift-clarity's.

## Code

[`hue_shift_clarity_near` in `underwater_color/correct.py`](../../underwater_color/correct.py)
