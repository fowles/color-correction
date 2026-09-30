import glob, random, sys, math, pickle
from pathlib import Path
import numpy as np
from PIL import Image, ImageOps

random.seed(0)
pairs = sorted(glob.glob("/Users/mfk/dev/photogen/photos/*/*.dive-plus.*"))
sample = random.sample(pairs, 100)          # same 100 as before (seed 0)
holdout = random.sample([p for p in pairs if p not in sample], 60)
D = {r["path"]: r for r in pickle.load(open(Path(__file__).with_name("diveplus_dcc.pkl"), "rb"))}
W = 480
def load(p):
    im = ImageOps.exif_transpose(Image.open(p)).convert("RGB"); im.thumbnail((W, W * 10)); return np.asarray(im).astype(float)
def rmse(a, b): return float(np.sqrt(np.mean((a - b) ** 2)))
def hs_row(h):
    U = math.cos(math.radians(h)); Wc = math.sin(math.radians(h))
    return np.array([0.299 + 0.701 * U + 0.168 * Wc, 0.587 - 0.587 * U + 0.330 * Wc, 0.114 - 0.114 * U - 0.497 * Wc])

def stretch(ch, lo_pct, hi_pct, hi_cap=None):
    lo = np.percentile(ch, lo_pct); hi = np.percentile(ch, hi_pct)
    if hi_cap is not None: hi = min(hi, hi_cap)
    if hi - lo < 1: return np.clip(ch, 0, 255)
    return np.clip((ch - lo) * 255.0 / (hi - lo), 0, 255)

def h_lookup(in_r):
    # piecewise-linear on the bucket medians from the fitted sample
    xs = [0, 3, 8, 15, 30, 55, 90, 140]; ys = [92, 90, 81, 78, 77, 76, 62, 20]
    return float(np.interp(in_r, xs, ys))

def h_ratio(in_r, in_g):
    # alternative: based on red/green ratio
    r = in_r / max(in_g, 1)
    xs = [0, 0.03, 0.07, 0.15, 0.3, 0.5, 0.75, 1.0]; ys = [92, 90, 81, 78, 77, 74, 55, 15]
    return float(np.interp(r, xs, ys))

def correct(x, h, lo=0.4, hi=99.9, magic=1.0):
    row = hs_row(h) * np.array([1, 1, magic])
    r1 = x @ row
    out = np.empty_like(x)
    out[..., 0] = stretch(r1, lo, hi)
    out[..., 1] = stretch(x[..., 1], lo, hi)
    out[..., 2] = stretch(x[..., 2], lo, hi)
    return out

def run(paths, label, hfn, **kw):
    errs = []
    for dp in paths:
        op = dp.replace(".dive-plus", "")
        x = load(op); y = load(dp)
        if x.shape != y.shape: continue
        m = x.reshape(-1, 3).mean(0)
        h = hfn(m, op)
        errs.append(rmse(correct(x, h, **kw), y))
    e = np.array(errs)
    print(f"{label:48} n={len(e):3} RMSE median {np.median(e):5.1f}  p10 {np.percentile(e,10):5.1f}  p90 {np.percentile(e,90):5.1f}  mean {e.mean():5.1f}")
    return e

oracle_h = lambda m, op: D[op]["h_fit"]
if "--fit" in sys.argv:
    print("== on the 100 fitted pairs ==")
    run(sample, "oracle h, stretch(0.4,99.9)", oracle_h)
    for lo, hi in ((0.1, 99.9), (0.4, 99.9), (0.4, 99.95), (0.5, 99.9), (1.0, 99.9), (0.4, 99.5), (0.4, 100)):
        run(sample, f"lookup h(in_r), stretch({lo},{hi})", lambda m, op: h_lookup(m[0]), lo=lo, hi=hi)
    run(sample, "ratio h(r/g), stretch(0.4,99.9)", lambda m, op: h_ratio(m[0], m[1]))
    run(sample, "fixed h=80, stretch(0.4,99.9)", lambda m, op: 80.0)
    run(sample, "fixed h=90 magic1.2, stretch(0.4,99.9)", lambda m, op: 90.0, magic=1.2)
    run(sample, "h=0 (pure per-channel stretch, ~channel-stretch)", lambda m, op: 0.0)
print("== HOLDOUT 60 pairs ==")
run(holdout, "lookup h(in_r), stretch(0.4,99.9)", lambda m, op: h_lookup(m[0]))
run(holdout, "ratio h(r/g), stretch(0.4,99.9)", lambda m, op: h_ratio(m[0], m[1]))
run(holdout, "fixed h=80, stretch(0.4,99.9)", lambda m, op: 80.0)
run(holdout, "h=0 (pure per-channel stretch)", lambda m, op: 0.0)
