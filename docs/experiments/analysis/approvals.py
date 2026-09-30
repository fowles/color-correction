# SPDX-License-Identifier: MIT
"""Recompute every table in docs/experiments/results/approvals.md from the raw
approval-vote labels in docs/experiments/data/variant-approvals.jsonl.

    uv run python docs/experiments/analysis/approvals.py > docs/experiments/results/approvals.md

Standard library only, deterministic, no network: the committed results file
must equal this script's output byte for byte (tests/test_experiments.py).
"""
from __future__ import annotations

import json
import math
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data" / "variant-approvals.jsonl"

# The two labeling rounds, split by timestamp. Round 1 opened each photo with
# the incumbent scorer's pick pre-approved (see 02-labeling-protocol.md);
# round 2 opened every tile unapproved.
ROUND_2_START = "2026-08-16T22:00:00Z"
ROUNDS = {
    "round 1 (2026-08-12 to 2026-08-16, pre-filled)":
        lambda r: r["ts"] < ROUND_2_START,
    "round 2 (2026-08-16/17, not pre-filled)":
        lambda r: r["ts"] >= ROUND_2_START,
}
STRATA = ("baseline", "dark", "noise-risk")
Z95 = 1.959963984540054


def load() -> list[dict]:
    with DATA.open() as f:
        return [json.loads(line) for line in f]


def wilson(k: int, n: int) -> tuple[float, float]:
    """Wilson score 95% interval for k successes in n trials, as fractions."""
    if n == 0:
        return (math.nan, math.nan)
    p = k / n
    denom = 1 + Z95 ** 2 / n
    centre = (p + Z95 ** 2 / (2 * n)) / denom
    half = Z95 * math.sqrt(p * (1 - p) / n + Z95 ** 2 / (4 * n * n)) / denom
    return (centre - half, centre + half)


def pct(k: int, n: int) -> str:
    return "—" if n == 0 else f"{100 * k / n:.0f}%"


def methods_in(records: list[dict]) -> list[str]:
    """Methods ever shown, most-approved first (ties by name), `original` last."""
    shown = Counter(m for r in records for m in r["shown"])
    approved = Counter(m for r in records for m in r["approved"])
    order = sorted(shown, key=lambda m: (m == "original", -approved[m] / shown[m], m))
    return order


def approval_table(records: list[dict]) -> list[str]:
    shown = Counter(m for r in records for m in r["shown"])
    approved = Counter(m for r in records for m in r["approved"])
    favs = Counter(r["favorite"] for r in records if r["favorite"])
    sole = Counter(r["approved"][0] for r in records if len(r["approved"]) == 1)
    out = ["| method | shown | approved | rate | 95% CI (Wilson) | favorite | sole approved |",
           "| --- | ---: | ---: | ---: | --- | ---: | ---: |"]
    for m in methods_in(records):
        lo, hi = wilson(approved[m], shown[m])
        out.append(f"| `{m}` | {shown[m]} | {approved[m]} | {pct(approved[m], shown[m])} "
                   f"| {100 * lo:.0f}–{100 * hi:.0f}% | {favs[m]} | {sole[m]} |")
    return out


def stratum_table(records: list[dict]) -> list[str]:
    counts = Counter(r["stratum"] for r in records)
    out = ["| method | " + " | ".join(f"{s} (n={counts[s]})" for s in STRATA) + " |",
           "| --- |" + " ---: |" * len(STRATA)]
    for m in methods_in(records):
        cells = []
        for s in STRATA:
            rs = [r for r in records if r["stratum"] == s and m in r["shown"]]
            k = sum(m in r["approved"] for r in rs)
            cells.append(f"{k}/{len(rs)} ({pct(k, len(rs))})" if rs else "—")
        out.append(f"| `{m}` | " + " | ".join(cells) + " |")
    return out


def head_to_head(records: list[dict]) -> list[str]:
    """For each pair shown together: photos where only A was approved, only B,
    both, and neither."""
    out = ["| A | B | only A | only B | both | neither |",
           "| --- | --- | ---: | ---: | ---: | ---: |"]
    for a, b in combinations(methods_in(records), 2):
        rs = [r for r in records if a in r["shown"] and b in r["shown"]]
        if not rs:
            continue
        ina = [a in r["approved"] for r in rs]
        inb = [b in r["approved"] for r in rs]
        only_a = sum(x and not y for x, y in zip(ina, inb))
        only_b = sum(y and not x for x, y in zip(ina, inb))
        both = sum(x and y for x, y in zip(ina, inb))
        out.append(f"| `{a}` | `{b}` | {only_a} | {only_b} | {both} "
                   f"| {len(rs) - only_a - only_b - both} |")
    return out


def fixed_rules(records: list[dict]) -> list[str]:
    """Top-1 of fixed rules: the share of photos with at least one approved
    tile where the rule's pick was approved. A rule's pick is the first entry
    of its list that the photo was shown."""
    rated = [r for r in records if r["approved"]]
    # "Always X" only for methods every photo was shown; a file-backed
    # correction (dive-plus) exists for some photos, so it only leads a rule.
    everywhere = [m for m in methods_in(records) if m != "original"
                  and all(m in r["shown"] for r in records)]
    rules = [(m,) for m in everywhere]
    if any("dive-plus" in r["shown"] for r in records):
        rules += [("dive-plus", m) for m in everywhere]
    out = [f"Photos with at least one approved tile: {len(rated)} of {len(records)}.",
           "",
           "| rule (first shown entry wins) | top-1 | 95% CI (Wilson) |",
           "| --- | ---: | --- |"]
    for rule in rules:
        hits = 0
        for r in rated:
            hits += next(m for m in rule if m in r["shown"]) in r["approved"]
        lo, hi = wilson(hits, len(rated))
        name = " → ".join(f"`{m}`" for m in rule)
        out.append(f"| {name} | {hits}/{len(rated)} ({100 * hits / len(rated):.1f}%) "
                   f"| {100 * lo:.1f}–{100 * hi:.1f}% |")
    return out


def overview(records: list[dict]) -> list[str]:
    per_labeler = Counter(r["labeler"] for r in records)
    photos = {(r["dive_slug"], r["stem"]) for r in records}
    strata = Counter(r["stratum"] for r in records)
    return [
        f"- records: {len(records)}; distinct photos: {len(photos)}; "
        f"dives: {len({r['dive_slug'] for r in records})}",
        f"- first / last timestamp: {min(r['ts'] for r in records)} / "
        f"{max(r['ts'] for r in records)}",
        "- records per labeler: " + ", ".join(
            f"{k} {v}" for k, v in sorted(per_labeler.items())),
        "- strata: " + ", ".join(f"{s} {strata[s]}" for s in STRATA),
        f"- all tiles rejected: {sum(not r['approved'] for r in records)}; "
        f"cull votes: {sum(bool(r.get('cull')) for r in records)}; "
        f"favorite set: {sum(bool(r['favorite']) for r in records)}",
        "- scorer whose pick was pre-approved (round 1) or recorded (round 2): "
        + ", ".join(f"{k} {v}" for k, v in sorted(
            Counter(r["context"]["metric"] for r in records).items())),
    ]


def main() -> None:
    records = load()
    photos = Counter((r["dive_slug"], r["stem"]) for r in records)
    lines = [
        "<!-- Generated by docs/experiments/analysis/approvals.py; do not edit. -->",
        "# Approval-vote results",
        "",
        "Every number below is recomputed from",
        "[`data/variant-approvals.jsonl`](../data/variant-approvals.jsonl) by",
        "[`analysis/approvals.py`](../analysis/approvals.py). Rates are",
        "approved / shown; intervals are Wilson 95%. Each photo was labeled by",
        f"exactly one labeler (most labels on one photo: {max(photos.values())}),",
        "so no row here is a consensus of several people.",
        "",
        "## All records",
        "",
        *overview(records),
    ]
    for title, keep in ROUNDS.items():
        rs = [r for r in records if keep(r)]
        lines += ["", f"## {title[0].upper()}{title[1:]}", "", *overview(rs),
                  "", "### Approval by method", "", *approval_table(rs),
                  "", "### Approval by stratum", "", *stratum_table(rs),
                  "", "### Head to head", "", *head_to_head(rs),
                  "", "### Fixed rules", "", *fixed_rules(rs)]
    sys.stdout.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
