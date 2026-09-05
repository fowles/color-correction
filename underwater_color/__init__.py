# SPDX-License-Identifier: MIT
"""Underwater photo and video color correction.

Closed-form and learned corrections for underwater imagery: numpy in, numpy
out for stills, and a clip-wide ffmpeg filter expression for video. See
README.md for the method menu and how it was chosen.
"""
__version__ = "0.1.0"

from underwater_color.correct import (  # noqa: E402,F401
    ALL_KEYWORD,
    DEFAULT_VARIANTS,
    GENERATED_METHODS,
    VIDEO_CAPABLE,
    ancuti_fusion,
    channel_gains,
    channel_stretch,
    dicam_correct,
    hue_shift,
    hue_shift_clarity,
    hue_shift_clarity_near,
    hue_shift_params,
    resolve_methods,
)
