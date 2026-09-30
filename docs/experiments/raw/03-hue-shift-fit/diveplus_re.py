# Throwaway: reverse-engineer the original -> Dive+ transform from paired photos.
import glob, random, sys, pickle
from pathlib import Path
import numpy as np
from PIL import Image, ImageOps

random.seed(0)
pairs = sorted(glob.glob("/Users/mfk/dev/photogen/photos/*/*.dive-plus.*"))
pairs = random.sample(pairs, min(int(sys.argv[1]) if len(sys.argv) > 1 else 120, len(pairs)))
W = 480

def load(p):
    im = ImageOps.exif_transpose(Image.open(p)).convert("RGB")
    im.thumbnail((W, W * 10))
    return np.asarray(im).astype(np.float64)

def rmse(a, b): return float(np.sqrt(np.mean((a - b) ** 2)))

def fit_affine(x, y):
    """per-channel y = g*x + o"""
    out = np.empty_like(y); params = []
    for c in range(3):
        A = np.stack([x[..., c].ravel(), np.ones(x[..., c].size)], 1)
        (g, o), *_ = np.linalg.lstsq(A, y[..., c].ravel(), rcond=None)
        out[..., c] = g * x[..., c] + o; params.append((g, o))
    return np.clip(out, 0, 255), params

def fit_matrix(x, y):
    """y = M x + o (3x3 + offset)"""
    A = np.concatenate([x.reshape(-1, 3), np.ones((x.shape[0] * x.shape[1], 1))], 1)
    M, *_ = np.linalg.lstsq(A, y.reshape(-1, 3), rcond=None)
    return np.clip((A @ M).reshape(y.shape), 0, 255), M

def fit_lut(x, y):
    """independent per-channel 256-entry LUT (conditional mean), smoothed"""
    out = np.empty_like(y); luts = []
    for c in range(3):
        xi = x[..., c].ravel().astype(int); yi = y[..., c].ravel()
        s = np.bincount(xi, yi, 256); n = np.bincount(xi, None, 256)
        lut = np.where(n > 0, s / np.maximum(n, 1), np.nan)
        # fill gaps by interpolation
        idx = np.arange(256); ok = ~np.isnan(lut)
        lut = np.interp(idx, idx[ok], lut[ok])
        out[..., c] = lut[xi].reshape(x.shape[:2]); luts.append(lut)
    return np.clip(out, 0, 255), luts

def fit_lut_matrix(x, y):
    """3x3 matrix+offset first, then per-channel LUT on top (matrix then curve)"""
    m, M = fit_matrix(x, y)
    o, luts = fit_lut(m, y)
    return o, (M, luts)

def local_structure(resid, x):
    """is the residual explained by local mean luminance (dehaze/CLAHE-like) or position?"""
    from scipy.ndimage import uniform_filter
    lum = x.mean(2)
    loc = uniform_filter(lum, 41)
    r = resid.mean(2)
    c_local = np.corrcoef(r.ravel(), (lum - loc).ravel())[0, 1]   # residual vs local contrast
    c_loc = np.corrcoef(r.ravel(), loc.ravel())[0, 1]             # residual vs neighbourhood brightness
    h, w = r.shape
    yy, xx = np.mgrid[0:h, 0:w]
    rad = np.hypot((yy - h / 2) / h, (xx - w / 2) / w)
    c_rad = np.corrcoef(r.ravel(), rad.ravel())[0, 1]             # vignetting-like
    # spatial autocorrelation of residual (lag 8)
    ac = np.corrcoef(r[:, :-8].ravel(), r[:, 8:].ravel())[0, 1]
    return dict(local_contrast=c_local, neigh_bright=c_loc, radial=c_rad, autocorr8=ac)

results = []
for i, dp in enumerate(pairs):
    op = dp.replace(".dive-plus", "")
    if not Path(op).exists(): continue
    y = load(dp); x = load(op)
    if y.shape != x.shape:
        continue
    r = dict(path=op, base=rmse(x, y))
    a, pa = fit_affine(x, y); r["affine"] = rmse(a, y); r["affine_p"] = pa
    m, pm = fit_matrix(x, y); r["matrix"] = rmse(m, y); r["matrix_p"] = pm
    l, pl = fit_lut(x, y); r["lut"] = rmse(l, y); r["lut_p"] = pl
    lm, plm = fit_lut_matrix(x, y); r["lut_matrix"] = rmse(lm, y)
    r["struct"] = local_structure(y - lm, x)
    r["stats_x"] = dict(mean=x.mean((0, 1)).tolist(), p1=np.percentile(x, 1, (0, 1)).tolist(), p99=np.percentile(x, 99, (0, 1)).tolist())
    r["stats_y"] = dict(mean=y.mean((0, 1)).tolist(), p1=np.percentile(y, 1, (0, 1)).tolist(), p99=np.percentile(y, 99, (0, 1)).tolist(),
                        clip_hi=(y >= 254).mean((0, 1)).tolist(), clip_lo=(y <= 1).mean((0, 1)).tolist())
    results.append(r)
    print(f"{i:3} {Path(op).name[:12]} base={r['base']:5.1f} affine={r['affine']:5.1f} matrix={r['matrix']:5.1f} lut={r['lut']:5.1f} lut+mat={r['lut_matrix']:5.1f}  "
          + " ".join(f"{k}={v:+.2f}" for k, v in r["struct"].items()), file=sys.stderr)

pickle.dump(results, open(Path(__file__).with_name("diveplus_fits.pkl"), "wb"))
R = lambda k: np.array([r[k] for r in results])
print(f"\nn={len(results)}  median RMSE: base={np.median(R('base')):.1f} affine={np.median(R('affine')):.1f} matrix={np.median(R('matrix')):.1f} lut={np.median(R('lut')):.1f} lut+matrix={np.median(R('lut_matrix')):.1f}")
for k in ("local_contrast", "neigh_bright", "radial", "autocorr8"):
    v = np.array([r["struct"][k] for r in results]); print(f"  resid corr {k}: median {np.median(v):+.2f}  |median| {np.median(np.abs(v)):.2f}")
