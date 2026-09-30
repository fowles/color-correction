import pickle, sys, itertools
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np

rows = pickle.load((Path(__file__).with_name("features.pkl")).open("rb"))
FEATS = sorted(rows[0]["feats"]["original"].keys())
STRATA = ["noise-risk", "dark", "baseline"]
rng = np.random.default_rng(0)

def evaluate(score_fn, subset=None):
    res = defaultdict(lambda: [0, 0]); c = n = 0
    for r in (subset or rows):
        sc = {s: score_fn(r, s) for s in r["shown"]}
        pick = max(sc, key=lambda s: (sc[s], s == "original"))
        hit = pick in r["approved"]
        for k in ("overall", r["stratum"]):
            res[k][0] += hit; res[k][1] += 1
        rej = [s for s in r["shown"] if s not in r["approved"]]
        for g in r["approved"]:
            for b in rej:
                n += 1; c += sc[g] > sc[b]
    return res, (c, n)

def fmt(res, pr):
    s = "  ".join(f"{k}={res[k][0]/res[k][1]*100:5.1f}%" for k in ["overall"] + STRATA if k in res)
    return s + f"  pairs={pr[0]/pr[1]*100:5.1f}%"

def F(r, s, name): return r["feats"][s][name]
uciqe_nr = lambda r, s: F(r, s, "uciqe") - 4 * F(r, s, "speckle_a")

print("baseline uciqe-nr     ", fmt(*evaluate(uciqe_nr)))
print("l_contrast            ", fmt(*evaluate(lambda r, s: F(r, s, "l_contrast"))))

# dive-plus prior
def with_dp(fn, bonus=1000):
    return lambda r, s: fn(r, s) + (bonus if s == "dive-plus" else 0)
print("uciqe-nr + dive+ first", fmt(*evaluate(with_dp(uciqe_nr))))
print("l_contrast + dive+ 1st", fmt(*evaluate(with_dp(lambda r, s: F(r, s, "l_contrast")))))
dp_rows = [r for r in rows if "dive-plus" in r["shown"]]
print(f"  photos with dive-plus shown: {len(dp_rows)}; strata {Counter(r['stratum'] for r in dp_rows)}")
print("  on those, uciqe-nr:", fmt(*evaluate(uciqe_nr, dp_rows)))
print("  on those, l_contrast:", fmt(*evaluate(lambda r, s: F(r, s, 'l_contrast'), dp_rows)))
nodp = [r for r in rows if "dive-plus" not in r["shown"]]
print(f"  photos WITHOUT dive-plus: {len(nodp)}")
print("  on those, uciqe-nr:", fmt(*evaluate(uciqe_nr, nodp)))
print("  on those, l_contrast:", fmt(*evaluate(lambda r, s: F(r, s, 'l_contrast'), nodp)))

# --- 2-feature grid: l_contrast + w * feature (feature z-scored per photo? no — raw, small grid on scale)
print("\n2-feature combos with l_contrast (raw scale weights):")
def std_of(name):
    return np.std([F(r, s, name) for r in rows for s in r["shown"]])
lc_sd = std_of("l_contrast")
results = []
for name in FEATS:
    if name == "l_contrast": continue
    sd = std_of(name) or 1.0
    for w in (-2, -1, -0.5, -0.25, 0.25, 0.5, 1, 2):
        ww = w * lc_sd / sd
        fn = lambda r, s, ww=ww, name=name: F(r, s, "l_contrast") + ww * F(r, s, name)
        res, pr = evaluate(fn)
        results.append((res["overall"][0], pr[0] / pr[1], name, w, fmt(res, pr)))
results.sort(reverse=True)
for x in results[:20]:
    print(f"  {x[2]:16} w={x[3]:+5.2f}sd  {x[4]}")

# --- logistic regression on pairwise differences, grouped 10-fold CV by photo
print("\nLogistic-regression pairwise model (grouped CV):")
try:
    from sklearn.linear_model import LogisticRegression
except ImportError:
    LogisticRegression = None
    print("  no sklearn; using numpy GD")

def zscore_table():
    X = np.array([[F(r, s, n) for n in FEATS] for r in rows for s in r["shown"]])
    return X.mean(0), X.std(0) + 1e-9
MU, SD = zscore_table()
def vec(r, s, names):
    idx = [FEATS.index(n) for n in names]
    v = np.array([F(r, s, n) for n in names])
    return (v - MU[idx]) / SD[idx]

def fit_pairs(train, names, C=1.0):
    X = []; y = []
    for r in train:
        rej = [s for s in r["shown"] if s not in r["approved"]]
        for g in r["approved"]:
            for b in rej:
                d = vec(r, g, names) - vec(r, b, names)
                X.append(d); y.append(1); X.append(-d); y.append(0)
    X = np.array(X); y = np.array(y)
    if LogisticRegression:
        m = LogisticRegression(C=C, fit_intercept=False, max_iter=2000).fit(X, y)
        return m.coef_[0]
    w = np.zeros(X.shape[1])
    for _ in range(3000):
        p = 1 / (1 + np.exp(-X @ w)); w -= 0.05 * (X.T @ (p - y) / len(y) + w / (C * len(y)))
    return w

def cv(names, C=1.0, k=10, seed=0):
    idx = np.arange(len(rows)); np.random.default_rng(seed).shuffle(idx)
    folds = np.array_split(idx, k)
    hits = defaultdict(lambda: [0, 0]); pc = pn = 0
    for i in range(k):
        test = [rows[j] for j in folds[i]]
        train = [rows[j] for f in folds[:i] + folds[i+1:] for j in f]
        w = fit_pairs(train, names, C)
        fn = lambda r, s: float(vec(r, s, names) @ w)
        res, pr = evaluate(fn, test)
        for kk, (h, n) in res.items(): hits[kk][0] += h; hits[kk][1] += n
        pc += pr[0]; pn += pr[1]
    return hits, (pc, pn)

sets = {
    "all": FEATS,
    "uciqe parts": ["chroma_std", "l_contrast", "sat_mean", "speckle_a"],
    "lc+entropy+lstd": ["l_contrast", "entropy", "l_std"],
    "lc+speckle": ["l_contrast", "speckle_a", "speckle_L"],
    "lc+clip": ["l_contrast", "clip_hi_any", "clip_lo_any"],
    "lc+color": ["l_contrast", "chroma_std", "cast", "r_frac", "hue_bluecyan"],
    "lc+lstd+entropy+clip+speckle": ["l_contrast", "l_std", "entropy", "clip_hi_any", "clip_lo_any", "speckle_a"],
}
for label, names in sets.items():
    for C in (0.01, 0.1, 1.0):
        res, pr = cv(names, C)
        print(f"  {label:30} C={C:<5} {fmt(res, pr)}")
    w = fit_pairs(rows, names, 0.1)
    top = sorted(zip(names, w), key=lambda t: -abs(t[1]))[:8]
    print("     full-fit weights:", ", ".join(f"{n}={v:+.2f}" for n, v in top))
