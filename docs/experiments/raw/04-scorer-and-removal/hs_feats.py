import json, sys
from pathlib import Path
import numpy as np
from PIL import Image
sys.path.insert(0, "/Users/mfk/dev/photogen")
sys.path.insert(0, str(Path(__file__).parent))
from photogen.config import load_config
from photogen.variant_labels import variant_thumb_resolver
cfg = load_config(Path("/Users/mfk/dev/photogen"))
resolve = variant_thumb_resolver(cfg.output_dir, cfg.cache_dir)
from photogen.quality import _decode_lab, chroma_speckle
import random; random.seed(1)
entries = sorted(cfg.cache_dir.glob("*/*.json"))
dp = [p for p in entries if "dive-plus" in json.loads(p.read_text()).get("variant_selection", {}).get("scores", {})]
sample = random.sample(dp, 120)
rows = {s: [] for s in ("original","dive-plus","hue-shift","channel-stretch","dicam")}
for p in sample:
    for s in rows:
        f = resolve(p.parent.name, p.stem, s)
        if not f: continue
        im = Image.open(f); im.thumbnail((600, 6000))
        L, a, b = _decode_lab(im)
        rgb = np.asarray(im.convert("RGB")).astype(float)
        hsv = np.asarray(im.convert("HSV")).astype(float)
        rows[s].append(dict(lc=np.percentile(L,99)-np.percentile(L,1), spk=chroma_speckle(a), sat=hsv[...,1].mean(),
                            rg=rgb[...,0].mean()/max(rgb[...,1].mean(),1), lmean=L.mean(), clip_lo=(rgb.min(2)<=1).mean(), clip_hi=(rgb.max(2)>=254).mean(),
                            cnr=np.percentile(L,99)-np.percentile(L,1)-3*chroma_speckle(a)))
for s, rs in rows.items():
    print(f"{s:16}", "  ".join(f"{k}={np.median([r[k] for r in rs]):7.2f}" for k in rs[0]))
# paired: hue-shift minus dive-plus
print("hs - dp paired medians:", {k: round(float(np.median([h[k]-d[k] for h,d in zip(rows['hue-shift'], rows['dive-plus'])])),2) for k in rows['dive-plus'][0]})
