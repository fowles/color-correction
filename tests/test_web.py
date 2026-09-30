# SPDX-License-Identifier: MIT
"""web/glue.py, the Python half of the static page, run under CPython against
the real correct module (Pyodide runs the same file)."""
import importlib.util
from pathlib import Path

import numpy as np
import pytest

from underwater_color.correct import DEFAULT_VARIANTS, GENERATED_METHODS

GLUE = Path(__file__).resolve().parent.parent / "web" / "glue.py"


@pytest.fixture(scope="module")
def glue():
    spec = importlib.util.spec_from_file_location("glue", GLUE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_page_offers_every_method_but_dicam(glue):
    """A new method shows up on the page automatically. If one also has to
    be left out, UNAVAILABLE and this test should both say so."""
    names = [m["name"] for m in glue.menu()]
    assert set(GENERATED_METHODS) - set(names) == {"dicam"}
    assert len(names) == len(set(names))


def test_the_menu_leads_with_the_defaults_in_precedence_order(glue):
    menu = glue.menu()
    lead = [m["name"] for m in menu[:len(DEFAULT_VARIANTS)]]
    assert lead == list(DEFAULT_VARIANTS)
    assert [m["default"] for m in menu] == (
        [True] * len(DEFAULT_VARIANTS)
        + [False] * (len(menu) - len(DEFAULT_VARIANTS)))


def test_correct_round_trips_canvas_rgba(glue):
    h, w = 24, 40
    rng = np.random.default_rng(0)
    rgba = rng.integers(0, 256, size=(h, w, 4), dtype=np.uint8)
    rgb = glue.rgb_from_rgba(memoryview(rgba.tobytes()), w, h)
    assert np.array_equal(rgb, rgba[..., :3])
    out = np.frombuffer(glue.correct("hue-shift", rgb), np.uint8).reshape(h, w, 4)
    assert np.array_equal(out[..., :3], GENERATED_METHODS["hue-shift"](rgba[..., :3]))
    assert (out[..., 3] == 255).all()
