import pickle, sys, itertools
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np

rows = pickle.load((Path(__file__).with_name("features.pkl")).open("rb"))
FEATS = sorted(rows[0]["feats"]["original"].keys())
METHODS = sorted({s for r in rows for s in r["shown"]})
STRATA = ["noise-risk", "dark", "baseline"]

print(f"{len(rows)} photos; strata {Counter(r['stratum'] for r in rows)}")

# --- descriptive: per-method approval rate & always-pick baseline
shown = Counter(); appr = Counter(); fav = Counter()
for r in rows:
    for s in r["shown"]: shown[s] += 1
    for s in r["approved"]: appr[s] += 1
    if r["favorite"]: fav[r["favorite"]] += 1
print("\nmethod         shown approved  rate  favorite")
for m in METHODS:
    print(f"{m:14} {shown[m]:5} {appr[m]:8} {appr[m]/shown[m]:5.2f} {fav[m]:8}")
print("mean approved per photo", np.mean([len(r['approved']) for r in rows]))

def top1(score_fn, subset=None):
    """score_fn(row, slug) -> float. Returns dict of stratum -> (hit, n)."""
    res = defaultdict(lambda: [0, 0])
    for r in (subset or rows):
        sc = {s: score_fn(r, s) for s in r["shown"]}
        best = max(sc.values())
        # near-tie tiebreak preferring original like select_best (eps 1e-3 relative-ish)
        pick = max(sc, key=lambda s: (sc[s], s == "original"))
        hit = pick in r["approved"]
        for k in ("overall", r["stratum"]):
            res[k][0] += hit; res[k][1] += 1
    return res

def pairs(score_fn, subset=None):
    c = n = 0
    for r in (subset or rows):
        rej = [s for s in r["shown"] if s not in r["approved"]]
        for g in r["approved"]:
            for b in rej:
                n += 1; c += score_fn(r, g) > score_fn(r, b)
    return c, n

def fmt(res, pr=None):
    s = "  ".join(f"{k}={res[k][0]/res[k][1]*100:5.1f}%({res[k][1]})" for k in ["overall"] + STRATA if k in res)
    if pr: s += f"  pairs={pr[0]/pr[1]*100:5.1f}%"
    return s

def always(m):
    return lambda r, s: (1.0 if s == m else 0.0) + (0.5 if s == "original" else 0)
print()
for m in METHODS:
    print(f"always {m:14}", fmt(top1(always(m))))

def f(name, sign=1):
    return lambda r, s: sign * r["feats"][s][name]
print("\nuciqe-nr repro:", fmt(top1(lambda r, s: r["feats"][s]["uciqe"] - 4 * r["feats"][s]["speckle_a"]),
                            pairs(lambda r, s: r["feats"][s]["uciqe"] - 4 * r["feats"][s]["speckle_a"])))

# --- single-feature concordance
print("\nsingle features (pair concordance, top-1) — sign chosen best")
out = []
for name in FEATS:
    for sign in (1, -1):
        c, n = pairs(f(name, sign))
        out.append((c / n, sign, name))
out.sort(reverse=True)
seen = set()
for rate, sign, name in out:
    if name in seen: continue
    seen.add(name)
    t = top1(f(name, sign))
    print(f"{'+' if sign>0 else '-'}{name:16} pairs={rate*100:5.1f}%  {fmt(t)}")
