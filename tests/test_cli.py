# SPDX-License-Identifier: MIT
"""The `underwater-color` command: run every color-correction variant over
files named on the command line, writing siblings next to them."""

import argparse
import threading

import numpy as np
import pytest
from PIL import Image

from underwater_color import video
from underwater_color.cli import run
from underwater_color.correct import DEFAULT_VARIANTS, GENERATED_METHODS, VIDEO_CAPABLE

# dicam needs a downloaded checkpoint; every test here names its methods so the
# suite never depends on one being present.
CHEAP = ["channel-stretch", "hue-shift"]


def _args(files, *, variants=None, out_dir=None, force=False, jobs=None):
    return argparse.Namespace(
        files=[str(f) for f in files],
        variants=variants,
        out_dir=None if out_dir is None else str(out_dir),
        force=force,
        jobs=jobs,
    )


def _write_image(path, *, exif=None, mode="RGB"):
    rng = np.random.default_rng(0)
    arr = rng.integers(0, 256, size=(16, 16, 3), dtype=np.uint8)
    arr[..., 0] //= 4  # red-starved, like a real underwater frame
    img = Image.fromarray(arr).convert(mode)
    img.save(path, **({"exif": exif} if exif else {}))
    return path


def test_writes_one_sibling_per_method_matching_the_input_extension(tmp_path):
    src = _write_image(tmp_path / "foo.png")

    assert run(_args([src], variants=CHEAP)) == 0

    for method in CHEAP:
        out = tmp_path / f"foo.{method}.png"
        assert out.exists(), method
        with Image.open(out) as im:
            assert im.format == "PNG"
            assert im.size == (16, 16)


def test_defaults_to_the_generated_default_variant_menu(tmp_path, monkeypatch):
    # Stub dicam so the run never depends on a downloaded checkpoint, even
    # though it should not be reached: dicam isn't in DEFAULT_VARIANTS.
    monkeypatch.setitem(GENERATED_METHODS, "dicam", lambda arr: arr)
    src = _write_image(tmp_path / "bar.jpg")

    assert run(_args([src])) == 0

    expected = [m for m in DEFAULT_VARIANTS if m in GENERATED_METHODS]
    for method in expected:
        assert (tmp_path / f"bar.{method}.jpg").exists(), method
    for method in GENERATED_METHODS:
        if method not in expected:
            assert not (tmp_path / f"bar.{method}.jpg").exists(), method


def test_all_runs_every_generator(tmp_path, monkeypatch):
    """`--variants all` means every generator — and only the generators: the
    file-backed methods (dive-plus, google) have no pixels to compute here."""
    # Stub dicam's generator AND its preflight: 'all' does reach it.
    monkeypatch.setitem(GENERATED_METHODS, "dicam", lambda arr: arr)
    from underwater_color import dicam
    monkeypatch.setattr(dicam, "preflight", lambda: None)
    src = _write_image(tmp_path / "bar.jpg")

    assert run(_args([src], variants=["all"])) == 0

    for method in GENERATED_METHODS:
        assert (tmp_path / f"bar.{method}.jpg").exists(), method
    for method in ("dive-plus", "google"):
        assert not (tmp_path / f"bar.{method}.jpg").exists(), method


def test_variants_flag_is_repeatable_via_the_parser():
    from underwater_color import cli

    args = cli.build_parser().parse_args(
        ["a.jpg", "--variants", "hue-shift", "--variants", "all"])
    assert args.variants == ["hue-shift", "all"]


def test_each_input_gets_its_own_outputs(tmp_path):
    a = _write_image(tmp_path / "foo.png")
    b = _write_image(tmp_path / "bar.jpg")

    assert run(_args([a, b], variants=["hue-shift"])) == 0

    assert (tmp_path / "foo.hue-shift.png").exists()
    assert (tmp_path / "bar.hue-shift.jpg").exists()


def test_carries_exif_into_formats_that_support_it(tmp_path):
    exif = Image.Exif()
    exif[0x010F] = "Canon"  # Make
    src = _write_image(tmp_path / "foo.jpg", exif=exif.tobytes())

    assert run(_args([src], variants=["hue-shift"])) == 0

    with Image.open(tmp_path / "foo.hue-shift.jpg") as im:
        assert im.getexif().get(0x010F) == "Canon"


def test_existing_output_is_skipped_with_a_notice(tmp_path, capsys):
    src = _write_image(tmp_path / "foo.png")
    dest = tmp_path / "foo.hue-shift.png"
    dest.write_bytes(b"not an image")

    assert run(_args([src], variants=["hue-shift"])) == 0

    assert dest.read_bytes() == b"not an image"
    assert "skip" in capsys.readouterr().out.lower()


def test_force_overwrites_an_existing_output(tmp_path):
    src = _write_image(tmp_path / "foo.png")
    dest = tmp_path / "foo.hue-shift.png"
    dest.write_bytes(b"not an image")

    assert run(_args([src], variants=["hue-shift"], force=True)) == 0

    with Image.open(dest) as im:
        assert im.size == (16, 16)


def test_out_dir_redirects_outputs_and_is_created(tmp_path):
    src = _write_image(tmp_path / "foo.png")
    out = tmp_path / "nested" / "out"

    assert run(_args([src], variants=["hue-shift"], out_dir=out)) == 0

    assert (out / "foo.hue-shift.png").exists()
    assert not (tmp_path / "foo.hue-shift.png").exists()


def test_unreadable_file_is_reported_and_the_run_continues(tmp_path, capsys):
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"not an image")
    good = _write_image(tmp_path / "foo.png")

    assert run(_args([bad, good], variants=["hue-shift"])) == 1

    assert (tmp_path / "foo.hue-shift.png").exists()
    assert "bad.jpg" in capsys.readouterr().err


def test_unknown_method_fails_before_any_work(tmp_path):
    src = _write_image(tmp_path / "foo.png")

    with pytest.raises(SystemExit) as excinfo:
        run(_args([src], variants=["nope"]))

    assert excinfo.value.code == 2
    assert not list(tmp_path.glob("foo.*.png"))


# --- video -----------------------------------------------------------------

requires_ffmpeg = pytest.mark.skipif(
    not video.have_ffmpeg(), reason="ffmpeg not installed")


def _write_clip(path):
    """A one-second, red-starved clip — an underwater frame's colour shape."""
    video._run([
        "ffmpeg", "-nostdin", "-y", "-f", "lavfi",
        "-i", "color=c=0x102040:size=64x48:rate=10:duration=1",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "0", str(path),
    ])
    return path


@requires_ffmpeg
def test_video_gets_one_corrected_clip_per_video_capable_variant(tmp_path):
    src = _write_clip(tmp_path / "dive.mp4")

    assert run(_args([src], variants=list(VIDEO_CAPABLE))) == 0

    for method in VIDEO_CAPABLE:
        out = tmp_path / f"dive.{method}.mp4"
        assert out.exists(), method
        # A real clip, not a copy of the source: the filter changed the pixels.
        assert out.read_bytes() != src.read_bytes()
        assert video.probe(out).duration_s == pytest.approx(1.0, abs=0.3)


@requires_ffmpeg
def test_video_skips_variants_with_no_clip_wide_form(tmp_path, capsys):
    """hue-shift-clarity is a per-frame spatial filter with no closed form, so
    a video is corrected with what applies and the rest is skipped — not a
    failure, and not a reason to skip the whole file."""
    src = _write_clip(tmp_path / "dive.mp4")

    assert run(
        _args([src], variants=["hue-shift", "hue-shift-clarity"])) == 0

    assert (tmp_path / "dive.hue-shift.mp4").exists()
    assert not (tmp_path / "dive.hue-shift-clarity.mp4").exists()
    assert "hue-shift-clarity" in capsys.readouterr().out


@requires_ffmpeg
def test_a_mov_comes_out_as_mp4(tmp_path):
    """transcode always writes an H.264 MP4, so naming the output .mov would
    describe the container wrongly."""
    src = _write_clip(tmp_path / "dive.mov")

    assert run(_args([src], variants=["hue-shift"])) == 0

    assert (tmp_path / "dive.hue-shift.mp4").exists()
    assert not (tmp_path / "dive.hue-shift.mov").exists()


@requires_ffmpeg
def test_mixed_command_line_corrects_each_input_with_what_applies(tmp_path):
    clip = _write_clip(tmp_path / "dive.mp4")
    photo = _write_image(tmp_path / "foo.png")

    assert run(
        _args([clip, photo], variants=["hue-shift", "hue-shift-clarity"])) == 0

    assert (tmp_path / "dive.hue-shift.mp4").exists()
    assert not (tmp_path / "dive.hue-shift-clarity.mp4").exists()
    assert (tmp_path / "foo.hue-shift.png").exists()
    assert (tmp_path / "foo.hue-shift-clarity.png").exists()


def test_unreadable_video_is_reported_and_the_run_continues(tmp_path, capsys,
                                                            monkeypatch):
    monkeypatch.setattr(video, "preflight", lambda: None)
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"not a video")  # sample_frames returns [], never raises
    good = _write_image(tmp_path / "foo.png")

    assert run(_args([bad, good], variants=["hue-shift"])) == 1

    assert not list(tmp_path.glob("bad.*.mp4"))
    assert (tmp_path / "foo.hue-shift.png").exists()
    assert "bad.mp4" in capsys.readouterr().err


def test_video_only_run_skips_the_dicam_preflight(tmp_path, monkeypatch):
    """dicam isn't VIDEO_CAPABLE, so a run over videos alone can never reach
    it — demanding its checkpoint would fail a run that doesn't need one."""
    from underwater_color import dicam

    monkeypatch.setattr(video, "preflight", lambda: None)
    monkeypatch.setattr(video, "sample_frames", lambda *a, **k: [])
    called = []
    monkeypatch.setattr(dicam, "preflight", lambda: called.append(True))
    src = tmp_path / "dive.mp4"
    src.write_bytes(b"not a video")

    run(_args([src], variants=["all"]))

    assert not called


# --- parallelism -----------------------------------------------------------


def test_files_are_corrected_in_parallel(tmp_path, monkeypatch):
    """A real concurrency assertion, not a call count: three files must be in
    the generator at the same moment or the barrier times out."""
    barrier = threading.Barrier(3, timeout=10)

    def _blocking(arr):
        barrier.wait()  # BrokenBarrierError on timeout -> the method "fails"
        return arr

    monkeypatch.setitem(GENERATED_METHODS, "hue-shift", _blocking)
    srcs = [_write_image(tmp_path / f"f{i}.png") for i in range(3)]

    assert run(_args(srcs, variants=["hue-shift"], jobs=3)) == 0

    for i in range(3):
        assert (tmp_path / f"f{i}.hue-shift.png").exists()


def test_output_stays_in_command_line_order_whatever_the_jobs(tmp_path, capsys):
    """Workers buffer their own lines and the parent prints them in input
    order, so a parallel run's log reads exactly like a serial one's."""
    srcs = [_write_image(tmp_path / f"f{i}.png") for i in range(6)]

    assert run(_args(srcs, variants=["hue-shift"], jobs=4)) == 0
    parallel = capsys.readouterr().out

    for src in srcs:
        (tmp_path / f"{src.stem}.hue-shift.png").unlink()
    assert run(_args(srcs, variants=["hue-shift"], jobs=1)) == 0

    assert capsys.readouterr().out == parallel
    assert [line.split("/")[-1] for line in parallel.splitlines()] == [
        f"f{i}.hue-shift.png" for i in range(6)]


def test_jobs_flag_is_parsed():
    from underwater_color import cli

    args = cli.build_parser().parse_args(["a.jpg", "--jobs", "3"])
    assert args.jobs == 3
    assert cli.build_parser().parse_args(["a.jpg"]).jobs is None


# --- parser surface ---------------------------------------------------------


def test_no_files_prints_help_and_exits_nonzero():
    from underwater_color import cli

    assert cli.main([]) == 2


def test_init_downloads_the_checkpoint(monkeypatch):
    """`init` is the one subcommand; it must reach dicam's downloader and
    nothing else."""
    from underwater_color import cli, dicam

    called = []
    monkeypatch.setattr(dicam, "download_checkpoint",
                        lambda: called.append(True))
    assert cli.main(["init"]) == 0
    assert called == [True]


def test_variants_is_repeatable():
    from underwater_color import cli

    args = cli.build_parser().parse_args(
        ["--variants", "hue-shift", "--variants", "dicam", "a.jpg"])
    assert args.variants == ["hue-shift", "dicam"]
    assert args.files == ["a.jpg"]
