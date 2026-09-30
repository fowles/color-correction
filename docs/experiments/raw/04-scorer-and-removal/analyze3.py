import pickle, sys, json
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np
sys.path.insert(0, "/Users/mfk/dev/photogen")

rows = pickle.load((Path(__file__).with_name("features.pkl")).open("rb"))
STRATA = ["noise-risk", "dark", "baseline"]
def F(r, s, n): return r["feats"][s][n]

CANDS = {
    "uciqe-nr":        lambda r, s: F(r, s, "uciqe") - 4 * F(r, s, "speckle_a"),
    "lc":              lambda r, s: F(r, s, "l_contrast"),
    "lc-1spk":         lambda r, s: F(r, s, "l_contrast") - 1.0 * F(r, s, "speckle_a"),
    "lc-2spk":         lambda r, s: F(r, s, "l_contrast") - 2.0 * F(r, s, "speckle_a"),
    "lc-4spk":         lambda r, s: F(r, s, "l_contrast") - 4.0 * F(r, s, "speckle_a"),
    "lc-8spk":         lambda r, s: F(r, s, "l_contrast") - 8.0 * F(r, s, "speckle_a"),
    "lc+lstd":         lambda r, s: F(r, s, "l_contrast") + F(r, s, "l_std"),
}
def dp(fn): return lambda r, s: fn(r, s) + (1000 if s == "dive-plus" else 0)
for k in list(CANDS): CANDS[k + "+dp"] = dp(CANDS[k])

def per_photo(fn, r):
    sc = {s: fn(r, s) for s in r["shown"]}
    pick = max(sc, key=lambda s: (sc[s], s == "original"))
    rej = [s for s in r["shown"] if s not in r["approved"]]
    pc = sum(sc[g] > sc[b] for g in r["approved"] for b in rej)
    return int(pick in r["approved"]), pc, len(r["approved"]) * len(rej), pick

def summarize(fn, subset):
    hits = defaultdict(lambda: [0, 0]); pc = pn = 0
    for r in subset:
        h, c, n, _ = per_photo(fn, r)
        for k in ("overall", r["stratum"]): hits[k][0] += h; hits[k][1] += 1
        pc += c; pn += n
    s = "  ".join(f"{k}={hits[k][0]/hits[k][1]*100:5.1f}%" for k in ["overall"] + STRATA if k in hits)
    return s + f"  pairs={pc/pn*100:5.1f}%"

print("=== candidates (n=%d) ===" % len(rows))
for k, fn in CANDS.items():
    print(f"{k:14}", summarize(fn, rows))

# paired bootstrap of difference vs uciqe-nr
print("\n=== paired bootstrap Δ vs uciqe-nr (top-1 pts, pair-rate pts) 95% CI ===")
rng = np.random.default_rng(0)
base = [per_photo(CANDS["uciqe-nr"], r) for r in rows]
for k, fn in CANDS.items():
    if k == "uciqe-nr": continue
    mine = [per_photo(fn, r) for r in rows]
    d1 = []; d2 = []
    n = len(rows)
    for _ in range(4000):
        idx = rng.integers(0, n, n)
        d1.append(np.mean([mine[i][0] - base[i][0] for i in idx]) * 100)
        b_c = sum(base[i][1] for i in idx); b_n = sum(base[i][2] for i in idx)
        m_c = sum(mine[i][1] for i in idx)
        d2.append((m_c - b_c) / b_n * 100)
    print(f"{k:14} top1 Δ={np.mean(d1):+5.1f} [{np.percentile(d1,2.5):+5.1f},{np.percentile(d1,97.5):+5.1f}]"
          f"   pairs Δ={np.mean(d2):+5.1f} [{np.percentile(d2,2.5):+5.1f},{np.percentile(d2,97.5):+5.1f}]")

# per-labeler (raw, non-consensus records) — reload approvals directly
from photogen.variant_labels import load_approvals, APPROVALS_FILENAME
feat_by = {(r["dive"], r["stem"]): r for r in rows}
aps = load_approvals(Path("/Users/mfk/dev/photogen") / APPROVALS_FILENAME, warn=lambda s: None)
print("\n=== per labeler (raw records that have features) ===")
for lab in ("labeler-1", "labeler-2", "labeler-3"):
    sub = []
    for a in aps:
        if a.labeler != lab or not a.approved: continue
        r = feat_by.get((a.dive_slug, a.stem))
        if r is None or set(a.shown) != set(r["shown"]): continue
        sub.append(dict(r, approved=list(a.approved), shown=list(a.shown)))
    print(f"-- {lab}: {len(sub)} records")
    for k in ("uciqe-nr", "lc", "lc-2spk", "uciqe-nr+dp", "lc+dp", "lc-2spk+dp"):
        print(f"   {k:14}", summarize(CANDS[k], sub))

# what does uciqe-nr pick when dive-plus is shown & approved?
print("\n=== when dive-plus shown: what each metric picks ===")
for k in ("uciqe-nr", "lc", "lc-2spk"):
    picks = Counter(); miss = Counter()
    for r in rows:
        if "dive-plus" not in r["shown"]: continue
        h, _, _, pick = per_photo(CANDS[k], r)
        picks[pick] += 1
        if not h: miss[pick] += 1
    print(f"{k:10} picks={dict(picks)}  misses-by-pick={dict(miss)}")

# failures of lc-2spk+dp: list
print("\n=== misses for lc-2spk+dp ===")
for r in rows:
    h, _, _, pick = per_photo(CANDS["lc-2spk+dp"], r)
    if not h:
        print(f"  {r['dive']}/{r['stem']} [{r['stratum']}] picked {pick}, approved {r['approved']}")

# dive-plus rejected cases
print("\n=== dive-plus shown but NOT approved ===")
for r in rows:
    if "dive-plus" in r["shown"] and "dive-plus" not in r["approved"]:
        print(f"  {r['dive']}/{r['stem']} [{r['stratum']}] approved {r['approved']}")
