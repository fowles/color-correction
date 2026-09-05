# SPDX-License-Identifier: MIT
"""Every third-party import under underwater_color/ must be declared in
pyproject.toml — as a core dependency or in an optional-dependency group.

This is the tripwire for a class of defect a plain test run never catches:
`underwater-color init` imported `requests` (used only by dicam's checkpoint
downloader) with no declaration anywhere in pyproject.toml, so the entry
point was broken in a fresh install — but every test here still passed,
because the dev environment happened to have requests installed already for
unrelated reasons. Parsing pyproject.toml directly, rather than trusting
`uv run pytest` to run in a minimal environment, is what actually catches it.
"""
from __future__ import annotations

import ast
import re
import sys
import tomllib
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent / "underwater_color"
PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"

# Import name -> distribution name, where they differ.
DIST_NAME = {
    "cv2": "opencv-python",
    "PIL": "Pillow",
}

# Distribution name -> the stdlib-ish/local names its own declared spelling
# would never appear as (kept trivial; see NORMALIZE below for the real work).
NORMALIZE = re.compile(r"[-_.]+")


def _normalize(name: str) -> str:
    """Fold a distribution requirement spec down to a bare, comparable name.

    "opencv-python>=4.6" -> "opencvpython"; "Pillow" -> "pillow". Case and
    separators (-, _, .) are exactly what PyPI treats as equivalent, so this
    is not loosening the check, just matching PEP 503 normalization loosely
    enough for a static list.
    """
    bare = re.split(r"[<>=!~\[; ]", name, maxsplit=1)[0]
    return NORMALIZE.sub("", bare).lower()


def _declared_distributions() -> set[str]:
    data = tomllib.loads(PYPROJECT.read_text())
    project = data["project"]
    declared = set(project.get("dependencies", []))
    for group in project.get("optional-dependencies", {}).values():
        declared.update(group)
    for group in data.get("dependency-groups", {}).values():
        declared.update(g for g in group if isinstance(g, str))
    return {_normalize(d) for d in declared}


def _imported_top_level_modules() -> set[str]:
    """Every top-level module named in an `import X` / `from X import ...`
    anywhere under underwater_color/, excluding vendor/ (vendored code is not
    this package's own dependency surface)."""
    modules: set[str] = set()
    for path in PACKAGE_ROOT.rglob("*.py"):
        if "vendor" in path.relative_to(PACKAGE_ROOT).parts:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    modules.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.level:  # a relative "from . import x" names no module
                    continue
                if node.module:
                    modules.add(node.module.split(".")[0])
    return modules


def _third_party_modules() -> set[str]:
    imported = _imported_top_level_modules()
    imported -= {"underwater_color"}  # first-party
    imported -= sys.stdlib_module_names  # stdlib, incl. __future__
    return imported


def test_every_third_party_import_is_declared_in_pyproject():
    imported = _third_party_modules()

    # Anti-vacuity guard: a scanner that silently finds nothing would make
    # every assertion below pass for the wrong reason.
    assert "numpy" in imported
    assert "cv2" in imported

    declared = _declared_distributions()
    missing = []
    for module in sorted(imported):
        dist = DIST_NAME.get(module, module)
        if _normalize(dist) not in declared:
            missing.append(module)

    assert not missing, (
        f"module(s) imported under underwater_color/ but not declared in "
        f"pyproject.toml (as a dependency or an optional-dependency group): "
        f"{missing}")
