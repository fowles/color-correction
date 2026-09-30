# Throwaway: how does contrast-nr treat hue-shift when Dive+ is not on the menu?
import json, sys
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np
from PIL import Image

sys.path.insert(0, "/Users/mfk/dev/photogen")
from photogen.config import load_config
from photogen.quality import select_best, HAND_CORRECTED_METHODS
from photogen.variant_labels import (APPROVALS_FILENAME, consensus_approvals, current_hash_lookup,
                                     load_approvals, partition_by_staleness, retire_methods,
                                     variant_thumb_resolver)
from photogen.variants import METHOD_LABELS

base = Path("/Users/mfk/dev/photogen")
cfg = load_config(base)
HAND = set(HAND_CORRECTED_METHODS)

def entry(dive, stem):
    p = cfg.cache_dir / dive / f"{stem}.json"
    if not p.exists(): return None
    return json.loads(p.read_text())

def pick_without(scores, drop):
    s = {k: v for k, v in scores.items() if k not in drop}
    return select_best(s) or "original", s

# ---------- A. whole library: every cached photo ----------
entries = []
for p in cfg.cache_dir.glob("*/*.json"):
    e = json.loads(p.read_text())
    vs = e.get("variant_selection")
    if not vs or "hue-shift" not in vs.get("scores", {}): continue
    entries.append((p.parent.name, p.stem, vs))
print(f"cached photos with a hue-shift score: {len(entries)}  metric={Counter(vs['metric'] for _,_,vs in entries)}")
picks_all = Counter(); picks_nodp = Counter(); rank_hs = Counter(); rmse = []
with_dp = [t for t in entries if "dive-plus" in t[2]["scores"]]
for dive, stem, vs in entries:
    sc = vs["scores"]
    picks_all[select_best(sc)] += 1
    pk, s = pick_without(sc, HAND)
    picks_nodp[pk] += 1
    order = sorted(s, key=s.get, reverse=True)
    rank_hs[order.index("hue-shift") + 1] += 1
print("shown default (actual rule):", dict(picks_all.most_common()))
print("pick with dive-plus/google removed:", dict(picks_nodp.most_common()))
print("contrast-nr rank of hue-shift among generated+original:", dict(sorted(rank_hs.items())))
# on Dive+ photos: does the scorer prefer hue-shift over dive-plus? (no rule)
n = Counter()
for dive, stem, vs in with_dp:
    sc = vs["scores"]; n["hs>dp"] += sc["hue-shift"] > sc["dive-plus"]; n["total"] += 1
    n["argmax=hs"] += max(sc, key=sc.get) == "hue-shift"; n["argmax=dp"] += max(sc, key=sc.get) == "dive-plus"
print(f"photos carrying a real Dive+: {n['total']}; scorer prefers hue-shift over dive-plus on {n['hs>dp']}; raw argmax hs={n['argmax=hs']} dp={n['argmax=dp']}")

# ---------- B. labeled photos ----------
approvals = load_approvals(base / APPROVALS_FILENAME, warn=lambda s: None)
approvals, _ = retire_methods(approvals, [s for s in {x for a in approvals for x in a.shown} if s not in METHOD_LABELS])
part = partition_by_staleness(approvals, current_hash_lookup(cfg.cache_dir))
consensus, _ = consensus_approvals(part.fresh)
print(f"\nlabels: fresh={len(part.fresh)} stale={len(part.stale)} consensus photos={len(consensus)}")
resolve = variant_thumb_resolver(cfg.output_dir, cfg.cache_dir)

def load_med(dive, stem, slug):
    p = resolve(dive, stem, slug)
    if p is None or not p.exists(): return None
    im = Image.open(p).convert("RGB"); im.thumbnail((480, 4800)); return np.asarray(im).astype(float)

def rmse_of(a, b): return float(np.sqrt(np.mean((a - b) ** 2))) if a is not None and b is not None and a.shape == b.shape else None

STRATA = ["noise-risk", "dark", "baseline"]
hits = defaultdict(lambda: [0, 0]); base_hits = defaultdict(lambda: [0, 0])
hs_pick = Counter(); dp_rows = []; hs_when_dp_appr = []; hs_when_dp_rej = []
detail = []
for ap in consensus:
    if not ap.approved: continue
    e = entry(ap.dive_slug, ap.stem)
    if not e or "hue-shift" not in e.get("variant_selection", {}).get("scores", {}): continue
    sc = e["variant_selection"]["scores"]
    shown_nd = [s for s in ap.shown if s not in HAND]
    appr_nd = [s for s in ap.approved if s in shown_nd]
    if not appr_nd: continue   # nothing left to be right about
    # baseline: contrast-nr over the shown menu minus Dive+/Google (no hue-shift)
    bpick, _ = pick_without({k: v for k, v in sc.items() if k in shown_nd}, HAND)
    for k in ("overall", ap.stratum): base_hits[k][1] += 1; base_hits[k][0] += bpick in appr_nd
    # with hue-shift on the menu, Dive+ off it
    pk, _ = pick_without({k: v for k, v in sc.items() if k in shown_nd or k == "hue-shift"}, HAND)
    hs_pick[pk == "hue-shift"] += 1
    dp_shown = "dive-plus" in ap.shown; dp_appr = "dive-plus" in ap.approved
    r = rmse_of(load_med(ap.dive_slug, ap.stem, "hue-shift"), load_med(ap.dive_slug, ap.stem, "dive-plus")) if dp_shown else None
    if dp_shown:
        (hs_when_dp_appr if dp_appr else hs_when_dp_rej).append(r)
    # proxy truth: hue-shift counts as approved iff Dive+ was approved (only defined where Dive+ was shown)
    if dp_shown:
        proxy_ok = appr_nd + (["hue-shift"] if dp_appr else [])
        for k in ("overall", ap.stratum): hits[k][1] += 1; hits[k][0] += pk in proxy_ok
    detail.append((ap.stratum, ap.dive_slug, ap.stem, dp_shown, dp_appr, pk, bpick, r))

def pct(h): return "  ".join(f"{k}={h[k][0]/h[k][1]*100:5.1f}% (n={h[k][1]})" for k in ["overall"] + STRATA if k in h)
print("\n[B1] contrast-nr top-1, Dive+/Google removed from the menu, WITHOUT hue-shift:", pct(base_hits))
print("[B2] hue-shift is the pick when Dive+ removed:", dict(hs_pick))
print("[B3] proxy top-1 (hue-shift counted approved iff Dive+ was approved), Dive+ removed, hue-shift on menu:", pct(hits))
print(f"[B4] RMSE(hue-shift medium, Dive+ medium): where Dive+ approved median={np.median([x for x in hs_when_dp_appr if x is not None]):.1f} "
      f"(n={len(hs_when_dp_appr)}); where Dive+ rejected median={np.median([x for x in hs_when_dp_rej if x is not None]) if hs_when_dp_rej else float('nan'):.1f} (n={len(hs_when_dp_rej)})")
print("\nper photo: stratum dive stem dp_shown dp_appr pick_with_hs pick_without rmse")
for row in detail:
    if row[3]: print("  ", *row)
