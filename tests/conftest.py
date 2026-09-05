# SPDX-License-Identifier: MIT
"""Shared test fixtures. Keeps the suite hermetic: the DICAM model is stubbed
by default so tests never require the downloaded checkpoint or run real torch
inference (see underwater_color/dicam.py). Tests that exercise the real dicam
module opt out by living in test_dicam.py."""
import pytest


@pytest.fixture(autouse=True)
def _stub_dicam(request, monkeypatch):
    # test_dicam.py tests the real loader/preflight/enhance with its own fakes.
    if request.module.__name__.rsplit(".", 1)[-1] == "test_dicam":
        return
    import underwater_color.dicam as dc
    monkeypatch.setattr(dc, "preflight", lambda: None, raising=False)
    monkeypatch.setattr(dc, "enhance", lambda arr: arr, raising=False)
