import json, sys
from pathlib import Path
sys.path.insert(0, "/Users/mfk/dev/photogen")
from photogen.config import load_config
from photogen.quality import select_best, HAND_CORRECTED_METHODS
from photogen.variant_labels import NEAR_TIE_FRACTION
cfg = load_config(Path("/Users/mfk/dev/photogen"))
n = win = tie = winall = tieall = 0
for p in cfg.cache_dir.glob("*/*.json"):
    sc = json.loads(p.read_text()).get("variant_selection", {}).get("scores", {})
    if "hue-shift" not in sc: continue
    n += 1
    for drop, (w, t) in ((set(HAND_CORRECTED_METHODS), "nodp"), (set(), "all")):
        s = {k: v for k, v in sc.items() if k not in drop}
        top = max(s.values()); hs = s["hue-shift"]
        is_win = select_best(s) == "hue-shift"
        near = hs >= top - NEAR_TIE_FRACTION * abs(top)
        if t == "nodp": win += is_win; tie += (near and not is_win)
        else: winall += is_win; tieall += (near and not is_win)
print(f"n={n} tie_frac={NEAR_TIE_FRACTION}")
print(f"Dive+ removed : hue-shift selected {win/n*100:.1f}%, within {NEAR_TIE_FRACTION:.0%} of the top on another {tie/n*100:.1f}%  (total {(win+tie)/n*100:.1f}%)")
print(f"Dive+ present : hue-shift selected {winall/n*100:.1f}%, within {NEAR_TIE_FRACTION:.0%} of the top on another {tieall/n*100:.1f}%  (total {(winall+tieall)/n*100:.1f}%)")
