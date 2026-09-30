# SPDX-License-Identifier: MIT
"""The ffmpeg layer: applying a correction to a clip, and the clip-wide closed
forms of the methods that have one.

Leaf module — stdlib and numpy only, plus correct.py for the two parameter
functions. A correction that can be expressed as one ffmpeg filter is baked
once per clip from sampled frames and frozen for its whole length: per-frame
estimation makes the color breathe.

Container introspection (duration, dimensions, camera identity) is
deliberately NOT here — that is the caller's domain, not color's. The one
exception is the tiny ``probe`` below: it exists only so ``sample_frames``
can learn a clip's duration/dimensions and so tests can verify what
``transcode``/``extract_poster`` actually produced, and it deliberately reads
that handful of fields via ``ffprobe`` rather than porting photogen's
byte-level mvhd/tkhd/EXIF parser (camera identity, orientation, and the rest
of that parser stay in photogen — this module never touches them).
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

FFMPEG_MISSING_MSG = (
    "ffmpeg is required to process video but was not found on PATH.\n"
    "  Install it with:  brew install ffmpeg\n"
    "  (both `ffmpeg` and `ffprobe` are needed.)"
)


class VideoError(RuntimeError):
    """A video operation failed. Carries an actionable message."""


def have_ffmpeg() -> bool:
    import shutil
    return shutil.which("ffmpeg") is not None


def preflight() -> None:
    """Fail early and actionably when ffmpeg is missing.

    Called once before any video work rather than per-video, so a missing
    binary costs a message at second zero instead of surfacing hours into a
    long run.
    """
    if not have_ffmpeg():
        raise VideoError(FFMPEG_MISSING_MSG)


def _run(argv: list[str], *, capture: bool = False, context=None) -> bytes:
    """Run an ffmpeg-family command, raising VideoError with stderr on failure.

    A list argv with no shell: album titles and dive-site names reach these
    paths, and some contain quotes and apostrophes.

    ``context`` (typically the source Path) is folded into the error message
    so a failure raised out of a per-video build loop over a large library
    names which file broke, rather than reading as a bare "ffmpeg failed (1)"
    with no way to tell the culprit apart from every other video.
    """
    try:
        proc = subprocess.run(
            argv,
            stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError as exc:
        raise VideoError(FFMPEG_MISSING_MSG) from exc
    if proc.returncode != 0:
        tail = (proc.stderr or b"").decode("utf-8", "replace").strip().splitlines()
        where = f" on {context}" if context is not None else ""
        raise VideoError(
            f"{argv[0]} failed{where} ({proc.returncode}): " + " / ".join(tail[-3:])
        )
    return proc.stdout or b""


@dataclass
class _ProbedVideo:
    """The handful of fields ``sample_frames`` and the video tests need.

    NOT a port of photogen's ``VideoMeta`` — no camera identity, no
    orientation, no EXIF. Just duration/dimensions/creation-time, read via
    ``ffprobe`` rather than parsed by hand out of the mvhd/tkhd atoms.
    """
    width: int | None
    height: int | None
    duration_s: float | None
    created: datetime | None


def probe(path: Path) -> _ProbedVideo:
    """Read duration, dimensions and creation time via ffprobe. Never raises:
    an unreadable file yields a probe with every field None, mirroring
    photogen's own probe() contract of "never raises, missing signal is
    just None"."""
    try:
        out = _run([
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries",
            "stream=width,height:format=duration:format_tags=creation_time",
            "-of", "json", str(path),
        ], capture=True, context=path)
    except VideoError:
        return _ProbedVideo(None, None, None, None)
    try:
        data = json.loads(out or b"{}")
    except json.JSONDecodeError:
        return _ProbedVideo(None, None, None, None)
    stream = (data.get("streams") or [{}])[0]
    fmt = data.get("format") or {}
    width = stream.get("width")
    height = stream.get("height")
    duration_s = float(fmt["duration"]) if fmt.get("duration") else None
    created = None
    tag = (fmt.get("tags") or {}).get("creation_time")
    if tag:
        try:
            created = datetime.strptime(
                tag.split(".")[0].rstrip("Z"), "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            created = None
    return _ProbedVideo(width, height, duration_s, created)


def levels_filter(gains, los) -> str:
    """An ffmpeg ``colorlevels`` expression equivalent to correct.channel_stretch.

    channel_stretch maps [lo, lo + 255/gain] onto [0, 255] per channel and
    clips. colorlevels maps [Nimin, Nimax] onto [Nomin, Nomax] with the same
    clipping, in 0..1 units — so imin = lo/255 and imax = (lo + 255/gain)/255.

    The gains are computed ONCE from sampled frames and frozen for the whole
    clip. That is deliberate: per-frame re-estimation makes the correction
    breathe visibly on any clip whose content changes, which reads as a fault
    in the video rather than a correction.
    """
    his = [float(lo) + 255.0 / max(float(g), 1e-6) for g, lo in zip(gains, los)]
    return _levels_expr(los, his)


def _levels_expr(los, his) -> str:
    """``colorlevels`` mapping per-channel [lo, hi] (0..255) onto [0, 255]."""
    parts = []
    for idx, key in enumerate("rgb"):
        parts.append(f"{key}imin={float(los[idx]) / 255.0:.6f}")
        parts.append(f"{key}imax={float(his[idx]) / 255.0:.6f}")
    return "colorlevels=" + ":".join(parts)


def hue_shift_filter(row, los, his) -> str:
    """An ffmpeg chain equivalent to correct.hue_shift: one ``colorchannelmixer``
    whose red row is ``row`` (a, b, c) over identity green/blue rows, then the
    ``colorlevels`` stretch of [lo, hi] -> [0, 255] per channel. Like
    levels_filter, the parameters are estimated once from sampled frames and
    frozen for the whole clip — never re-estimated per frame. The mixer clips
    to [0, 255] before the levels stage, matching correct._mix_red.
    """
    a, b, c = (float(v) for v in row)
    mixer = ("colorchannelmixer="
             f"rr={a:.6f}:rg={b:.6f}:rb={c:.6f}:"
             "gr=0:gg=1:gb=0:br=0:bg=0:bb=1")
    return mixer + "," + _levels_expr(los, his)


def _scale_filter(max_height: int) -> str:
    """Downscale to max_height, never upscale, keeping dimensions even.

    H.264 with yuv420p requires even dimensions; -2 lets ffmpeg pick the width
    that preserves aspect ratio and satisfies that.
    """
    return f"scale=-2:'min({max_height},ih)'"


def transcode(src: Path, dst: Path, *, crf: int = 23, max_height: int = 1080,
              encoder: str = "libx264", vfilter: str | None = None,
              created: datetime | None = None) -> None:
    """Encode a web-playable MP4: H.264 + AAC, faststart, optional color filter."""
    chain = [_scale_filter(max_height)]
    if vfilter:
        chain.append(vfilter)
    argv = [
        "ffmpeg", "-nostdin", "-y", "-i", str(src),
        "-vf", ",".join(chain),
        "-c:v", encoder, "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
    ]
    if encoder == "libx264":
        argv += ["-preset", "medium", "-crf", str(crf)]
    else:
        # VideoToolbox has no CRF; approximate with a quality scale.
        argv += ["-q:v", str(max(1, min(100, 100 - crf * 2)))]
    if created is not None:
        # `created` is the naive decode of the source's mvhd creation time,
        # whose epoch-seconds are UTC by spec. The explicit Z matters: ffmpeg
        # parses a bare isoformat string in the MACHINE's local zone, which
        # would shift the stored time by the importing machine's UTC offset.
        argv += ["-metadata", f"creation_time={created.isoformat()}Z"]
    # Explicit muxer, not inferred from dst's extension: callers write through
    # a temp path first (import's ``<dest>.part``, for atomic rename), so the
    # final path component ffmpeg would sniff is ".part", not ".mp4" — with no
    # ``-f`` it fails "Error initializing the muxer" for every such caller.
    argv += ["-f", "mp4"]
    argv.append(str(dst))
    dst.parent.mkdir(parents=True, exist_ok=True)
    _run(argv, context=src)


def _clamp_poster_at(at: float, duration_s: float | None) -> float:
    """Keep the poster offset inside the clip.

    A clip shorter than the configured offset posters from its midpoint, so a
    two-second clip can never yield an empty poster.
    """
    if duration_s is None or duration_s <= 0:
        return max(0.0, at)
    if at >= duration_s:
        return duration_s / 2.0
    return max(0.0, at)


def extract_poster(src: Path, dst: Path, *, at: float = 1.0,
                   duration_s: float | None = None) -> None:
    """Write a single full-resolution frame as the clip's poster image."""
    seek = _clamp_poster_at(at, duration_s)
    dst.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-nostdin", "-y", "-ss", f"{seek:.3f}", "-i", str(src),
        "-frames:v", "1", "-q:v", "2", str(dst),
    ], context=src)


def sample_frames(src: Path, n: int = 12, *, height: int = 240, meta=None) -> list:
    """Decode ``n`` evenly-spaced frames as small RGB arrays, in one ffmpeg call.

    ``meta``, if given, is used instead of calling ``probe(src)`` — duck-typed:
    anything with ``.duration_s``, ``.width`` and ``.height`` will do. This
    exists for a caller that has already parsed the container itself (e.g.
    photogen's own mvhd/tkhd probe, which knows things this module's ffprobe-
    based ``probe()`` does not, such as a raw/malformed container's real
    dimensions): it should not pay for a second probe, and — more importantly
    — must not risk a second, disagreeing answer. Duration is the input to
    the fps filter below, so two probes reaching different durations would
    sample different frames, bake a different frozen filter, and change
    rendition bytes for a clip where nothing about the correction changed.

    Small by design: these only feed percentile statistics, so full resolution
    would cost decode time and memory for no change in the resulting gains.

    A single invocation, not one process per frame: an ``fps`` filter set to
    ``n/duration``, spanning the whole clip from t=0, lands on n evenly
    spaced timestamps (0, D/n, 2D/n, ... (n-1)D/n) while paying for exactly
    one container open and one decode pass. Output frames come back
    concatenated on one rawvideo pipe and are split by a fixed per-frame byte
    stride, which is why the scale target is an explicit, even width rather
    than ffmpeg's aspect-preserving ``-2`` shorthand (whose exact rounding
    isn't ours to predict) — we compute the same even-width aspect scale
    ourselves so the stride is known up front.

    Deliberately does NOT seek forward to bucket-centre the first sample
    (skipping the clip's opening moment) the way the old per-frame ``-ss``
    loop did: an early version of this single-invocation rewrite did exactly
    that (``-ss D/(2n)`` ahead of the fps filter) and it silently dropped one
    frame on ordinary-length clips — the seek eats real decode time out of
    the window the fps filter then has to fill at rate n/duration, so the
    filter runs out of clip a touch before reaching n outputs. Spanning from
    t=0 keeps every output timestamp strictly less than the full duration, so
    ``-frames:v n`` reliably gets fed enough source frames to satisfy exactly
    n outputs on any clip long enough to contain them — reliability of the
    count matters more here than excluding the very first frame.

    Never raises: an unreadable file (ffmpeg exits non-zero) or a clip with
    no frames at all yields ``[]``, same contract as before. ``_gains()``
    downstream treats an empty list as "ship the original alone".
    """
    import numpy as np

    n = max(1, n)
    if meta is None:
        meta = probe(src)
    duration = meta.duration_s or 0.0

    width: int | None
    if meta.width and meta.height:
        width = max(2, int(round(meta.width * height / meta.height)) & ~1)
        scale = f"scale={width}:{height}"
    else:
        # Unknown container dimensions (e.g. a garbage/malformed file) — fall
        # back to ffmpeg's own aspect-preserving scale and best-effort split
        # the returned bytes assuming a single frame came back.
        width = None
        scale = f"scale=-2:{height}"

    fps = (n / duration) if duration > 0 else 25.0

    argv = [
        "ffmpeg", "-nostdin", "-v", "error", "-i", str(src),
        "-vf", f"fps={fps:.6f},{scale}",
        "-frames:v", str(n),
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
    ]
    try:
        raw = _run(argv, capture=True, context=src)
    except VideoError:
        return []
    if not raw:
        return []

    if width is None:
        w = len(raw) // (height * 3)
        if w <= 0:
            return []
        return [np.frombuffer(raw, dtype=np.uint8).reshape(height, w, 3)]

    frame_bytes = height * width * 3
    count = len(raw) // frame_bytes
    if count <= 0:
        return []
    frames = np.frombuffer(
        raw, dtype=np.uint8, count=count * frame_bytes
    ).reshape(count, height, width, 3)
    return [frames[i] for i in range(count)]


def video_filter(method: str, stacked) -> str:
    """The ffmpeg filter chain baking generated method ``method`` into a clip,
    with its parameters estimated once from ``stacked`` (the sampled frames as
    one (N,1,3) uint8 array) and frozen for the whole clip. Every entry of
    VIDEO_CAPABLE must be dispatched here — that tuple is the list
    of methods with a clip-wide closed form, and this is the closed form."""
    from underwater_color.correct import channel_gains, hue_shift_params

    if method == "channel-stretch":
        return levels_filter(*channel_gains(stacked))
    if method == "hue-shift":
        return hue_shift_filter(*hue_shift_params(stacked))
    raise ValueError(f"no clip-wide filter for video method {method!r}")
