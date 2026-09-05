# SPDX-License-Identifier: MIT
"""The `underwater-color` command line tool.

Run every color-correction variant over files named on the command line,
writing corrected siblings next to them — no site, no library, no config.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from underwater_color import correct

# frames sampled per clip to estimate a clip-wide filter's parameters
VIDEO_GAIN_SAMPLES = 12

# Formats whose PIL writer accepts an ``exif=`` blob. PNG carries no EXIF
# block, so a source's metadata is simply dropped there.
_EXIF_EXTS = {".jpg", ".jpeg", ".webp", ".tif", ".tiff"}

VIDEO_EXTENSIONS: set[str] = {".mp4", ".mov"}


def is_video(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTENSIONS


def run(args):
    """Run color-correction variants over files named on the command line.

    Defaults to the generators in ``correct.DEFAULT_VARIANTS``; ``--variants``
    (repeatable) names others, and ``all`` means every generator.

    Standalone by design: it reads no site.yaml and touches no photos/ tree —
    each input is decoded, corrected, and written back as
    ``<stem>.<method><ext>`` beside itself (or under --out-dir). The output
    format follows the input's extension, so a PNG in gives PNGs out.

    Video (.mp4/.mov) is corrected the way `build` does it: one clip-wide
    filter, its parameters estimated once from sampled frames and frozen for
    the whole clip. Only ``correct.VIDEO_CAPABLE`` has such a closed form, so
    the rest of the menu is skipped per video file rather than failing it —
    a mixed command line corrects each input with what applies to it.

    Files are processed on a thread pool (``--jobs``), one task per input —
    the same granularity ``build`` uses, and the one that keeps a file's
    methods sharing its single decode (or, for video, its single frame
    sampling). Each task buffers its own output and the lines are printed in
    command-line order as the results come back, so parallelism never
    interleaves two files' messages.
    """
    import numpy as np
    from PIL import Image

    from underwater_color import _pool
    from underwater_color import video as videolib
    from underwater_color._imageio import open_image
    from underwater_color.video import video_filter

    names = getattr(args, "variants", None)
    try:
        if not names:
            selected = set(m for m in correct.DEFAULT_VARIANTS
                           if m in correct.GENERATED_METHODS)
        elif correct.ALL_KEYWORD in names:
            # Only the generators: this command corrects pixels it decodes
            # itself, so the file-backed methods in ALL_VARIANTS (dive-plus,
            # google) have nothing to produce here.
            selected = set(correct.GENERATED_METHODS)
        else:
            selected = correct.resolve_methods(names)
    except ValueError as e:
        print(f"error: {e}, or '{correct.ALL_KEYWORD}'", file=sys.stderr)
        sys.exit(2)
    # Registry order, not set order, so the run is deterministic.
    methods = [m for m in correct.GENERATED_METHODS if m in selected]

    videos = [Path(f) for f in args.files if is_video(Path(f))]
    if videos and any(m in correct.VIDEO_CAPABLE for m in methods):
        # Same shape as build's: a missing ffmpeg fails the whole run up front
        # with an actionable message, not deep in per-file work.
        videolib.preflight()

    if "dicam" in selected and len(videos) < len(args.files):
        # Same shape as build's: surface a missing checkpoint before any file
        # is decoded, rather than after the cheap variants have written.
        # Videos alone can't reach dicam — it isn't VIDEO_CAPABLE.
        from underwater_color import dicam
        dicam.preflight()

    out_dir = Path(args.out_dir) if args.out_dir else None
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)

    def _one(name):
        """Correct one input. Returns (failures, stdout lines, stderr lines);
        nothing is printed from the worker thread, so two files' messages can
        never interleave."""
        out_lines: list[str] = []
        err_lines: list[str] = []
        failures = 0
        src = Path(name)
        is_vid = is_video(src)
        if is_vid:
            # A clip is always re-encoded as H.264 in an MP4 container
            # (video.transcode passes an explicit -f mp4), so a .mov in must
            # give a .mp4 out — naming the output .mov would misdescribe it.
            usable = [m for m in methods if m in correct.VIDEO_CAPABLE]
            for m in methods:
                if m not in usable:
                    out_lines.append(
                        f"{src}: skipping {m} (no clip-wide form for video)")
            suffix = ".mp4"
        else:
            usable = methods
            suffix = src.suffix
        dests = {m: (out_dir or src.parent) / f"{src.stem}.{m}{suffix}"
                 for m in usable}
        todo = [m for m in usable if args.force or not dests[m].exists()]
        for m in usable:
            if m not in todo:
                out_lines.append(
                    f"skipping {dests[m]} (exists; --force to overwrite)")
        if not todo:
            return failures, out_lines, err_lines

        if is_vid:
            frames = videolib.sample_frames(src, VIDEO_GAIN_SAMPLES)
            if not frames:
                # Unreadable or frameless: sample_frames never raises, so this
                # is the only signal. Nothing to estimate from, so nothing to
                # write — same call as build's, which ships the original alone.
                err_lines.append(
                    f"{src}: cannot sample frames (unreadable video?)")
                return failures + 1, out_lines, err_lines
            stacked = np.concatenate(
                [f.reshape(-1, 3) for f in frames]).reshape(-1, 1, 3)
            for m in todo:
                try:
                    videolib.transcode(src, dests[m],
                                       vfilter=video_filter(m, stacked))
                except Exception as e:
                    err_lines.append(
                        f"{src}: {m} failed ({type(e).__name__}: {e})")
                    failures += 1
                    continue
                out_lines.append(str(dests[m]))
            return failures, out_lines, err_lines

        try:
            with open_image(src) as img:
                exif = (img.info.get("exif")
                        if src.suffix.lower() in _EXIF_EXTS else None)
                arr = np.asarray(img.convert("RGB"))
        except Exception as e:
            err_lines.append(f"{src}: cannot open ({type(e).__name__}: {e})")
            return failures + 1, out_lines, err_lines

        for m in todo:
            try:
                out = correct.GENERATED_METHODS[m](arr)
                Image.fromarray(out).save(dests[m],
                                          **({"exif": exif} if exif else {}))
            except Exception as e:
                err_lines.append(f"{src}: {m} failed ({type(e).__name__}: {e})")
                failures += 1
                continue
            out_lines.append(str(dests[m]))
        return failures, out_lines, err_lines

    jobs = max(1, getattr(args, "jobs", None) or _pool.max_workers())
    failures = 0
    with _pool.interruptible_pool(jobs) as pool:
        # map, not submit+as_completed: results arrive in command-line order,
        # so the printed log reads the same at any --jobs.
        for n, out_lines, err_lines in pool.map(_one, args.files):
            failures += n
            for line in out_lines:
                print(line)
            for line in err_lines:
                print(line, file=sys.stderr)

    return 1 if failures else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="underwater-color",
        description="Correct the colour of underwater photos and video.",
        epilog="Run `underwater-color init` once to fetch the DICAM checkpoint.")

    p.add_argument("files", nargs="*", help="image or video files to correct")
    p.add_argument("--variants", action="append", metavar="NAME",
                   help=f"correction to run (repeatable); "
                        f"'{correct.ALL_KEYWORD}' for every generator. "
                        f"Default: {', '.join(correct.DEFAULT_VARIANTS)}")
    p.add_argument("-o", "--out-dir", metavar="DIR",
                   help="write outputs here instead of beside each input")
    p.add_argument("--force", action="store_true",
                   help="overwrite an output that already exists")
    p.add_argument("--jobs", type=int, metavar="N",
                   help="parallel files (default: CPUs - 2)")
    return p


def dicam_download() -> None:
    from underwater_color import dicam
    dicam.download_checkpoint()


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # `init` is dispatched before parsing: see the note above on why it is not
    # an argparse subparser.
    if argv[:1] == ["init"]:
        dicam_download()
        return 0
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.files:
        parser.print_help(sys.stderr)
        return 2
    return run(args)
