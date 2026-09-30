import random, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageOps

sys.path.insert(0, "/Users/mfk/dev/photogen")
from photogen.correct import hue_shift, channel_stretch

root = Path("/Users/mfk/dev/photogen/photos")
pairs = []
for dp in root.glob("*/*.dive-plus.webp"):
    orig = dp.with_name(dp.name.replace(".dive-plus", ""))
    if orig.exists():
        pairs.append((orig, dp))
random.seed(int(sys.argv[1]) if len(sys.argv) > 1 else 0)
sample = random.sample(pairs, min(40, len(pairs)))


def load(p):
    im = ImageOps.exif_transpose(Image.open(p)).convert("RGB")
    im.thumbnail((480, 480))
    return np.asarray(im)


def rmse(a, b):
    return float(np.sqrt(((a.astype(np.float64) - b.astype(np.float64)) ** 2).mean()))


hs, cs = [], []
for orig, dp in sample:
    o, d = load(orig), load(dp)
    if o.shape != d.shape:
        continue
    hs.append(rmse(hue_shift(o), d))
    cs.append(rmse(channel_stretch(o), d))
hs, cs = np.array(hs), np.array(cs)
print(f"pairs total={len(pairs)} used={len(hs)}")
print(f"hue-shift      median={np.median(hs):.1f} p90={np.percentile(hs, 90):.1f} mean={hs.mean():.1f}")
print(f"channel-stretch median={np.median(cs):.1f} p90={np.percentile(cs, 90):.1f} mean={cs.mean():.1f}")
