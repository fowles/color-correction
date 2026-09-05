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
