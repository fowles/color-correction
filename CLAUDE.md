# underwater-color

Underwater photo and video color correction as a library: **numpy in, numpy
out** for stills, and **one clip-wide ffmpeg filter expression** for video.
No site, no photo library, no config, no sidecars — the caller owns files and
metadata, this package owns pixels.

Extracted from [photogen](https://github.com/fowles/photogen), which consumes it
as a `uv` **editable path source** (`../color-correction`). A change here is
live in photogen immediately, with no publish step, so photogen's own suite is
a second, consumer-level check on anything landed here.

## Commands

```bash
uv sync
uv run pytest
uv run underwater-color FILE... [--variants NAME] [-o DIR] [--force] [--jobs N]
uv run underwater-color init     # download the DICAM checkpoint (only for `dicam`)
```

`ffmpeg`/`ffprobe` must be on PATH for anything touching video (`brew install
ffmpeg`). They are system binaries, not wheels — which is why there is
deliberately no `[video]` extra; a missing ffmpeg is reported at runtime by
`video.preflight()`.

## Layout

```
underwater_color/
  __init__.py   the public API: everything a caller needs is re-exported here,
                so the private module layout is free to move
  correct.py    LEAF: the algorithms and the METHOD VOCABULARY (GENERATED_METHODS,
                DEFAULT_VARIANTS, VIDEO_CAPABLE, ALL_KEYWORD, resolve_methods).
                numpy in, numpy out; no file or ffmpeg knowledge
  video.py      LEAF: the ffmpeg layer — transcode/extract_poster/sample_frames,
                plus the clip-wide closed forms (levels_filter, hue_shift_filter,
                video_filter) of the methods that have one
  dicam.py      the only torch-touching module: lazy singleton model,
                lock-serialized inference, sha256-pinned checkpoint download
  cli.py        the `underwater-color` command
  _pool.py      interruptible_pool/max_workers
  _imageio.py   open_image (always upright: exif_transpose)
  vendor/dicam/ the upstream DICAM network, with its own LICENSE and NOTICE
web/            the static demo page: index.html (UI), worker.js (boots Pyodide
                and runs correct.py off the main thread), glue.py (RGBA <->
                numpy and the menu; unit-tested under CPython in test_web.py),
                dicam.onnx (DICAM for onnxruntime-web, from export_dicam.py)
docs/methods/   one page per GENERATED_METHODS entry, citing its source
docs/experiments/  every eval behind the methods and menu: one page each,
                the pseudonymized labels (data/), the script that recomputes
                results/approvals.md from them (analysis/), and verbatim raw
                outputs and scripts recovered from the sessions (raw/). A
                new claim about how well a method does goes here, with its
                data or raw output, and the comment or doc links to it
```

## The method menu

**A fixed MENU, no scorer, no per-photo `best`** — a fixed rule out-scored
every scorer tried; do not re-add one.

`correct.GENERATED_METHODS` is the whole generated vocabulary:
`channel-stretch`, `hue-shift`, `hue-shift-clarity`, `hue-shift-clarity-near`,
`ancuti-fusion`, and `dicam`. `VIDEO_CAPABLE` is `channel-stretch` and
`hue-shift` — the two with a clip-wide closed form; everything else is
per-frame and is never offered for video. `DEFAULT_VARIANTS` is what a caller
that says nothing gets.

**List ORDER is precedence.** `DEFAULT_VARIANTS` is not a set: the first entry
a photo actually has is the one a consumer shows (photogen's `shown_method`
reads it that way). Reordering it changes which correction the world sees.

`gray-world` and `white-patch` are opt-in classical baselines, last in
`GENERATED_METHODS`. They were removed on measured evidence (approved 9% /
15% of the times shown against 141 consensus labels, the sole approved
variant on 1 / 0 photos) and restored so they can be compared, not shown.
**Never add them to `DEFAULT_VARIANTS`**;
`test_gray_world_and_white_patch_are_never_defaults` enforces it.

**Every `GENERATED_METHODS` entry has `docs/methods/<name>.md`**, citing the
primary source it comes from or saying it is original to this library. The
web page links each tile to its doc on GitHub (so it renders).
`test_every_generated_method_has_a_doc` catches a missing one, and
`test_every_method_links_to_a_committed_doc` checks the page's links.

## Algorithms

- **`hue_shift` is one GLOBAL 3×3 color matrix plus a stretch**: red is
  reconstructed as a hue-shifted mix of all three channels
  (`_hue_shift_row(h)`, the red row of the standard Rec.601-luma
  hue-rotation matrix — a rotation of the red primary about the gray axis) with G/B untouched and the angle `h` interpolated from the
  frame's mean red (~90° when red-starved, ~20° when already red), followed
  by a 0.4/99.9 per-channel percentile stretch. The angle table and
  percentiles were fitted to 100 hand-corrected pairs (plus 60 held out). Red is *synthesised*
  from green/blue rather than gained, which is why it needs no gain ceiling
  and is markedly less noisy than `channel_stretch` on red-starved frames.
- **`channel_stretch` caps per-channel gain at `MAX_CHANNEL_GAIN` 6.0**: a
  channel spanning only a handful of the 256 levels carries no recoverable
  signal — the span *is* the noise floor — so stretching it to full range
  amplifies ±1 LSB into gross color speckle rather than restoring detail.
- **`_mix_red` clips before the stretch**, exactly as ffmpeg's
  `colorchannelmixer` clips before `colorlevels`, so the photo and video paths
  agree on the same pixels.
- **Video bakes ONE frozen filter per clip**, its parameters estimated from 12
  sampled frames and then held for the clip's whole length. Per-frame
  estimation breathes — the color visibly pulses shot to shot.
- **`dicam.preflight()` fires only when `dicam` is in play**, and torch is
  imported lazily inside the functions that need it, so the `[dicam]` extra
  stays optional and a plain `import underwater_color` never pays torch's
  import cost (`tests/test_package.py` pins that in a subprocess).

## Gotchas

- **Every gotcha in this file ships with a test that fails when it is
  violated** — carried over from photogen, because it is the rule that kept
  the gotchas true. A gotcha about what the code COMPUTES gets an ordinary
  test; one about how the source is WRITTEN goes in
  `tests/test_repo_contracts.py`. A grep-shaped tripwire needs an
  **anti-vacuity guard** — assert it still matches a known-good file —
  because its failure mode is matching nothing after a rename and reading
  green forever.
- MIT; every tracked source file opens with `# SPDX-License-Identifier: MIT`.
  `underwater_color/vendor/` is exempt: it carries upstream attribution and
  its own `LICENSE`/`NOTICE`, and `test_the_vendored_tree_keeps_its_upstream_license`
  is what keeps those files present.
- **`_pool.interruptible_pool` is the only thread pool.** A bare
  `ThreadPoolExecutor` does not cancel its queue on Ctrl-C, so a large run
  ignores the interrupt for minutes.
- **Every third-party import must be declared in `pyproject.toml`.** A test
  run inside an already-populated venv cannot see a missing declaration —
  `requests` was imported by `dicam.py` and declared nowhere, so
  `underwater-color init` was broken in a fresh install while the suite read
  green. `test_every_third_party_import_is_declared_in_pyproject` parses
  `pyproject.toml` and the import graph directly, which is what catches it.
- **`init` is dispatched from argv before parsing**, not as an argparse
  subparser: argparse cannot combine a subparser group with a `files`
  positional taking `nargs="*"`.
- The CLI corrects only what it decodes itself, so `--variants all` means
  every entry of `GENERATED_METHODS` — a consumer's file-backed corrections
  (photogen's `dive-plus`, `google`) are not this package's vocabulary.
- **`docs/experiments/results/approvals.md` is generated** by
  `docs/experiments/analysis/approvals.py` from `data/variant-approvals.jsonl`;
  after changing either, regenerate it, or
  `test_the_committed_results_are_what_the_analysis_prints` fails. The data is
  pseudonymized (`labeler-N`); `test_labelers_are_pseudonymous` keeps real
  names out. `raw/` is a verbatim record: never edit a file there, even to add
  the SPDX header (it is exempt for that reason).
- The suite is hermetic: `tests/conftest.py` stubs the DICAM model by default,
  so no test needs the downloaded checkpoint or runs real inference.
  `test_dicam.py` opts out and drives the real loader with its own fakes.
- **The web page runs the real `correct.py` in Pyodide**, not a port, so
  `correct.py`, `dicam.py` and `web/glue.py` may import at module level only
  numpy, cv2, the stdlib and `underwater_color.correct`/`.dicam`. Anything
  else must either be imported lazily inside the function that needs it (as
  `dicam.enhance` imports torch) or be added to `PACKAGES` in
  `web/worker.js`, and it must exist in Pyodide.
  `test_the_browser_sources_import_only_what_the_worker_provides` enforces
  this. The page offers every `GENERATED_METHODS` entry except the ones in
  `glue.UNAVAILABLE` (currently none), so a new method appears on the page
  automatically.
- **The page runs DICAM's network as `web/dicam.onnx` under onnxruntime-web**,
  with `glue.py` running the library's own `dicam.work_input`/`transfer`
  around it. It uses **512 px** (`glue.DICAM_WEB_LONGEST`), not 1024: memory
  grows with pixel count, and wasm32 hits `bad_alloc` at 704×528. The ONNX file
  is committed and records the checkpoint sha256 it was exported from.
  Changing the checkpoint means re-running `web/export_dicam.py`, and
  `test_the_committed_model_was_exported_from_the_pinned_checkpoint` fails
  until you do.
- **GitHub Pages serves the repo root from `main`** (branch mode, no
  workflow), so the page is at `/web/` there exactly as when serving the repo
  root locally, and the worker's `../underwater_color/correct.py` resolves in
  both. Moving `web/` or `correct.py` breaks the published page;
  `test_every_file_the_worker_fetches_exists_where_pages_serves_it` catches it.
- `web/worker.js` must stay a **module** worker: Pyodide 314 refuses to boot
  in a classic one ("Classic web workers are not supported"). Cross-origin
  `importScripts` hides that error behind a generic NetworkError.
- `video.probe` reads only duration and dimensions, via `ffprobe`. Container
  introspection proper — camera identity, orientation, the byte-level
  mvhd/tkhd/EXIF parsing — stays in the caller; this package never touches it.

## Dependencies

`uv` + `pyproject.toml`/`uv.lock`. numpy, Pillow, opencv-python (Ancuti and
DICAM pre/post). `torch` and `requests` are the `[dicam]` extra: torch runs
the one learned method, requests downloads its checkpoint. External binaries:
`ffmpeg`/`ffprobe`.
