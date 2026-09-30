import pickle, sys, itertools
from collections import defaultdict, Counter
from pathlib import Path
import numpy as np
sys.path.insert(0, "/Users/mfk/dev/photogen")

rows = pickle.load((Path(__file__).with_name("features.pkl")).open("rb"))
# drop retired methods so we score over the live menu
RETIRED = {"gray-world", "white-patch"}
rows2 = []
for r in rows:
    shown = [s for s in r["shown"] if s not in RETIRED]
    appr = [s for s in r["approved"] if s not in RETIRED]
    if not appr: continue
    rows2.append(dict(r, shown=shown, approved=appr))
rows = rows2
STRATA = ["noise-risk", "dark", "baseline"]
def F(r, s, n): return r["feats"][s][n]
FEATS = sorted(rows[0]["feats"]["original"].keys())

def cnr(r, s): return F(r, s, "l_contrast") - 3.0 * F(r, s, "speckle_a")

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

print(f"n={len(rows)}")
print("contrast-nr        ", summarize(cnr, rows))
print("contrast-nr +dp    ", summarize(lambda r, s: cnr(r, s) + (1000 if s == "dive-plus" else 0), rows))

# 1. Where dive-plus shown+approved but cnr picks something else: how does dive-plus differ from the pick?
print("\n=== dive-plus approved, cnr missed: dive-plus minus cnr-pick, per feature (median, and sign consistency) ===")
diffs = defaultdict(list)
n_dp = n_miss = 0
for r in rows:
    if "dive-plus" not in r["shown"] or "dive-plus" not in r["approved"]: continue
    n_dp += 1
    _, _, _, pick = per_photo(cnr, r)
    if pick == "dive-plus" or pick in r["approved"]: continue
    n_miss += 1
    for f in FEATS:
        diffs[f].append(F(r, "dive-plus", f) - F(r, pick, f))
print(f"dive-plus shown&approved: {n_dp}; cnr missed (picked a rejected variant): {n_miss}")
res = []
for f in FEATS:
    d = np.array(diffs[f]);
    # scale by typical spread across variants
    spread = np.median([np.std([F(r, s, f) for s in r["shown"]]) for r in rows]) or 1e-9
    res.append((abs(np.mean(np.sign(d))), f, np.median(d), np.mean(d > 0), spread))
for cons, f, med, frac, spread in sorted(res, reverse=True)[:20]:
    print(f"  {f:14} median Δ={med:+8.2f}  frac>0={frac:4.2f}  (typ within-photo std {spread:6.2f})")

# 2. Search: cnr + w * feat  (feature-normalised) — does any single added feature reproduce the +dp lift?
print("\n=== cnr + w*feature: best top-1 over w grid ===")
results = []
for f in FEATS:
    spread = np.median([np.std([F(r, s, f) for s in r["shown"]]) for r in rows]) or 1e-9
    spr_c = np.median([np.std([cnr(r, s) for s in r["shown"]]) for r in rows])
    best = None
    for w in [-4, -2, -1, -0.5, -0.25, 0.25, 0.5, 1, 2, 4]:
        ww = w * spr_c / spread
        fn = lambda r, s, ww=ww, f=f: cnr(r, s) + ww * F(r, s, f)
        hits = sum(per_photo(fn, r)[0] for r in rows) / len(rows)
        if best is None or hits > best[0]: best = (hits, w, fn)
    results.append((best[0], f, best[1], best[2]))
for hits, f, w, fn in sorted(results, reverse=True)[:12]:
    print(f"  {f:14} w={w:+5.2f}  ", summarize(fn, rows))

# 3. Where does dive-plus itself sit on the top candidates vs others (all photos where shown)?
print("\n=== per-variant medians (photos where dive-plus shown) ===")
sub = [r for r in rows if "dive-plus" in r["shown"]]
for f in ("l_contrast", "speckle_a", "hsv_sat_mean", "cast", "chroma_mean", "colorfulness", "clip_hi", "clip_lo", "r_frac", "rg_ratio", "l_mean", "hue_bluecyan", "entropy"):
    line = f"  {f:14}"
    for s in ("original", "dive-plus", "channel-stretch", "ancuti-fusion", "dicam", "google"):
        vals = [F(r, s, f) for r in sub if s in r["shown"]]
        if vals: line += f" {s[:8]:>8}={np.median(vals):7.2f}"
    print(line)

# 4. shaped / two-feature candidates
print("\n=== shaped candidates ===")
def rg_band(r, s, lo=0.6, hi=1.0):
    x = F(r, s, "rg_ratio"); return -max(0.0, lo - x) - max(0.0, x - hi)  # 0 inside band, negative outside
def sat_pen(r, s, t=150): return -max(0.0, F(r, s, "hsv_sat_mean") - t)
def cast_pen(r, s, t=15): return -max(0.0, F(r, s, "cast") - t)
def rgcap(r, s, cap=0.8): return min(F(r, s, "rg_ratio"), cap)
SHAPED = {}
for w in (5, 10, 20, 40, 80):
    SHAPED[f"cnr+{w}*rgband(.6,1)"] = lambda r, s, w=w: cnr(r, s) + w * rg_band(r, s)
    SHAPED[f"cnr+{w}*rgband(.5,.95)"] = lambda r, s, w=w: cnr(r, s) + w * rg_band(r, s, .5, .95)
    SHAPED[f"cnr+{w}*rgcap(.8)"] = lambda r, s, w=w: cnr(r, s) + w * rgcap(r, s)
    SHAPED[f"cnr+{w}*rgcap(.7)"] = lambda r, s, w=w: cnr(r, s) + w * rgcap(r, s, .7)
for w in (0.05, 0.1, 0.2, 0.4):
    for t in (120, 150, 180, 200):
        SHAPED[f"cnr+{w}*satpen({t})"] = lambda r, s, w=w, t=t: cnr(r, s) + w * sat_pen(r, s, t)
for w in (0.5, 1, 2):
    for t in (10, 15, 20, 25):
        SHAPED[f"cnr+{w}*castpen({t})"] = lambda r, s, w=w, t=t: cnr(r, s) + w * cast_pen(r, s, t)
for w in (200, 500, 1000, 2000):
    SHAPED[f"cnr-{w}*sat_clip"] = lambda r, s, w=w: cnr(r, s) - w * F(r, s, "sat_clip")
    SHAPED[f"cnr-{w}*clip_lo"] = lambda r, s, w=w: cnr(r, s) - w * F(r, s, "clip_lo")
out = []
for k, fn in SHAPED.items():
    hits = sum(per_photo(fn, r)[0] for r in rows) / len(rows)
    out.append((hits, k, fn))
for hits, k, fn in sorted(out, key=lambda t: -t[0])[:25]:
    print(f"  {k:24}", summarize(fn, rows))

# what does the best shaped one do WITHOUT dive-plus in the menu (i.e. how it would rank hue-shift-like variants)?
print("\n=== same, but with dive-plus/google removed from the menu (photos that still have an approved variant) ===")
def strip(rs):
    out = []
    for r in rs:
        shown = [s for s in r["shown"] if s not in ("dive-plus", "google")]
        appr = [s for s in r["approved"] if s in shown]
        if appr: out.append(dict(r, shown=shown, approved=appr))
    return out
rows_nd = strip(rows)
print(f"n={len(rows_nd)}")
print("  contrast-nr             ", summarize(cnr, rows_nd))
for hits, k, fn in sorted(out, key=lambda t: -t[0])[:12]:
    print(f"  {k:24}", summarize(fn, rows_nd))

# 5. a learned per-METHOD prior (approval rate when shown), leave-one-out, added to cnr in units of cnr's within-photo spread
print("\n=== cnr + beta * spread * (approval_rate[method] - 0.5), leave-one-photo-out ===")
spr_c = np.median([np.std([cnr(r, s) for s in r["shown"]]) for r in rows])
shown_ct = Counter(); appr_ct = Counter()
for r in rows:
    for s in r["shown"]: shown_ct[s] += 1
    for s in r["approved"]: appr_ct[s] += 1
print("  approval rate when shown:", {s: f"{appr_ct[s]/shown_ct[s]:.2f} (n={shown_ct[s]})" for s in shown_ct})
def loo_rate(r, s):
    n = shown_ct[s] - 1; a = appr_ct[s] - (1 if s in r["approved"] else 0)
    return (a + 1) / (n + 2)
for beta in (0.5, 1, 2, 4, 8):
    fn = lambda r, s, beta=beta: cnr(r, s) + beta * spr_c * (loo_rate(r, s) - 0.5)
    print(f"  beta={beta:<4}", summarize(fn, rows), " | no-dp menu:", summarize(fn, rows_nd))

print("\n=== inverted-U saturation band: cnr - w*max(0,|sat-target|-halfwidth) ===")
res = []
for tgt in (80, 100, 120):
    for hw in (0, 20, 40, 60):
        for w in (0.1, 0.2, 0.4):
            fn = lambda r, s, tgt=tgt, hw=hw, w=w: cnr(r, s) - w * max(0.0, abs(F(r, s, "hsv_sat_mean") - tgt) - hw)
            res.append((sum(per_photo(fn, r)[0] for r in rows) / len(rows), f"tgt={tgt} hw={hw} w={w}", fn))
for h, k, fn in sorted(res, key=lambda t: -t[0])[:8]:
    print(f"  {k:22}", summarize(fn, rows), " | no-dp menu:", summarize(fn, rows_nd))
