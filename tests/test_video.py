# SPDX-License-Identifier: MIT
"""The ffmpeg layer and the clip-wide filter builders."""
from datetime import datetime

import numpy as np
import pytest

from underwater_color import video
from underwater_color.correct import channel_gains

requires_ffmpeg = pytest.mark.skipif(
    not video.have_ffmpeg(), reason="ffmpeg not installed"
)


def test_levels_filter_expression_shape():
    gains = np.array([2.0, 1.0, 1.0])
    los = np.array([10.0, 0.0, 0.0])
    expr = video.levels_filter(gains, los)
    assert expr.startswith("colorlevels=")
    # lo maps to rimin; hi = lo + 255/gain maps to rimax.
    assert "rimin=0.039216" in expr
    assert "rimax=0.539216" in expr
    assert "gimin=0.000000" in expr


def test_hue_shift_filter_is_a_mixer_then_levels_chain():
    """The clip-wide hue-shift: one 3x3 mixer (red row from the fitted angle,
    identity green/blue rows) followed by per-channel levels."""
    row = (0.5, 0.9, -0.4)
    los = np.array([10.0, 0.0, 5.1])
    his = np.array([200.0, 255.0, 250.0])
    expr = video.hue_shift_filter(row, los, his)
    mixer, levels = expr.split(",")
    assert mixer.startswith("colorchannelmixer=")
    assert "rr=0.500000" in mixer and "rg=0.900000" in mixer and "rb=-0.400000" in mixer
    for ident in ("gr=0", "gg=1", "gb=0", "br=0", "bg=0", "bb=1"):
        assert ident in mixer, ident
    assert levels.startswith("colorlevels=")
    assert "rimin=0.039216" in levels and "rimax=0.784314" in levels
    assert "gimin=0.000000" in levels and "gimax=1.000000" in levels
    assert "bimin=0.020000" in levels and "bimax=0.980392" in levels


@requires_ffmpeg
def test_baked_hue_shift_matches_correct_hue_shift(tmp_path):
    """Video and photo hue-shift are the same transform: the mixer+levels
    chain baked into a clip reproduces correct.hue_shift on its frames."""
    from PIL import Image
    from underwater_color.correct import hue_shift, hue_shift_params
    src = tmp_path / "src.mp4"
    video._run([
        "ffmpeg", "-nostdin", "-y", "-f", "lavfi",
        "-i", "color=c=0x203060:size=320x240:rate=10:duration=1",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "0", str(src),
    ])
    frames = video.sample_frames(src, n=4, height=240)
    stacked = np.concatenate([f.reshape(-1, 3) for f in frames]).reshape(-1, 1, 3)
    row, los, his = hue_shift_params(stacked)

    out = tmp_path / "out.mp4"
    video.transcode(src, out, crf=0, max_height=240,
                    vfilter=video.hue_shift_filter(row, los, his))
    poster = tmp_path / "p.png"
    video.extract_poster(out, poster, at=0.2, duration_s=1.0)
    got = np.asarray(Image.open(poster).convert("RGB"))

    expected = hue_shift(frames[0])
    assert np.abs(got.astype(int) - expected.astype(int)).mean() < 6


def test_preflight_raises_when_ffmpeg_missing(monkeypatch):
    monkeypatch.setattr(video, "have_ffmpeg", lambda: False)
    with pytest.raises(video.VideoError) as excinfo:
        video.preflight()
    assert "ffmpeg" in str(excinfo.value)


@requires_ffmpeg
def test_transcode_produces_a_probeable_smaller_video(tmp_path):
    src = tmp_path / "src.mp4"
    video._run([
        "ffmpeg", "-nostdin", "-y", "-f", "lavfi",
        "-i", "testsrc=size=1920x1080:rate=30:duration=2",
        "-c:v", "libx264", "-preset", "ultrafast", str(src),
    ])
    dst = tmp_path / "out.mp4"
    video.transcode(src, dst, max_height=480)
    meta = video.probe(dst)
    assert meta.height == 480
    assert meta.duration_s == pytest.approx(2.0, abs=0.2)


@requires_ffmpeg
def test_transcode_round_trips_creation_time_regardless_of_machine_tz(
        tmp_path, monkeypatch):
    """mvhd stores seconds since 1904 UTC and probe decodes them naively, so
    the value handed to `created` must come back from the transcoded file
    unchanged. A naive isoformat string is parsed by ffmpeg in the MACHINE's
    local zone, which silently shifted every imported clip's creation time by
    the importing machine's UTC offset (observed +4h/+5h across the real
    library, varying with DST at import time)."""
    monkeypatch.setenv("TZ", "America/New_York")
    src = tmp_path / "src.mp4"
    video._run([
        "ffmpeg", "-nostdin", "-y", "-f", "lavfi",
        "-i", "testsrc=size=320x240:rate=10:duration=1",
        "-c:v", "libx264", "-preset", "ultrafast", str(src),
    ])
    dst = tmp_path / "out.mp4"
    stamp = datetime(2024, 7, 9, 16, 43, 21)
    video.transcode(src, dst, max_height=240, created=stamp)
    assert video.probe(dst).created == stamp


@requires_ffmpeg
def test_extract_poster_writes_an_image(tmp_path):
    from PIL import Image
    src = tmp_path / "src.mp4"
    video._run([
        "ffmpeg", "-nostdin", "-y", "-f", "lavfi",
        "-i", "testsrc=size=320x240:rate=10:duration=2",
        "-c:v", "libx264", "-preset", "ultrafast", str(src),
    ])
    dst = tmp_path / "poster.png"
    video.extract_poster(src, dst, at=1.0, duration_s=2.0)
    assert Image.open(dst).size == (320, 240)


@requires_ffmpeg
def test_poster_at_beyond_duration_falls_back_to_midpoint(tmp_path):
    src = tmp_path / "short.mp4"
    video._run([
        "ffmpeg", "-nostdin", "-y", "-f", "lavfi",
        "-i", "testsrc=size=320x240:rate=10:duration=0.5",
        "-c:v", "libx264", "-preset", "ultrafast", str(src),
    ])
    dst = tmp_path / "poster.png"
    video.extract_poster(src, dst, at=5.0, duration_s=0.5)
    assert dst.exists() and dst.stat().st_size > 0


@requires_ffmpeg
def test_sample_frames_returns_rgb_arrays(tmp_path):
    src = tmp_path / "src.mp4"
    video._run([
        "ffmpeg", "-nostdin", "-y", "-f", "lavfi",
        "-i", "testsrc=size=320x240:rate=10:duration=2",
        "-c:v", "libx264", "-preset", "ultrafast", str(src),
    ])
    frames = video.sample_frames(src, n=4, height=120)
    assert len(frames) == 4
    assert frames[0].shape[0] == 120 and frames[0].shape[2] == 3
    assert frames[0].dtype == np.uint8


@requires_ffmpeg
def test_baked_gain_matches_channel_stretch(tmp_path):
    """THE load-bearing test: the ffmpeg filter and correct.channel_stretch are
    the same transform, so video and photo corrections agree."""
    from PIL import Image
    src = tmp_path / "src.mp4"
    # A flat, red-suppressed colour so the comparison is not confounded by
    # inter-frame codec noise on a busy test pattern.
    video._run([
        "ffmpeg", "-nostdin", "-y", "-f", "lavfi",
        "-i", "color=c=0x203060:size=320x240:rate=10:duration=1",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "0", str(src),
    ])
    frames = video.sample_frames(src, n=4, height=240)
    stacked = np.concatenate([f.reshape(-1, 3) for f in frames]).reshape(-1, 1, 3)
    gains, los = channel_gains(stacked)

    out = tmp_path / "out.mp4"
    video.transcode(src, out, crf=0, max_height=240,
                    vfilter=video.levels_filter(gains, los))
    poster = tmp_path / "p.png"
    video.extract_poster(out, poster, at=0.2, duration_s=1.0)
    got = np.asarray(Image.open(poster).convert("RGB"))

    expected = np.clip(
        (frames[0].astype(np.float32) - los) * gains, 0, 255
    ).astype(np.uint8)
    # Tolerance covers YUV 4:2:0 round-tripping, not a difference in transform.
    assert np.abs(got.astype(int) - expected.astype(int)).mean() < 6


@requires_ffmpeg
def test_sample_frames_short_clip_yields_at_least_one_frame(tmp_path):
    """A clip shorter than the requested sample count must still return
    something rather than raising — the single-invocation fps/seek math must
    not divide by a near-zero remaining duration and blow up."""
    src = tmp_path / "short.mp4"
    video._run([
        "ffmpeg", "-nostdin", "-y", "-f", "lavfi",
        "-i", "testsrc=size=320x240:rate=10:duration=0.5",
        "-c:v", "libx264", "-preset", "ultrafast", str(src),
    ])
    frames = video.sample_frames(src, n=12, height=120)
    assert len(frames) >= 1
    assert frames[0].shape[0] == 120 and frames[0].shape[2] == 3


@requires_ffmpeg
def test_sample_frames_normal_clip_returns_exactly_n(tmp_path):
    """Regression: a forward -ss seek ahead of the fps filter used to eat
    part of the sampling window and silently return n-1 frames on ordinary
    clips (reproduced on a 10s/30fps clip at the default n=12). Also asserts
    the frames actually differ, which is what would catch a regression to
    sampling n consecutive frames from the clip's opening moment instead of
    spreading them across the duration."""
    src = tmp_path / "normal.mp4"
    video._run([
        "ffmpeg", "-nostdin", "-y", "-f", "lavfi",
        "-i", "testsrc=size=320x240:rate=30:duration=10",
        "-c:v", "libx264", "-preset", "ultrafast", str(src),
    ])
    frames = video.sample_frames(src, n=12, height=120)
    assert len(frames) == 12
    assert not all(np.array_equal(frames[0], f) for f in frames[1:])


@requires_ffmpeg
def test_sample_frames_uses_injected_meta_and_skips_probe(tmp_path, monkeypatch):
    """A caller that already parsed the container (photogen's own mvhd/tkhd
    probe, in particular) must get sample_frames to use ITS answer rather
    than a second, possibly-disagreeing one from this module's ffprobe-based
    probe() — duration feeds the fps filter, so two probes could sample
    different frames and bake a different frozen clip-wide filter."""
    def _boom(_src):
        raise AssertionError("probe() must not be called when meta is injected")
    monkeypatch.setattr(video, "probe", _boom)

    src = tmp_path / "src.mp4"
    video._run([
        "ffmpeg", "-nostdin", "-y", "-f", "lavfi",
        "-i", "testsrc=size=320x240:rate=10:duration=2",
        "-c:v", "libx264", "-preset", "ultrafast", str(src),
    ])

    class _StubMeta:
        duration_s = 2.0
        width = 320
        height = 240

    frames = video.sample_frames(src, n=4, height=120, meta=_StubMeta())
    assert len(frames) == 4
    assert frames[0].shape[0] == 120 and frames[0].shape[2] == 3


@requires_ffmpeg
def test_sample_frames_probes_by_default(tmp_path):
    """Anti-vacuity for the injection test above: with no meta given,
    sample_frames still calls probe() itself and works exactly as before."""
    src = tmp_path / "src.mp4"
    video._run([
        "ffmpeg", "-nostdin", "-y", "-f", "lavfi",
        "-i", "testsrc=size=320x240:rate=10:duration=2",
        "-c:v", "libx264", "-preset", "ultrafast", str(src),
    ])
    frames = video.sample_frames(src, n=4, height=120)
    assert len(frames) == 4


@requires_ffmpeg
def test_run_error_names_the_source_file(tmp_path):
    """A VideoError raised out of a per-video build loop must name which
    file broke — otherwise a failure deep in a large library is untraceable."""
    junk = tmp_path / "not-a-video.mp4"
    junk.write_bytes(b"this is not a video file")
    with pytest.raises(video.VideoError) as excinfo:
        video._run([
            "ffmpeg", "-nostdin", "-v", "error", "-i", str(junk),
            "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
        ], capture=True, context=junk)
    assert str(junk) in str(excinfo.value)


def test_video_filter_dispatches_every_video_capable_method():
    """VIDEO_CAPABLE is the claim that a method has a clip-wide closed form,
    and video_filter is that closed form. A method added to the tuple without
    a branch here would fail at transcode time, per clip, deep in a run."""
    from underwater_color import VIDEO_CAPABLE
    from underwater_color.video import video_filter

    stacked = np.random.default_rng(0).integers(
        0, 256, size=(64, 1, 3), dtype=np.uint8)
    for method in VIDEO_CAPABLE:
        expr = video_filter(method, stacked)
        assert isinstance(expr, str) and expr


def test_video_filter_rejects_a_method_with_no_clip_wide_form():
    from underwater_color.video import video_filter

    stacked = np.zeros((8, 1, 3), dtype=np.uint8)
    with pytest.raises(ValueError, match="no clip-wide filter"):
        video_filter("ancuti-fusion", stacked)
