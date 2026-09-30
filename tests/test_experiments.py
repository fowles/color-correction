# SPDX-License-Identifier: MIT
"""docs/experiments is the record a paper would cite, so its numbers must be
reproducible from its committed data, and its data must stay pseudonymous."""
import json
import re
import subprocess
import sys
from pathlib import Path

EXPERIMENTS = Path(__file__).resolve().parents[1] / "docs" / "experiments"
DATA = EXPERIMENTS / "data" / "variant-approvals.jsonl"


def test_the_committed_results_are_what_the_analysis_prints():
    """Edit the data or the script, and results/approvals.md must be
    regenerated — a hand-edited or stale number fails here."""
    fresh = subprocess.run(
        [sys.executable, str(EXPERIMENTS / "analysis" / "approvals.py")],
        check=True, capture_output=True, text=True).stdout
    committed = (EXPERIMENTS / "results" / "approvals.md").read_text()
    assert committed == fresh, (
        "results/approvals.md is stale: run "
        "`uv run python docs/experiments/analysis/approvals.py "
        "> docs/experiments/results/approvals.md`")


def test_the_results_reproduce_the_published_round_2_numbers():
    """The 2026-08-16 menu decision quotes these; they must stay derivable."""
    text = (EXPERIMENTS / "results" / "approvals.md").read_text()
    round2 = text[text.index("## Round 2"):]
    for row in ("| `hue-shift-clarity` | 198 | 153 | 77% |",
                "| `hue-shift` | 198 | 145 | 73% |",
                "| `hue-shift-clarity` | 153/191 (80.1%) |",
                "| `dive-plus` → `hue-shift-clarity` | 155/191 (81.2%) |"):
        assert row in round2, row


def test_labelers_are_pseudonymous():
    """Labelers are other people; the public data names none of them."""
    records = [json.loads(line) for line in DATA.read_text().splitlines()]
    assert len(records) == 350  # anti-vacuity: the file is the full set
    bad = {r["labeler"] for r in records
           if not re.fullmatch(r"labeler-\d+", r["labeler"])}
    assert not bad, f"non-pseudonymous labeler ids: {sorted(bad)}"


def test_every_experiment_page_is_in_the_index():
    pages = sorted(p.name for p in EXPERIMENTS.glob("[0-9][0-9]-*.md"))
    assert len(pages) >= 5  # anti-vacuity: the glob still finds the pages
    index = (EXPERIMENTS / "README.md").read_text()
    missing = [p for p in pages if f"]({p})" not in index]
    assert not missing, f"not linked from docs/experiments/README.md: {missing}"


def test_every_relative_link_in_the_experiments_resolves():
    """The pages cite raw files and each other by relative path; a rename
    must not leave a citation pointing at nothing."""
    link = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")
    checked, broken = 0, []
    for page in EXPERIMENTS.rglob("*.md"):
        for target in link.findall(page.read_text()):
            if "://" in target:
                continue
            checked += 1
            if not (page.parent / target).exists():
                broken.append(f"{page.relative_to(EXPERIMENTS)} -> {target}")
    assert checked > 50  # anti-vacuity: the pattern still matches links
    assert not broken, broken
