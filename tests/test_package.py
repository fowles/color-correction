# SPDX-License-Identifier: MIT
"""The package imports and declares a version. Cheap, but it is the tripwire
for a broken pyproject: a packaging mistake otherwise surfaces as a confusing
ImportError deep inside a real test."""


def test_package_imports_and_has_a_version():
    import underwater_color

    assert isinstance(underwater_color.__version__, str)
    assert underwater_color.__version__


def test_importing_the_package_does_not_import_torch():
    """torch is the [dicam] extra and costs seconds to import. Nothing on the
    plain `import underwater_color` path may pull it in — dicam loads it
    lazily, inside the functions that need it."""
    import subprocess
    import sys

    out = subprocess.run(
        [sys.executable, "-c",
         "import underwater_color, sys; print('torch' in sys.modules)"],
        capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"


def test_the_public_api_is_reachable_from_the_package_root():
    """Callers import from the package, not its private module layout. A name
    that only exists on underwater_color.correct is not public API."""
    import underwater_color as uc

    for name in ("channel_stretch", "hue_shift", "hue_shift_clarity",
                 "hue_shift_clarity_near", "ancuti_fusion", "dicam_correct",
                 "channel_gains", "hue_shift_params", "resolve_methods",
                 "GENERATED_METHODS", "DEFAULT_VARIANTS", "VIDEO_CAPABLE",
                 "ALL_KEYWORD"):
        assert hasattr(uc, name), f"{name} is not re-exported"
