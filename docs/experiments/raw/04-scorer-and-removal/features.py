# Throwaway: extract a feature bank per (photo, shown variant) from the
# consensus approvals, pickle it for analysis.
import pickle, sys
from pathlib import Path
import numpy as np
from PIL import Image

sys.path.insert(0, "/Users/mfk/dev/photogen")
from photogen.config import load_config
from photogen.variant_labels import (
    APPROVALS_FILENAME, consensus_approvals, current_hash_lookup,
    load_approvals, partition_by_staleness, variant_thumb_resolver,
)
from photogen.quality import _decode_lab, chroma_speckle

base = Path("/Users/mfk/dev/photogen")
cfg = load_config(base)
approvals = load_approvals(base / APPROVALS_FILENAME, warn=lambda s: None)
part = partition_by_staleness(approvals, current_hash_lookup(cfg.cache_dir))
consensus, agreement = consensus_approvals(part.fresh)
resolve = variant_thumb_resolver(cfg.output_dir, cfg.cache_dir)


def feats(img):
    rgb = np.asarray(img.convert("RGB")).astype(np.float64)
    L, a, b = _decode_lab(img)
    f = {}
    chroma = np.sqrt(a * a + b * b)
    f["chroma_std"] = chroma.std()
    f["chroma_mean"] = chroma.mean()
    f["l_contrast"] = np.percentile(L, 99) - np.percentile(L, 1)
    f["l_std"] = L.std()
    f["l_mean"] = L.mean()
    sat = np.where(L > 0, chroma / np.maximum(L, 1e-6), 0.0)
    f["sat_mean"] = sat.mean()
    f["uciqe"] = 0.4680 * f["chroma_std"] + 0.2745 * f["l_contrast"] + 0.2576 * f["sat_mean"]
    f["speckle_a"] = chroma_speckle(a)
    f["speckle_b"] = chroma_speckle(b)
    f["speckle_L"] = chroma_speckle(L)
    f["a_mean"] = a.mean(); f["b_mean"] = b.mean()
    f["cast"] = np.hypot(a.mean(), b.mean())      # gray-world deviation
    f["a_std"] = a.std(); f["b_std"] = b.std()
    r, g, bl = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    f["r_mean"] = r.mean(); f["g_mean"] = g.mean(); f["b_mean_rgb"] = bl.mean()
    f["r_frac"] = r.mean() / max(rgb.mean(), 1e-6)
    f["rg_ratio"] = r.mean() / max(g.mean(), 1e-6)
    f["rb_ratio"] = r.mean() / max(bl.mean(), 1e-6)
    # Hasler-Susstrunk colorfulness
    rg = r - g; yb = 0.5 * (r + g) - bl
    f["colorfulness"] = np.hypot(rg.std(), yb.std()) + 0.3 * np.hypot(rg.mean(), yb.mean())
    # UICM (from UIQM): asymmetric alpha-trimmed mean/var of rg, yb
    def trim(x, alpha=0.1):
        s = np.sort(x.ravel()); n = s.size; k = int(alpha * n)
        s = s[k:n - k]
        return s.mean(), s.var()
    m_rg, v_rg = trim(rg); m_yb, v_yb = trim(yb)
    f["uicm"] = -0.0268 * np.hypot(m_rg, m_yb) + 0.1586 * np.sqrt(v_rg + v_yb)
    # sharpness (Laplacian variance) on gray, and EME-like local contrast
    gray = 0.299 * r + 0.587 * g + 0.114 * bl
    lap = (4 * gray[1:-1, 1:-1] - gray[:-2, 1:-1] - gray[2:, 1:-1]
           - gray[1:-1, :-2] - gray[1:-1, 2:])
    f["lap_var"] = lap.var()
    f["lap_med"] = np.median(np.abs(lap))
    f["lap_p90"] = np.percentile(np.abs(lap), 90)
    # clipping
    f["clip_hi"] = (rgb.max(axis=2) >= 254).mean()
    f["clip_lo"] = (rgb.min(axis=2) <= 1).mean()
    f["clip_hi_any"] = (rgb >= 254).mean()
    f["clip_lo_any"] = (rgb <= 1).mean()
    # per-channel percentile spans (raw dynamic range use)
    for name, ch in (("r", r), ("g", g), ("b", bl)):
        f[f"{name}_span"] = np.percentile(ch, 99) - np.percentile(ch, 1)
    # entropy of gray
    hist, _ = np.histogram(gray, bins=256, range=(0, 255)); p = hist / hist.sum(); p = p[p > 0]
    f["entropy"] = -(p * np.log2(p)).sum()
    # HSV saturation
    hsv = np.asarray(img.convert("HSV")).astype(np.float64)
    f["hsv_sat_mean"] = hsv[..., 1].mean()
    f["hsv_sat_p95"] = np.percentile(hsv[..., 1], 95)
    f["sat_clip"] = (hsv[..., 1] >= 250).mean()
    # blue/green dominance (underwater cast) in hue: fraction of pixels in blue-cyan hue band
    h = hsv[..., 0]  # 0-255
    f["hue_bluecyan"] = ((h > 120) & (h < 180) & (hsv[..., 1] > 40)).mean()
    f["hue_redorange"] = (((h < 25) | (h > 240)) & (hsv[..., 1] > 40)).mean()
    # extreme chroma fraction (garish)
    f["chroma_p99"] = np.percentile(chroma, 99)
    f["chroma_hi"] = (chroma > 60).mean()
    return {k: float(v) for k, v in f.items()}


rows = []
for ap in consensus:
    if not ap.approved:
        continue
    per = {}
    ok = True
    for slug in ap.shown:
        p = resolve(ap.dive_slug, ap.stem, slug)
        if p is None or not p.exists():
            ok = False; break
        with Image.open(p) as im:
            per[slug] = feats(im)
    if not ok:
        continue
    rows.append(dict(dive=ap.dive_slug, stem=ap.stem, stratum=ap.stratum,
                     shown=list(ap.shown), approved=list(ap.approved),
                     favorite=ap.favorite, feats=per,
                     ctx_scores=(ap.context or {}).get("scores")))
    print(len(rows), end="\r", file=sys.stderr)

out = Path(__file__).with_name("features.pkl")
pickle.dump(rows, out.open("wb"))
print(f"\n{len(rows)} photos", file=sys.stderr)
