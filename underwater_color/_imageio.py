# SPDX-License-Identifier: MIT
"""Image decoding.

Copied from photogen's scanner for the same reason as _pool.py.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps


def open_image(path: Path) -> Image.Image:
    """Open an image as an upright PIL Image.

    The EXIF orientation is always applied (:func:`PIL.ImageOps.exif_transpose`)
    so the returned pixels are upright — a portrait shot whose rotation lives
    in the orientation tag rather than the pixels would otherwise be corrected
    sideways relative to how every viewer displays it.
    """
    return ImageOps.exif_transpose(Image.open(path))
