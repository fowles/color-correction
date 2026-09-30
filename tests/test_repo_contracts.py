# SPDX-License-Identifier: MIT
"""Contracts about how the source is written, not what it computes.

Each of these is a rule that bit at least once and now fails loudly.
Grep-shaped tests carry an anti-vacuity guard: their failure mode is
matching nothing after a rename and reading green forever.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

try:
    # tomllib is 3.11+, but pyproject declares requires-python >= 3.10, so on a
    # 3.10 dev environment a bare import errors this whole module out. Nothing
    # skips on 3.11+; the fallback is a backport, not a drop in coverage.
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - only reachable on Python 3.10
    tomllib = pytest.importorskip(
        "tomli",
        reason="reading pyproject.toml needs tomllib (Python 3.11+) or the "
               "tomli backport; this package's floor is requires-python >=3.10",
    )

ROOT = Path(__file__).resolve().parent.parent
PACKAGE_ROOT = ROOT / "underwater_color"
PYPROJECT = ROOT / "pyproject.toml"
SPDX = "# SPDX-License-Identifier: MIT"


def _tracked_sources():
    for p in sorted(ROOT.rglob("*.py")):
        rel = p.relative_to(ROOT)
        if any(part.startswith(".") for part in rel.parts):
            continue
        # vendor/ carries upstream attribution and its own LICENSE.
        if "vendor" in rel.parts:
            continue
        yield p


def test_the_source_walk_actually_finds_the_source():
    """Anti-vacuity guard for every walk below: a rename that emptied
    _tracked_sources() would make all of them pass for the wrong reason."""
    found = {str(p.relative_to(ROOT)) for p in _tracked_sources()}
    for expected in ("underwater_color/correct.py", "underwater_color/video.py",
                     "underwater_color/cli.py", "underwater_color/_pool.py"):
        assert expected in found, f"{expected} is not being walked"


def test_every_source_file_opens_with_the_spdx_header():
    files = list(_tracked_sources())
    assert files, "anti-vacuity: found no source files to check"
    missing = [str(p.relative_to(ROOT)) for p in files
               if not p.read_text().startswith(SPDX)]
    assert not missing, f"missing SPDX header: {missing}"


def test_the_vendored_tree_keeps_its_upstream_license():
    """vendor/ is exempt from the SPDX header precisely because it carries its
    upstream's own terms; deleting them while keeping the exemption would ship
    the code with no licence at all."""
    vendor = ROOT / "underwater_color" / "vendor" / "dicam"
    assert (vendor / "LICENSE").is_file()
    assert (vendor / "NOTICE").is_file()


def _constructs_a_bare_pool(path: Path) -> bool:
    return "ThreadPoolExecutor(" in path.read_text()


def test_interruptible_pool_is_the_only_thread_pool():
    """A bare ThreadPoolExecutor does not cancel its queue on Ctrl-C, so a
    large run ignores the interrupt for minutes. _pool.py is the one place
    that constructs one."""
    offenders = []
    for p in _tracked_sources():
        rel = p.relative_to(ROOT)
        # tests/ is excluded because this very file names the symbol.
        if p.name == "_pool.py" or rel.parts[0] == "tests":
            continue
        if _constructs_a_bare_pool(p):
            offenders.append(str(rel))
    assert not offenders, (
        f"construct pools via _pool.interruptible_pool: {offenders}")


def test_the_pool_helper_really_does_construct_one():
    """Anti-vacuity guard for the test above."""
    src = (ROOT / "underwater_color" / "_pool.py").read_text()
    assert "ThreadPoolExecutor(" in src


def test_the_test_exclusion_is_doing_real_work():
    """Second anti-vacuity guard: the tests/ exclusion above is positional, so
    pin that it is excluding a file that WOULD otherwise be flagged — this one.
    A layout change that moved the suite would fail here rather than silently
    stop excluding anything."""
    me = Path(__file__).resolve()
    assert me.relative_to(ROOT).parts[0] == "tests"
    assert _constructs_a_bare_pool(me)


# --- declared dependencies ---------------------------------------------------
#
# Every third-party import under underwater_color/ must be declared in
# pyproject.toml — as a core dependency or in an optional-dependency group.
#
# This is the tripwire for a class of defect a plain test run never catches:
# `underwater-color init` imported `requests` (used only by dicam's checkpoint
# downloader) with no declaration anywhere in pyproject.toml, so the entry
# point was broken in a fresh install — but every other test still passed,
# because the dev environment happened to have requests installed already for
# unrelated reasons. Parsing pyproject.toml directly, rather than trusting
# `uv run pytest` to run in a minimal environment, is what actually catches it.

# Import name -> distribution name, where they differ.
DIST_NAME = {
    "cv2": "opencv-python",
    "PIL": "Pillow",
}

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


# --- the static web page ------------------------------------------------------
#
# web/worker.js ships only correct.py and web/glue.py into Pyodide, and loads
# only the Pyodide packages in its PACKAGES list. A module-level import in
# either file that the list does not cover (a new third-party dependency, or a
# first-party import of video.py or dicam.py) breaks the page, while every
# CPython test stays green. Imports inside functions are exempt: they run only
# when that function is called, which is how dicam_correct gets away with
# importing torch (the page never offers dicam).

WORKER_JS = ROOT / "web" / "worker.js"
BROWSER_SOURCES = (PACKAGE_ROOT / "correct.py", ROOT / "web" / "glue.py")


def _worker_packages() -> set[str]:
    m = re.search(r"^const PACKAGES = \[(.*?)\];", WORKER_JS.read_text(), re.M)
    assert m, "anti-vacuity: PACKAGES not found in web/worker.js"
    return {_normalize(p) for p in re.findall(r'"([^"]+)"', m.group(1))}


def _module_level_imports(path: Path) -> set[str]:
    """Dotted module names imported at module level only (tree.body).

    ``from underwater_color import video`` names a submodule, not an
    attribute, so it is recorded as ``underwater_color.video``; recording
    only the package would let it through as shipped."""
    modules: set[str] = set()
    for node in ast.parse(path.read_text(), filename=str(path)).body:
        if isinstance(node, ast.Import):
            modules.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            if node.module == "underwater_color":
                modules.update(f"underwater_color.{a.name}" for a in node.names)
            else:
                modules.add(node.module)
    return modules


def test_the_browser_sources_import_only_what_the_worker_provides():
    packages = _worker_packages()
    # The worker writes correct.py (and an empty __init__) and glue.py.
    shipped = {"underwater_color", "underwater_color.correct", "glue"}
    imported = set()
    for path in BROWSER_SOURCES:
        imported |= _module_level_imports(path)
    # Anti-vacuity guard: both the scan and the package list saw something.
    assert {"numpy", "cv2", "underwater_color.correct"} <= imported
    assert packages
    missing = sorted(
        m for m in imported
        if m not in shipped
        and m.split(".")[0] not in sys.stdlib_module_names
        and _normalize(DIST_NAME.get(m.split(".")[0], m.split(".")[0]))
        not in packages)
    assert not missing, (
        f"module-level import(s) in {[p.name for p in BROWSER_SOURCES]} that "
        f"web/worker.js neither ships nor lists in PACKAGES: {missing}")


def test_the_worker_ships_the_files_the_scan_checks():
    """Anti-vacuity guard for the test above: if worker.js stopped shipping
    either file under the name assumed there, the scan would be checking the
    wrong thing."""
    src = WORKER_JS.read_text()
    assert '"underwater_color/correct.py": "../underwater_color/correct.py"' in src
    assert '"glue.py": "glue.py"' in src


def test_the_worker_is_a_module_worker():
    """Pyodide 314 refuses to boot in a classic worker, and a cross-origin
    importScripts reports that only as a generic NetworkError."""
    page = (ROOT / "web" / "index.html").read_text()
    assert 'new Worker("worker.js", { type: "module" })' in page
    src = WORKER_JS.read_text()
    assert "importScripts(" not in src
    assert re.search(r'^import \{ loadPyodide \} from "https://', src, re.M)



def test_every_file_the_worker_fetches_exists_where_pages_serves_it():
    """Pages serves the repo root, so each SOURCES url, resolved against
    web/, must be a real tracked file; moving web/ or correct.py breaks the
    published page while every CPython test still passes."""
    m = re.search(r"^const SOURCES = \{(.*?)^\};", WORKER_JS.read_text(),
                  re.M | re.S)
    assert m, "anti-vacuity: SOURCES not found in web/worker.js"
    urls = re.findall(r':\s*"([^"]+)"', m.group(1))
    assert "../underwater_color/correct.py" in urls  # anti-vacuity
    missing = [u for u in urls if not (ROOT / "web" / u).is_file()]
    assert not missing, f"web/worker.js fetches missing file(s): {missing}"
