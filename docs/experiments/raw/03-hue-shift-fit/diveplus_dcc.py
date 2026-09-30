import glob, random, sys, math, pickle
from pathlib import Path
import numpy as np
from PIL import Image, ImageOps
sys.path.insert(0, str(Path(__file__).parent))
import dcc

random.seed(0)
pairs = sorted(glob.glob("/Users/mfk/dev/photogen/photos/*/*.dive-plus.*"))
pairs = random.sample(pairs, 100)
W = 480
def load(p):
    im = ImageOps.exif_transpose(Image.open(p)).convert("RGB"); im.thumbnail((W, W * 10))
    return np.asarray(im)
def rmse(a, b): return float(np.sqrt(np.mean((a.astype(float) - b.astype(float)) ** 2)))

def hs_row(h):
    U = math.cos(math.radians(h)); Wc = math.sin(math.radians(h))
    return np.array([0.299 + 0.701 * U + 0.168 * Wc, 0.587 - 0.587 * U + 0.330 * Wc, 0.114 - 0.114 * U - 0.497 * Wc])

def fit_constrained(x, y):
    """Best (h, red_gain, red_off) for the red row given the model R' = gain*(hs_row(h)·[R,G,B]) + off,
    with blue coeff possibly scaled by a magic value; grid over h, lstsq for gain/off. Also fits G/B affine."""
    X = x.reshape(-1, 3).astype(float); Y = y.reshape(-1, 3).astype(float)
    best = None
    for magic in (1.0, 1.2):
        for h in range(0, 121):
            row = hs_row(h) * np.array([1, 1, magic])
            proj = X @ row
            A = np.stack([proj, np.ones_like(proj)], 1)
            (g, o), *_ = np.linalg.lstsq(A, Y[:, 0], rcond=None)
            e = np.sqrt(np.mean((np.clip(A @ [g, o], 0, 255) - Y[:, 0]) ** 2))
            if best is None or e < best[0]: best = (e, h, magic, g, o)
    return best

res = []
for i, dp in enumerate(pairs):
    op = dp.replace(".dive-plus", "")
    x = load(op); y = load(dp)
    if x.shape != y.shape: continue
    out = dcc.correct(x.copy())[..., ::-1]  # returns BGR
    e_dcc = rmse(out, y)
    # per-channel: what does dcc's stretch do vs Dive+? compare channel means
    e_red, h, magic, g, o = fit_constrained(x, y)
    # what hue shift would dcc pick?
    avg = np.array(x.reshape(-1, 3).mean(0), dtype=np.uint8); hh = 0; nr = avg[0]
    while nr < dcc.MIN_AVG_RED and hh <= dcc.MAX_HUE_SHIFT:
        nr = np.sum(dcc.hue_shift_red(avg, hh)); hh += 1
    res.append(dict(path=op, e_dcc=e_dcc, e_red_fit=e_red, h_fit=h, magic=magic, red_gain=g, red_off=o, h_dcc=hh - 1 if hh else 0,
                    in_mean=x.reshape(-1, 3).mean(0), out_mean=y.reshape(-1, 3).mean(0), dcc_mean=out.reshape(-1, 3).mean(0)))
    print(f"{i:3} dcc-vs-dive+ rmse={e_dcc:5.1f}  red-row constrained fit rmse={e_red:4.1f} h={h:3} magic={magic} gain={g:.2f} off={o:6.1f} | dcc would pick h={hh-1:3}  in_mean={np.round(res[-1]['in_mean'])} dive+={np.round(res[-1]['out_mean'])} dcc={np.round(res[-1]['dcc_mean'])}", file=sys.stderr)

pickle.dump(res, open(Path(__file__).with_name("diveplus_dcc.pkl"), "wb"))
E = np.array([r["e_dcc"] for r in res]); H = np.array([r["h_fit"] for r in res]); Hd = np.array([r["h_dcc"] for r in res])
print(f"\nn={len(res)} dcc-vs-Dive+ RMSE median {np.median(E):.1f} p10 {np.percentile(E,10):.1f} p90 {np.percentile(E,90):.1f}")
print(f"constrained red-row fit RMSE median {np.median([r['e_red_fit'] for r in res]):.2f}")
print(f"fitted h: median {np.median(H)} p10 {np.percentile(H,10)} p90 {np.percentile(H,90)};  magic=1.2 chosen in {np.mean([r['magic']==1.2 for r in res])*100:.0f}%")
print(f"dcc-rule h: median {np.median(Hd)} ; corr(fitted h, dcc h) = {np.corrcoef(H, Hd)[0,1]:.2f}")
