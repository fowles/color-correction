# SPDX-License-Identifier: MIT
"""The Python half of the static demo page, run inside Pyodide by worker.js.

worker.js writes the package's real ``correct.py`` into Pyodide's filesystem
as ``underwater_color/correct.py`` (beside an empty ``__init__``), so the page
runs the same algorithms and constants as the library rather than a port.
This file only converts the browser's RGBA buffers and decides the menu; it
imports cleanly under CPython too, which is how tests/test_web.py checks it.
"""
from __future__ import annotations

import numpy as np

from underwater_color.correct import DEFAULT_VARIANTS, GENERATED_METHODS

# Methods that cannot run in the browser, with the reason. Everything else in
# GENERATED_METHODS is offered automatically.
UNAVAILABLE = {"dicam": "needs torch, which has no Pyodide build"}


def menu() -> list[dict]:
    """The methods the page offers, in DEFAULT_VARIANTS precedence then
    GENERATED_METHODS order, each flagged with whether it is a default."""
    order = list(DEFAULT_VARIANTS) + [
        m for m in GENERATED_METHODS if m not in DEFAULT_VARIANTS]
    return [{"name": m, "default": m in DEFAULT_VARIANTS}
            for m in order if m not in UNAVAILABLE]


def rgb_from_rgba(rgba, width: int, height: int) -> np.ndarray:
    """A canvas's RGBA bytes as the (H, W, 3) uint8 array the methods take.
    Alpha is dropped, as open_image's convert("RGB") drops it."""
    arr = np.frombuffer(rgba, dtype=np.uint8).reshape(height, width, 4)
    return np.ascontiguousarray(arr[..., :3])


def correct(name: str, rgb: np.ndarray) -> bytes:
    """Run method ``name`` on ``rgb``; returns opaque RGBA bytes ready for
    a canvas ImageData."""
    out = GENERATED_METHODS[name](rgb)
    rgba = np.empty(out.shape[:2] + (4,), dtype=np.uint8)
    rgba[..., :3] = out
    rgba[..., 3] = 255
    return rgba.tobytes()
