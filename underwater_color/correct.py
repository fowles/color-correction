# SPDX-License-Identifier: MIT
"""Algorithmic underwater color-correction methods.

Pure/leaf module — numpy in, numpy out. No file, sidecar or site knowledge,
so it is unit-testable with synthetic arrays. The clip-wide ffmpeg forms of
the two methods that have one live in video.py.
"""
from __future__ import annotations

from typing import Callable

import cv2
import numpy as np

LOW_PCT = 0.5           # channel-stretch: low percentile mapped to 0
HIGH_PCT = 99.5         # channel-stretch: high percentile mapped to 255
MAX_CHANNEL_GAIN = 6.0  # channel-stretch: ceiling on per-channel gain


def _percentile_bounds(arr: np.ndarray, low_pct: float,
                       high_pct: float) -> tuple[np.ndarray, np.ndarray]:
    """Per-channel (los, his) percentiles of an (..., 3) array, both shape (3,)
    float64. ``his`` is forced at least 1e-6 above ``los`` so a flat channel
    never divides by zero downstream."""
    flat = arr.reshape(-1, 3)
    los = np.percentile(flat, low_pct, axis=0).astype(np.float64)
    his = np.percentile(flat, high_pct, axis=0).astype(np.float64)
    his = np.maximum(his, los + 1e-6)
    return los, his


def channel_gains(arr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per-channel percentile-stretch (gains, los), both shape (3,).

    Public because it is the parameter half of channel_stretch: a caller
    baking the same correction into an ffmpeg filter (see video.py) needs the
    parameters without the pixels.

    gain[c] = 255 / (hi - lo) is how hard channel c must be stretched to fill
    the range; a balanced channel already spanning [0,255] yields gain ~= 1.

    Gains are capped at MAX_CHANNEL_GAIN. A channel spanning only a handful of
    the 256 levels carries no recoverable signal — the span *is* the
    sensor/compression noise floor — so stretching it to full range amplifies
    +-1 LSB of noise into gross color speckle rather than restoring detail.
    """
    los, his = _percentile_bounds(arr, LOW_PCT, HIGH_PCT)
    gains = np.minimum(255.0 / (his - los), MAX_CHANNEL_GAIN)
    return gains, los


def channel_stretch(arr: np.ndarray) -> np.ndarray:
    """Per-channel histogram stretch: remap [LOW_PCT, HIGH_PCT] to [0, 255]."""
    gains, los = channel_gains(arr)
    out = (arr.astype(np.float32) - los) * gains
    return np.clip(out, 0, 255).astype(np.uint8)


# --- hue-shift ---------------------------------------------------------------
#
# One GLOBAL 3x3 color matrix, applied identically to every pixel, in two steps:
#
#   1. Red reconstruction. R' = clip(a*R + b*G + c*B), with G and B passed
#      through untouched. (a, b, c) is the "hue_shift_red" row of
#      bornfree/dive-color-corrector (MIT,
#      https://github.com/bornfree/dive-color-corrector): the red primary
#      rotated by an angle h about the luma axis. The angle is looked up from
#      the frame's mean red (HUE_SHIFT_MEAN_RED -> HUE_SHIFT_ANGLES,
#      piecewise-linear): a red-starved frame gets ~90 degrees, where green
#      feeds red and blue is subtracted; an already-red frame gets ~20.
#   2. Per-channel level stretch. Each channel's HUE_SHIFT_LOW_PCT /
#      HUE_SHIFT_HIGH_PCT percentiles, measured AFTER step 1, map to 0 / 255.
#
# The angle table and the 0.4/99.9 percentiles were fitted on 2026-08-15 to
# 160 hand-corrected original->corrected pairs in this library, which a free
# linear fit showed to be a single global matrix + offset (1.1 RMSE, no
# spatial structure left in the residual). This form matches them at median
# 5.2 RMSE on the fitted pairs and 4.2 on 60 held-out pairs (p90 ~11-24),
# against 23-30 for a pure per-channel stretch (~channel_stretch); a fixed
# h=80 still lands at 5.3-5.9. Red is *synthesised* from green/blue rather than
# gained, which is why it needs no MAX_CHANNEL_GAIN and is markedly less noisy
# than channel_stretch on red-starved frames.

HUE_SHIFT_LOW_PCT = 0.4     # hue-shift stretch: low percentile mapped to 0
HUE_SHIFT_HIGH_PCT = 99.9   # hue-shift stretch: high percentile mapped to 255
# Frame mean red (0-255) -> hue-shift angle in degrees, piecewise-linear
# (np.interp; clamped beyond both ends). Redder frames need less shift.
HUE_SHIFT_MEAN_RED = (0.0, 3.0, 8.0, 15.0, 30.0, 55.0, 90.0, 140.0)
HUE_SHIFT_ANGLES = (92.0, 90.0, 81.0, 78.0, 77.0, 76.0, 62.0, 20.0)


def _hue_shift_row(h: float) -> tuple[float, float, float]:
    """(a, b, c) such that R' = a*R + b*G + c*B — the hue_shift_red row from
    bornfree/dive-color-corrector, a rotation of the red primary about the
    luma axis. h=0 is the identity (1, 0, 0); at large h green feeds red
    and blue is subtracted (c < 0)."""
    u = np.cos(np.radians(h))
    w = np.sin(np.radians(h))
    a = 0.299 + 0.701 * u + 0.168 * w
    b = 0.587 - 0.587 * u + 0.330 * w
    c = 0.114 - 0.114 * u - 0.497 * w
    return float(a), float(b), float(c)


def _hue_shift_angle(mean_red: float) -> float:
    """Shift angle for a frame whose mean red channel is ``mean_red``."""
    return float(np.interp(mean_red, HUE_SHIFT_MEAN_RED, HUE_SHIFT_ANGLES))


def _mix_red(arr: np.ndarray, row: tuple[float, float, float]) -> np.ndarray:
    """Apply the red row: float32 (..., 3) with R replaced by clip(a*R+b*G+c*B)
    and G/B untouched. Clipped here, before the stretch, exactly as ffmpeg's
    colorchannelmixer clips before colorlevels — so photo and video agree."""
    f = arr.astype(np.float32)
    r1 = np.clip(row[0] * f[..., 0] + row[1] * f[..., 1] + row[2] * f[..., 2],
                 0, 255)
    return np.stack([r1, f[..., 1], f[..., 2]], axis=-1)


def hue_shift_params(arr: np.ndarray) -> tuple[tuple[float, float, float],
                                               np.ndarray, np.ndarray]:
    """The frozen parameters hue_shift would apply to ``arr``: (red row,
    per-channel los, per-channel his), the stretch bounds measured AFTER the
    red row. The video path bakes these into one ffmpeg filter chain; the
    photo path applies them in numpy. ``arr`` may be a stack of sampled
    frames — mean red is taken over whatever it is handed."""
    row = _hue_shift_row(_hue_shift_angle(float(arr[..., 0].mean())))
    los, his = _percentile_bounds(_mix_red(arr, row), HUE_SHIFT_LOW_PCT,
                                  HUE_SHIFT_HIGH_PCT)
    return row, los, his


def hue_shift(arr: np.ndarray) -> np.ndarray:
    """Red rebuilt as a luma-axis rotation of the red primary (angle from the
    frame's mean red), then a per-channel [HUE_SHIFT_LOW_PCT,
    HUE_SHIFT_HIGH_PCT] -> [0, 255] stretch. uint8 in/out."""
    row, los, his = hue_shift_params(arr)
    out = (_mix_red(arr, row) - los) * (255.0 / (his - los))
    return np.clip(out, 0, 255).astype(np.uint8)


# --- hue-shift-clarity -------------------------------------------------------
#
# hue_shift followed by a luminance-only, texture-gated local-contrast
# ("clarity") pass. It borrows the one thing labelers seemed to like about
# ancuti-fusion: its sigma=20 unsharp step (_sharpen) is really a clarity /
# local-contrast pass. The cast and darkening they disliked came from the
# gray-world white balance and the gamma=2 fusion input, which are NOT
# borrowed — the color here is exactly hue_shift's.
#
#   * Luminance-only: the pass runs on CIELAB L with a*/b* passed through
#     untouched, so color never moves.
#   * Gated: flat open water (a smooth blue gradient, faint 8-bit banding,
#     backscatter) has near-zero fine-detail energy and gets NO clarity — an
#     ungated pass turns hue_shift's faint gradient steps into visible contour
#     rings. Textured reef/subject gets the full amount.
#   * Judged by labelers: 198 blinded labels (2026-08-16) approved it 77% of
#     the times shown and made it the favorite 24x, ahead of hue_shift (73%,
#     4x), which is why it leads DEFAULT_VARIANTS.

CLARITY_SIGMA_FRAC = 1 / 60        # wide blur sigma as a fraction of the long side (~20 px at 1200)
CLARITY_FINE_SIGMA_FRAC = 1 / 600  # fine-detail sigma as a fraction of the long side (>= 1 px)
CLARITY_GATE_LO = 0.4              # local fine-detail energy (L units, 0-100) below which no clarity
CLARITY_GATE_HI = 1.2              # ... and above which the full amount
CLARITY_AMOUNT = 0.35              # unsharp strength on L (0.5 read as over-sharpened/over-saturated on
                                   # a mid-tone subject: same a*/b* on a darker L looks more saturated)


def _wide_blur(img: np.ndarray, sigma: float, k: int) -> np.ndarray:
    """Gaussian blur of a float32 (H, W) plane at ``sigma`` px, computed on a
    copy downsampled by the integer factor ``k`` and resized back.

    A speed trick, not an approximation that matters: ``arr`` is the full-res
    source (up to ~6000 px), so ``sigma`` can be ~100 px, and a Gaussian that
    wide has no content above the Nyquist of the ``k``-times-smaller grid —
    INTER_AREA shrink, blur at sigma/k, INTER_LINEAR back reproduces it to
    rounding. k=1 is a plain blur (tiny images).
    """
    h, w = img.shape[:2]
    if k <= 1:
        return cv2.GaussianBlur(img, (0, 0), sigmaX=sigma).astype(np.float32)
    small = cv2.resize(img, (max(1, w // k), max(1, h // k)),
                       interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (0, 0), sigmaX=max(sigma / k, 0.5))
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR).astype(np.float32)


class _ClarityPrep:
    """The shared front half of the clarity variants: hue_shift, CIELAB, the
    wide local mean, and the pooled fine-detail (texture) gate. The variants
    differ only in what they multiply into ``texture`` before ``finish``."""

    def __init__(self, arr: np.ndarray):
        base = hue_shift(arr)
        self.lab = cv2.cvtColor(base.astype(np.float32) / 255.0, cv2.COLOR_RGB2LAB)
        self.L = np.ascontiguousarray(self.lab[..., 0])          # 0-100
        h, w = self.L.shape
        long = max(h, w)
        self.sigma = long * CLARITY_SIGMA_FRAC
        fine_sigma = max(long * CLARITY_FINE_SIGMA_FRAC, 1.0)
        self.k = max(1, round(long / 1200))
        self.bl = self.pool(self.L)                              # wide local mean
        # Fine-detail energy at full res (it IS the fine detail), then pooled
        # over the same wide window: the texture gate.
        fine = np.abs(self.L - cv2.GaussianBlur(
            self.L, (0, 0), sigmaX=fine_sigma).astype(np.float32))
        energy = self.pool(fine)
        self.texture = np.clip(
            (energy - CLARITY_GATE_LO) / (CLARITY_GATE_HI - CLARITY_GATE_LO), 0, 1)

    def pool(self, plane: np.ndarray) -> np.ndarray:
        return _wide_blur(np.ascontiguousarray(plane), self.sigma, self.k)

    def finish(self, gate: np.ndarray) -> np.ndarray:
        lab = self.lab
        lab[..., 0] = np.clip(self.L + CLARITY_AMOUNT * gate * (self.L - self.bl), 0, 100)
        rgb = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB) * 255.0
        return np.clip(np.rint(rgb), 0, 255).astype(np.uint8)


def hue_shift_clarity(arr: np.ndarray) -> np.ndarray:
    """hue_shift, then a texture-gated clarity pass on CIELAB L only.
    uint8 RGB in/out, same shape. See the comment block above."""
    prep = _ClarityPrep(arr)
    return prep.finish(prep.texture)


# --- hue-shift-clarity-near --------------------------------------------------
#
# hue_shift_clarity with the gate additionally scaled by post-correction
# WARMTH: the CIELAB b* (blue<->yellow) of the hue-shifted frame, pooled over
# the same wide window. hue_shift rebuilds red from green and blue with one
# global matrix; a near subject still carries enough signal for that to land
# and comes out neutral or warm, while the water column and anything far has
# had its red absorbed entirely and stays blue whatever the matrix does. So
# "how blue is it after correction" is a free distance proxy, and reading it
# off the corrected image makes the gate answer the question that matters:
# did the color correction succeed here? If so add local contrast; if not,
# leave the haze alone — sharpened haze is what read as wrong.
#
# Why: on the 2026-08-16 label round the texture gate turned out to be
# effectively binary — flat blue water off, everything else fully on (~1 over
# >=95% of the frame on 9 of 12 sampled photos, since reef-frame fine-detail
# energy is 1-8 L against a 0.4-1.2 ramp). A blinded 12-photo flip over
# alternative gates (transmission / dark-channel, warmth, Weber contrast)
# preferred the current variant on 1 of 12 and warmth on 5, so it is in for a
# larger eval as its own variant rather than a silent retune. Color is
# still untouched (a*/b* pass through) and it is photo-only like its sibling.

CLARITY_NEAR_B_LO = -25.0   # pooled b* at/below which no clarity (still blue)
CLARITY_NEAR_B_HI = 0.0     # ... at/above which the full texture-gated amount


def hue_shift_clarity_near(arr: np.ndarray) -> np.ndarray:
    """hue_shift_clarity gated also by post-correction warmth (pooled b*), so
    still-blue far regions get no clarity. uint8 RGB in/out, same shape."""
    prep = _ClarityPrep(arr)
    bstar = prep.pool(prep.lab[..., 2])
    warmth = np.clip((bstar - CLARITY_NEAR_B_LO)
                     / (CLARITY_NEAR_B_HI - CLARITY_NEAR_B_LO), 0, 1)
    return prep.finish(prep.texture * warmth)


RED_COMPENSATION_ALPHA = 1.0  # Ancuti red-channel compensation weight (paper: alpha=1)
WB_PERCENTILE = 5.0           # gray-world illuminant: exclude this % top/bottom
GAMMA = 2.0                   # input2 gamma (>1 darkens, tames over-bright cast)


def _srgb_to_linear(f01: np.ndarray) -> np.ndarray:
    """sRGB [0,1] -> linear RGB [0,1] (IEC 61966-2-1)."""
    return np.where(f01 <= 0.04045, f01 / 12.92, ((f01 + 0.055) / 1.055) ** 2.4)


def _linear_to_srgb(lin: np.ndarray) -> np.ndarray:
    """Linear RGB [0,1] -> sRGB [0,1]."""
    lin = np.clip(lin, 0.0, 1.0)
    return np.where(lin <= 0.0031308, lin * 12.92, 1.055 * lin ** (1 / 2.4) - 0.055)


def _white_balance(arr: np.ndarray) -> np.ndarray:
    """Ancuti color-compensated white balance, returns float32 [0,255].

    Faithful to Ancuti et al. 2018: (1) spatially-adaptive red-channel
    compensation and (2) a gray-world illuminant estimate with the top/bottom
    `WB_PERCENTILE`% excluded, applied in *linear* RGB.

    The red compensation is the paper's eq. (per-pixel, channels in [0,1]):

        Irc = Ir + alpha * (mean(Ig) - mean(Ir)) * (1 - Ir) * Ig

    The `(1 - Ir) * Ig` factor is essential: red is lifted *in proportion to the
    local green value*, so genuinely dark shadow pixels (low green, and whose red
    is essentially pure sensor/compression noise) are barely touched instead of
    being multiplied up into red speckle. The earlier flat additive form (from
    the simplified GitHub `main.m`) dropped this factor, leaving the low-signal
    red channel to be blown up by the subsequent gray-world gain — the source of
    the red cast and speckling. Blue is left alone (least-attenuated channel).
    """
    f01 = arr.astype(np.float32) / 255.0
    r, g, b = f01[..., 0], f01[..., 1], f01[..., 2]
    # (1) spatially-adaptive red compensation, proportional to local green
    rc = r + RED_COMPENSATION_ALPHA * (float(g.mean()) - float(r.mean())) * (1.0 - r) * g
    comp = np.stack([np.clip(rc, 0, 1), g, b], axis=-1)

    # (2) gray-world white balance in linear RGB, percentile-trimmed illuminant
    lin = _srgb_to_linear(comp)
    flat = lin.reshape(-1, 3)
    lo = np.percentile(flat, WB_PERCENTILE, axis=0)
    hi = np.percentile(flat, 100 - WB_PERCENTILE, axis=0)
    mask = np.all((flat >= lo) & (flat <= hi), axis=1)
    trimmed = flat[mask] if mask.any() else flat
    illum = np.maximum(trimmed.mean(axis=0), 1e-6)
    gains = float(illum.mean()) / illum        # map illuminant toward neutral gray
    balanced = _linear_to_srgb(lin * gains)
    return np.clip(balanced * 255.0, 0, 255).astype(np.float32)


def _gamma_correct(arr_f: np.ndarray) -> np.ndarray:
    """Gamma correction (reference input2); input/return float32 [0,255]."""
    f01 = np.clip(arr_f / 255.0, 0, 1)
    return (f01 ** GAMMA * 255.0).astype(np.float32)


SHARPEN_AMOUNT = 1.0  # unsharp-mask strength (reference input1)


def _sharpen(arr_f: np.ndarray) -> np.ndarray:
    """Unsharp-mask sharpening (reference input1): the white-balanced image plus
    its high-frequency detail (image minus a wide Gaussian blur). float32
    [0,255].

    Deliberately a bounded unsharp mask rather than the reference's
    histogram-equalized detail layer: histeq of a detail-free (flat) region is
    degenerate and manufactures speckle out of rounding noise, so flat open-water
    backgrounds would be turned noisy. A plain unsharp mask leaves flat regions
    untouched (detail ~= 0 -> no change) while still boosting real edges.
    """
    wb = arr_f.astype(np.float32)
    blurred = cv2.GaussianBlur(wb, (0, 0), sigmaX=20).astype(np.float32)
    return np.clip(wb + SHARPEN_AMOUNT * (wb - blurred), 0, 255).astype(np.float32)


def _weight_maps(arr_f: np.ndarray) -> np.ndarray:
    """Sum of Laplacian-contrast, saturation, and saliency weight maps.
    Returns float32 (H,W), strictly positive."""
    gray = cv2.cvtColor(arr_f.astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32)
    laplacian = np.abs(cv2.Laplacian(gray, cv2.CV_32F))
    chan_mean = arr_f.mean(axis=2)
    saturation = np.sqrt(((arr_f - chan_mean[..., None]) ** 2).mean(axis=2))
    blurred = cv2.GaussianBlur(arr_f, (0, 0), sigmaX=5).astype(np.float32)
    saliency = np.linalg.norm(blurred - blurred.mean(axis=(0, 1)), axis=2)
    w = laplacian + saturation + saliency + 1e-6
    return w.astype(np.float32)


def _pyramid_fuse(inputs: list[np.ndarray], weights: list[np.ndarray], levels: int = 5) -> np.ndarray:
    """Multi-scale Laplacian-pyramid fusion. inputs are float32 [0,255] (H,W,3),
    weights are float32 (H,W) already normalized to sum to 1 across inputs."""
    def gauss_pyr(img):
        pyr = [img]
        for _ in range(levels - 1):
            pyr.append(cv2.pyrDown(pyr[-1]))
        return pyr

    def lap_pyr(img):
        gp = gauss_pyr(img)
        lp = []
        for i in range(levels - 1):
            up = cv2.pyrUp(gp[i + 1], dstsize=(gp[i].shape[1], gp[i].shape[0]))
            lp.append(gp[i] - up)
        lp.append(gp[-1])
        return lp

    weight_pyrs = [gauss_pyr(w) for w in weights]
    img_pyrs = [lap_pyr(img) for img in inputs]
    blended = []
    for lvl in range(levels):
        acc = np.zeros_like(img_pyrs[0][lvl])
        for k in range(len(inputs)):
            acc += img_pyrs[k][lvl] * weight_pyrs[k][lvl][..., None]
        blended.append(acc)
    # collapse
    out = blended[-1]
    for lvl in range(levels - 2, -1, -1):
        out = cv2.pyrUp(out, dstsize=(blended[lvl].shape[1], blended[lvl].shape[0])) + blended[lvl]
    return out


def ancuti_fusion(arr: np.ndarray) -> np.ndarray:
    """Ancuti color-balance-and-fusion underwater enhancement (OpenCV)."""
    wb = _white_balance(arr)
    inp1 = _sharpen(wb)         # reference input1: sharpened white-balanced image
    inp2 = _gamma_correct(wb)   # reference input2: gamma-corrected (darkens cast)
    w1 = _weight_maps(inp1)
    w2 = _weight_maps(inp2)
    wsum = w1 + w2
    w1n, w2n = w1 / wsum, w2 / wsum
    fused = _pyramid_fuse([inp1, inp2], [w1n, w2n])
    return np.clip(fused, 0, 255).astype(np.uint8)


def dicam_correct(arr: np.ndarray) -> np.ndarray:
    """DICAM variant. Delegates to the torch-isolated module so correct.py
    itself never imports torch."""
    from underwater_color.dicam import enhance
    return enhance(arr)


def resolve_methods(names) -> set[str]:
    """Validate variant method names against GENERATED_METHODS.

    Raises ValueError naming the unknown entries and listing the valid ones,
    so a typo in ``build --force-variant`` fails loudly instead of silently
    regenerating nothing.
    """
    names = set(names)
    unknown = sorted(names - set(GENERATED_METHODS))
    if unknown:
        raise ValueError(
            f"unknown variant(s): {', '.join(unknown)}. "
            f"Valid: {', '.join(GENERATED_METHODS)}"
        )
    return names


# gray-world and white-patch were removed 2026-08-15. Against the 141
# consensus labels in variant-approvals.jsonl they were dead weight: approved
# 9% / 15% of the times shown (0% on the noise-risk stratum), the sole
# approved variant on 1 / 0 photos, and dropping both left the selector's
# top-1 unchanged (86.5% -> 86.4%) — while costing ~15 GB of the ~46 GB
# output tree and two tiles on every labeling screen. Do not re-add them.
GENERATED_METHODS: dict[str, Callable[[np.ndarray], np.ndarray]] = {
    "channel-stretch": channel_stretch,
    "hue-shift": hue_shift,
    "hue-shift-clarity": hue_shift_clarity,
    "hue-shift-clarity-near": hue_shift_clarity_near,
    "ancuti-fusion": ancuti_fusion,
    "dicam": dicam_correct,
}

# The menu. DEFAULT_VARIANTS is the set to generate when a caller expresses no
# preference of its own; ORDER IS PRECEDENCE — the first entry a given photo
# actually has is the one to show. Chosen from 198 blinded labels on
# 2026-08-16: hue-shift-clarity 77% approved / 24 favorites, hue-shift 73%,
# dicam and channel-stretch 57%, ancuti-fusion 22%. hue-shift-clarity-near
# joined 2026-08-17 for a larger eval: it is generated by default but sits
# behind hue-shift-clarity in the order above, so it surfaces only where a
# caller's own menu names it first or hue-shift-clarity is missing — see the
# comment block above it.
DEFAULT_VARIANTS: tuple[str, ...] = (
    "hue-shift-clarity", "hue-shift-clarity-near", "hue-shift")
# Methods with a clip-wide closed form that can be baked into one ffmpeg
# filter; everything else is per-frame and never offered for video.
VIDEO_CAPABLE: tuple[str, ...] = ("channel-stretch", "hue-shift")
ALL_KEYWORD = "all"
