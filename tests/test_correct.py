# SPDX-License-Identifier: MIT
import numpy as np

from underwater_color import correct
from underwater_color.correct import (
    GENERATED_METHODS,
    MAX_CHANNEL_GAIN,
    ancuti_fusion,
    channel_stretch,
)


def _red_suppressed(h=32, w=32):
    """An underwater-like frame: green/blue span the full range, red is
    squished into a dark [0,60] band."""
    rng = np.random.default_rng(0)
    arr = np.empty((h, w, 3), dtype=np.uint8)
    arr[..., 0] = rng.integers(0, 61, size=(h, w))     # red: compressed low
    arr[..., 1] = rng.integers(0, 256, size=(h, w))    # green: full range
    arr[..., 2] = rng.integers(0, 256, size=(h, w))    # blue: full range
    return arr


def test_all_methods_preserve_shape_dtype_and_range():
    arr = _red_suppressed()
    for name, fn in GENERATED_METHODS.items():
        out = fn(arr)
        assert out.shape == arr.shape, name
        assert out.dtype == np.uint8, name
        assert out.min() >= 0 and out.max() <= 255, name


def test_channel_stretch_restores_red():
    arr = _red_suppressed()
    out = channel_stretch(arr)
    # Red was confined to <=60; after stretch it should reach near full range.
    assert out[..., 0].max() >= 240
    assert int(out[..., 0].max()) - int(arr[..., 0].max()) > 100


def _noise_floor_red(h=64, w=64):
    """A deep-water frame whose red channel carries no signal: it spans only
    ~14 of 256 levels, which is the sensor/compression noise floor. Modelled on
    photos/2025-08-14-invisibles/bba4ad4573395846 (red p0.5-p99.5 = 10-24)."""
    rng = np.random.default_rng(7)
    arr = np.empty((h, w, 3), dtype=np.uint8)
    arr[..., 0] = rng.integers(10, 25, size=(h, w))     # red: pure noise
    arr[..., 1] = rng.integers(128, 161, size=(h, w))   # green: narrow but real
    arr[..., 2] = rng.integers(163, 191, size=(h, w))   # blue: narrow but real
    return arr


def test_channel_stretch_does_not_amplify_a_noise_floor_channel():
    """A channel spanning only the noise floor must not be stretched to full
    range: doing so turns +-1 LSB of sensor noise into gross color speckle."""
    arr = _noise_floor_red()
    out = channel_stretch(arr)

    in_std = arr[..., 0].std()
    out_std = out[..., 0].std()
    assert out_std <= MAX_CHANNEL_GAIN * in_std * 1.1, (
        f"red noise amplified {out_std / in_std:.1f}x, cap is {MAX_CHANNEL_GAIN}x"
    )


def test_channel_stretch_still_stretches_below_the_cap():
    """Guard against over-clamping: a channel whose required gain is under the
    cap must still reach full range."""
    rng = np.random.default_rng(8)
    arr = np.empty((32, 32, 3), dtype=np.uint8)
    # Red spans ~85 levels -> needs gain ~3, comfortably below the cap.
    arr[..., 0] = rng.integers(0, 86, size=(32, 32))
    arr[..., 1] = rng.integers(0, 256, size=(32, 32))
    arr[..., 2] = rng.integers(0, 256, size=(32, 32))

    out = channel_stretch(arr)

    assert out[..., 0].max() >= 240


def test_channel_stretch_is_near_identity_on_balanced_image():
    rng = np.random.default_rng(1)
    arr = rng.integers(0, 256, size=(32, 32, 3), dtype=np.uint8)  # already full range
    out = channel_stretch(arr)
    assert np.abs(out.astype(int) - arr.astype(int)).mean() < 5


def test_generated_methods_are_exactly_the_six_that_earn_their_keep():
    # gray-world and white-patch were removed 2026-08-15: approved 9% / 15%
    # of the times shown (0% on noise-risk), never the sole approved variant
    # on more than 1/141 photos, and dropping both left the selector's top-1
    # unchanged while costing ~15 GB of the ~46 GB output tree. hue-shift
    # was added the same day: one global matrix rebuilding red as a
    # hue-rotated mix of R/G/B, angle from mean red, then a per-channel
    # stretch. hue-shift-clarity (2026-08-16) is
    # hue-shift plus a gated luminance-only clarity pass, in for a labeling
    # round. hue-shift-clarity-near (2026-08-17) is the same pass with the
    # gate also scaled by post-correction warmth (b*), so still-blue far
    # regions get no clarity — in for a larger eval.
    assert list(GENERATED_METHODS) == [
        "channel-stretch", "hue-shift", "hue-shift-clarity",
        "hue-shift-clarity-near", "ancuti-fusion", "dicam",
    ]
    assert not hasattr(__import__("underwater_color.correct", fromlist=["x"]), "gray_world")
    assert not hasattr(__import__("underwater_color.correct", fromlist=["x"]), "white_patch")


def test_methods_are_deterministic():
    arr = _red_suppressed()
    for fn in GENERATED_METHODS.values():
        assert np.array_equal(fn(arr), fn(arr))


def _bluish_image():
    # red suppressed (typical underwater cast), green/blue strong
    arr = np.zeros((32, 48, 3), dtype=np.uint8)
    arr[..., 0] = 40    # R low
    arr[..., 1] = 150   # G
    arr[..., 2] = 180   # B
    # add texture so CLAHE/pyramids have signal
    arr[::2, ::2, :] = arr[::2, ::2, :] // 2
    return arr


def test_ancuti_fusion_shape_dtype_and_clip():
    arr = _bluish_image()
    out = ancuti_fusion(arr)
    assert out.shape == arr.shape
    assert out.dtype == np.uint8
    assert out.min() >= 0 and out.max() <= 255


def test_ancuti_fusion_lifts_suppressed_red():
    arr = _bluish_image()
    out = ancuti_fusion(arr)
    # red channel mean should increase toward balance
    assert out[..., 0].mean() > arr[..., 0].mean()


def test_ancuti_fusion_does_not_amplify_red_noise():
    # Regression: the old multiplicative gray-world scaled the low-signal red
    # channel (and its noise) by a large gain, turning a smooth red channel into
    # the noisiest one -> visible red speckling. The reference Ancuti pipeline
    # compensates red *additively*, preserving its low contrast. So red must not
    # end up noisier than green.
    rng = np.random.default_rng(0)
    h, w = 64, 64
    arr = np.empty((h, w, 3), np.uint8)
    arr[..., 0] = np.clip(rng.normal(30, 6, (h, w)), 0, 255)   # dim, smooth red
    grad = np.linspace(80, 200, w)[None, :].repeat(h, 0)       # textured G/B
    arr[..., 1] = np.clip(grad + rng.normal(0, 6, (h, w)), 0, 255)
    arr[..., 2] = np.clip(grad + 20 + rng.normal(0, 6, (h, w)), 0, 255)
    out = ancuti_fusion(arr)
    assert out[..., 0].std() <= out[..., 1].std(), (
        f"red noise amplified: red std {out[..., 0].std():.1f} "
        f"> green std {out[..., 1].std():.1f}"
    )


def test_ancuti_fusion_deterministic():
    arr = _bluish_image()
    assert np.array_equal(ancuti_fusion(arr), ancuti_fusion(arr))


def test_ancuti_fusion_registered():
    assert GENERATED_METHODS["ancuti-fusion"] is ancuti_fusion


def test_ancuti_fusion_differs_from_plain_white_balance():
    # The full pipeline (CLAHE + weighted multi-scale fusion) must change the
    # image beyond what gray-world white balance alone produces.
    from underwater_color.correct import _white_balance
    arr = _bluish_image()
    wb_only = np.clip(_white_balance(arr), 0, 255).astype(np.uint8)
    assert not np.array_equal(ancuti_fusion(arr), wb_only)


def test_resolve_methods_accepts_known_names():
    from underwater_color.correct import resolve_methods

    assert resolve_methods(["channel-stretch", "dicam"]) == {"channel-stretch", "dicam"}


def test_resolve_methods_rejects_unknown_name_and_lists_valid_ones():
    import pytest

    from underwater_color.correct import resolve_methods

    with pytest.raises(ValueError) as exc:
        resolve_methods(["channel-strech"])          # typo
    msg = str(exc.value)
    assert "channel-strech" in msg
    assert "channel-stretch" in msg, "error must list the valid names"


def test_resolve_methods_empty_is_empty():
    from underwater_color.correct import resolve_methods

    assert resolve_methods([]) == set()


# --- hue-shift ---------------------------------------------------------------


def test_hue_shift_row_at_zero_degrees_is_identity():
    from underwater_color.correct import _hue_shift_row

    a, b, c = _hue_shift_row(0.0)
    assert abs(a - 1.0) < 1e-9 and abs(b) < 1e-9 and abs(c) < 1e-9


def test_hue_shift_row_at_ninety_borrows_green_and_subtracts_blue():
    from underwater_color.correct import _hue_shift_row

    a, b, c = _hue_shift_row(90.0)
    assert b > 0, "green must feed the reconstructed red"
    assert c < 0, "blue must be subtracted from the reconstructed red"
    # sin(90)=1, cos(90)=0: the closed forms.
    assert abs(a - (0.299 + 0.168)) < 1e-9
    assert abs(b - (0.587 + 0.330)) < 1e-9
    assert abs(c - (0.114 - 0.497)) < 1e-9


def test_hue_shift_angle_hits_anchors_and_is_monotone_decreasing():
    from underwater_color.correct import (
        HUE_SHIFT_ANGLES, HUE_SHIFT_MEAN_RED, _hue_shift_angle,
    )

    for mean_red, angle in zip(HUE_SHIFT_MEAN_RED, HUE_SHIFT_ANGLES):
        assert _hue_shift_angle(mean_red) == angle
    xs = np.linspace(-10, 300, 400)
    ys = [_hue_shift_angle(x) for x in xs]
    assert all(y1 >= y2 for y1, y2 in zip(ys, ys[1:]))
    # Clamped beyond both ends rather than extrapolated.
    assert _hue_shift_angle(-5) == HUE_SHIFT_ANGLES[0]
    assert _hue_shift_angle(255) == HUE_SHIFT_ANGLES[-1]


def test_hue_shift_output_shape_dtype_range():
    from underwater_color.correct import hue_shift

    arr = _red_suppressed()
    out = hue_shift(arr)
    assert out.shape == arr.shape
    assert out.dtype == np.uint8
    assert out.min() >= 0 and out.max() <= 255


def test_hue_shift_restores_red_on_a_red_starved_frame():
    """A deep-water frame (red carries no signal, green/blue strong): red is
    synthesised from green/blue rather than gained, so it comes back with
    substance instead of a stretched noise floor."""
    from underwater_color.correct import hue_shift

    arr = _noise_floor_red()
    out = hue_shift(arr)
    assert out[..., 0].mean() > arr[..., 0].mean() + 60


def test_hue_shift_on_red_rich_frame_uses_small_angle_and_stays_near_stretch():
    from underwater_color.correct import (
        HUE_SHIFT_HIGH_PCT, HUE_SHIFT_LOW_PCT, _hue_shift_angle, hue_shift,
    )

    rng = np.random.default_rng(3)
    arr = rng.integers(0, 256, size=(48, 48, 3), dtype=np.uint8)
    arr[..., 0] = rng.integers(140, 256, size=(48, 48))   # red-rich frame
    assert _hue_shift_angle(arr[..., 0].mean()) <= 25
    out = hue_shift(arr)
    # A plain per-channel stretch at the same percentiles.
    f = arr.astype(np.float32)
    lo = np.percentile(f.reshape(-1, 3), HUE_SHIFT_LOW_PCT, axis=0)
    hi = np.percentile(f.reshape(-1, 3), HUE_SHIFT_HIGH_PCT, axis=0)
    plain = np.clip((f - lo) * (255.0 / (hi - lo)), 0, 255).astype(np.uint8)
    assert np.abs(out.astype(int) - plain.astype(int)).mean() < 12


def test_hue_shift_flat_image_does_not_divide_by_zero():
    from underwater_color.correct import hue_shift

    arr = np.full((16, 16, 3), 77, dtype=np.uint8)
    out = hue_shift(arr)
    assert out.shape == arr.shape and out.dtype == np.uint8
    assert np.isfinite(out.astype(float)).all()


def test_hue_shift_never_applies_the_channel_gain_cap():
    """The cap exists because channel-stretch *multiplies* a starved red; hue
    shift synthesises red from G/B, so its stretch must reach full range even
    when the raw red span would have hit MAX_CHANNEL_GAIN."""
    from underwater_color.correct import hue_shift

    out = hue_shift(_noise_floor_red())
    assert out[..., 0].max() >= 240 and out[..., 0].min() <= 15


def test_hue_shift_params_agree_with_hue_shift():
    """The video path bakes (row, los, his) into ffmpeg; the closed form it
    describes must be exactly what hue_shift computes."""
    from underwater_color.correct import hue_shift, hue_shift_params

    arr = _red_suppressed()
    row, los, his = hue_shift_params(arr)
    f = arr.astype(np.float32)
    r1 = np.clip(row[0] * f[..., 0] + row[1] * f[..., 1] + row[2] * f[..., 2], 0, 255)
    mixed = np.stack([r1, f[..., 1], f[..., 2]], axis=-1)
    expected = np.clip((mixed - los) * (255.0 / (his - los)), 0, 255).astype(np.uint8)
    assert np.array_equal(hue_shift(arr), expected)


def test_hue_shift_registered_next_to_channel_stretch():
    from underwater_color.correct import hue_shift

    assert GENERATED_METHODS["hue-shift"] is hue_shift
    assert list(GENERATED_METHODS)[:2] == ["channel-stretch", "hue-shift"]


# --- hue-shift-clarity -------------------------------------------------------


def _lab(arr):
    import cv2
    return cv2.cvtColor(arr.astype(np.float32) / 255.0, cv2.COLOR_RGB2LAB)


def _l_spread(arr):
    L = _lab(arr)[..., 0]
    return float(np.percentile(L, 99) - np.percentile(L, 1))


def _textured_reef():
    """~8-px random blocks over a mid-tone bluish base — a textured subject.
    A sprinkle (~0.6%) of extreme cells pins hue-shift's 0.4/99.9 stretch so
    the mid-tone texture stays well inside [0,100] L and a local-contrast
    boost has room to widen p99-p1."""
    rng = np.random.default_rng(1)
    cells = rng.integers(-12, 13, (50, 75)).astype(float)
    ext = rng.random((50, 75))
    cells[ext < 0.006] = -90
    cells[ext > 0.994] = 90
    tex = np.kron(cells, np.ones((8, 8)))
    return np.stack([np.clip(60 + tex * 0.5, 0, 255),
                     np.clip(140 + tex, 0, 255),
                     np.clip(170 + tex, 0, 255)], -1).astype(np.uint8)   # 400x600


def test_hue_shift_clarity_preserves_shape_dtype_and_handles_tiny_images():
    from underwater_color.correct import hue_shift_clarity

    for shape in ((30, 40, 3), (64, 48, 3)):
        arr = np.random.default_rng(0).integers(0, 256, shape, dtype=np.uint8)
        out = hue_shift_clarity(arr)
        assert out.shape == arr.shape and out.dtype == np.uint8
        assert out.min() >= 0 and out.max() <= 255


def test_hue_shift_clarity_flat_image_equals_hue_shift():
    """No detail and a zero gate: the clarity pass must be a no-op."""
    from underwater_color.correct import hue_shift, hue_shift_clarity

    arr = np.full((64, 64, 3), (40, 150, 180), dtype=np.uint8)
    diff = np.abs(hue_shift_clarity(arr).astype(int) - hue_shift(arr).astype(int))
    assert diff.max() <= 1


def test_hue_shift_clarity_leaves_smooth_open_water_alone():
    """The open-water guarantee: a smooth blue gradient (no texture, faint
    8-bit banding) has near-zero fine-detail energy, so the gate suppresses
    the pass everywhere — an ungated one would draw contour rings."""
    from underwater_color.correct import hue_shift, hue_shift_clarity

    h, w = 200, 600
    g = np.linspace(0, 1, w)[None, :].repeat(h, 0)
    arr = np.stack([20 + 10 * g, 90 + 60 * g, 140 + 80 * g], -1).astype(np.uint8)
    diff = np.abs(hue_shift_clarity(arr).astype(int) - hue_shift(arr).astype(int))
    assert diff.max() <= 1


def test_hue_shift_clarity_widens_l_spread_but_leaves_color_untouched():
    """On texture the L p99-p1 spread must rise (that is the point), while
    a*/b* stay hue_shift's."""
    from underwater_color.correct import hue_shift, hue_shift_clarity

    arr = _textured_reef()
    hs, hc = hue_shift(arr), hue_shift_clarity(arr)
    assert _l_spread(hc) > _l_spread(hs)
    ab_diff = np.abs(_lab(hc)[..., 1:] - _lab(hs)[..., 1:])
    assert ab_diff.max() <= 2.0


def test_hue_shift_clarity_registered_next_to_hue_shift_and_photo_only():
    from underwater_color.correct import hue_shift_clarity

    assert GENERATED_METHODS["hue-shift-clarity"] is hue_shift_clarity
    assert list(GENERATED_METHODS)[1:3] == ["hue-shift", "hue-shift-clarity"]
    assert "hue-shift-clarity" not in correct.VIDEO_CAPABLE


def test_default_variants_is_clarity_then_near_then_hue_shift():
    assert correct.DEFAULT_VARIANTS == (
        "hue-shift-clarity", "hue-shift-clarity-near", "hue-shift")

# --- hue-shift-clarity-near --------------------------------------------------


def _warm_and_blue_texture():
    """Left half: the textured reef (warm after hue-shift). Right half: the
    same texture pattern on a strongly blue base that hue-shift cannot bring
    back to neutral. Both halves carry identical fine-detail energy, so the
    texture gate alone treats them alike; only the warmth gate tells them
    apart."""
    reef = _textured_reef()                       # 400x600, mid-tone bluish
    tex = reef.astype(int) - np.array([60, 140, 170])[None, None, :]
    blue = np.clip(np.array([5, 60, 200])[None, None, :] + tex, 0, 255).astype(np.uint8)
    return np.concatenate([reef, blue], axis=1)   # 400x1200


def test_hue_shift_clarity_near_preserves_shape_dtype():
    from underwater_color.correct import hue_shift_clarity_near

    for shape in ((1, 1, 3), (3, 5, 3), (40, 60, 3)):
        arr = np.random.default_rng(3).integers(0, 256, shape).astype(np.uint8)
        out = hue_shift_clarity_near(arr)
        assert out.shape == shape and out.dtype == np.uint8


def test_hue_shift_clarity_near_gates_blue_regions_but_not_warm_ones():
    """The point of the variant: on a frame that is textured everywhere, the
    half hue-shift left blue gets (almost) no clarity while the warm half
    gets the same clarity hue_shift_clarity gives it."""
    from underwater_color.correct import hue_shift, hue_shift_clarity, hue_shift_clarity_near

    arr = _warm_and_blue_texture()
    hs, hc, hn = hue_shift(arr), hue_shift_clarity(arr), hue_shift_clarity_near(arr)
    L = lambda a: _lab(a)[..., 0]
    warm, blue = (slice(None), slice(0, 500)), (slice(None), slice(700, None))
    # texture-only clarity moves L on both halves
    assert np.abs(L(hc) - L(hs))[blue].mean() > 0.5
    # near: warm half matches hue-shift-clarity, blue half matches hue-shift
    assert np.abs(L(hn) - L(hc))[warm].mean() < 0.15
    assert np.abs(L(hn) - L(hs))[blue].mean() < 0.15
    # color untouched, as for the sibling (the saturated blue half round-trips
    # through uint8 RGB a touch more coarsely than the reef fixture alone)
    assert np.abs(_lab(hn)[..., 1:] - _lab(hs)[..., 1:]).max() <= 2.5


def test_hue_shift_clarity_near_registered_after_clarity_and_photo_only():
    from underwater_color.correct import hue_shift_clarity_near

    assert GENERATED_METHODS["hue-shift-clarity-near"] is hue_shift_clarity_near
    assert list(GENERATED_METHODS)[2:4] == ["hue-shift-clarity", "hue-shift-clarity-near"]
    assert "hue-shift-clarity-near" not in correct.VIDEO_CAPABLE


def test_video_capable_subset():
    assert correct.VIDEO_CAPABLE == ("channel-stretch", "hue-shift")
