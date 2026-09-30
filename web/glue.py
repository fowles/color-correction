# SPDX-License-Identifier: MIT
"""The Python half of the static demo page, run inside Pyodide by worker.js.

worker.js writes the package's real ``correct.py`` into Pyodide's filesystem
as ``underwater_color/correct.py`` (beside an empty ``__init__``), so the page
runs the same algorithms and constants as the library rather than a port.
This file only converts the browser's RGBA buffers and decides the menu; it
imports cleanly under CPython too, which is how tests/test_web.py checks it.

torch has no Pyodide build, so DICAM is the exception: worker.js runs the
network (web/dicam.onnx, from export_dicam.py) under onnxruntime-web, and
this file does the resize and ratio-map transfer around it with the library's
own dicam.work_input and dicam.transfer.
"""
from __future__ import annotations

import numpy as np

from underwater_color import dicam
from underwater_color.correct import DEFAULT_VARIANTS, GENERATED_METHODS

# Methods that cannot run in the browser, with the reason. Everything else in
# GENERATED_METHODS is offered automatically.
UNAVAILABLE: dict[str, str] = {}

# Methods the worker runs as an ONNX model rather than through correct(),
# with the model's path relative to web/.
ONNX_MODELS = {"dicam": "dicam.onnx"}

# DICAM's working size on the page, in place of dicam.WORK_LONGEST (1024).
# Memory scales with pixels, and at 1024 px one intermediate alone is ~2.4 GB,
# past what onnxruntime-web's wasm32 heap can allocate (704x528 already fails).
# 512 fits at any aspect ratio. Its ratio map is coarser, so the page's dicam
# differs from the library's by ~1.4 levels mean, ~7 at the 99th percentile.
DICAM_WEB_LONGEST = 512

# Methods whose page output is not the library's, with the reason the page
# shows when "(approximate)" is hovered or clicked.
APPROXIMATE = {"dicam": "runs at lower resolution"}

# Each method's doc, docs/methods/<name>.md, as GitHub renders it.
DOCS_URL = "https://github.com/fowles/underwater-color/blob/main/docs/methods/{}.md"


def menu() -> list[dict]:
    """The methods the page offers, in DEFAULT_VARIANTS precedence then
    GENERATED_METHODS order, each with its doc link and, if the page only
    approximates it, why."""
    order = list(DEFAULT_VARIANTS) + [
        m for m in GENERATED_METHODS if m not in DEFAULT_VARIANTS]
    return [{"name": m, "docs": DOCS_URL.format(m),
             "model": ONNX_MODELS.get(m), "approximate": APPROXIMATE.get(m)}
            for m in order if m not in UNAVAILABLE]


def rgb_from_rgba(rgba, width: int, height: int) -> np.ndarray:
    """A canvas's RGBA bytes as the (H, W, 3) uint8 array the methods take.
    Alpha is dropped, as open_image's convert("RGB") drops it."""
    arr = np.frombuffer(rgba, dtype=np.uint8).reshape(height, width, 4)
    return np.ascontiguousarray(arr[..., :3])


def correct(name: str, rgb: np.ndarray) -> bytes:
    """Run method ``name`` on ``rgb``; returns opaque RGBA bytes ready for
    a canvas ImageData."""
    return _rgba(GENERATED_METHODS[name](rgb))


def dicam_input(rgb: np.ndarray) -> np.ndarray:
    """DICAM's float32 HxWx3 working image; pass it to nchw() for the model
    and back to dicam_finish()."""
    return dicam.work_input(rgb, DICAM_WEB_LONGEST)


def nchw(small: np.ndarray) -> bytes:
    """``small`` as the float32 NCHW bytes of the model's input tensor."""
    return np.ascontiguousarray(small.transpose(2, 0, 1)).tobytes()


def dicam_finish(rgb: np.ndarray, small: np.ndarray, out_nchw) -> bytes:
    """Apply the model's float32 NCHW output (for input ``small``) to
    ``rgb`` at full resolution; returns opaque RGBA bytes, as correct()."""
    h, w = small.shape[:2]
    out = np.frombuffer(out_nchw, dtype=np.float32).reshape(3, h, w)
    out = out.transpose(1, 2, 0).clip(0.0, 1.0)  # as enhance() clamps
    return _rgba(dicam.transfer(rgb, small, out))


def _rgba(rgb: np.ndarray) -> bytes:
    rgba = np.empty(rgb.shape[:2] + (4,), dtype=np.uint8)
    rgba[..., :3] = rgb
    rgba[..., 3] = 255
    return rgba.tobytes()
