# SPDX-License-Identifier: MIT
"""DICAM underwater image restoration — the only torch-touching correction
module. Lazy singleton model, lock-serialized native-res inference. Required at
build time: see preflight(). Vendored network in underwater_color/vendor/dicam/."""
from __future__ import annotations

import hashlib
import threading
from pathlib import Path

import numpy as np

# Upstream's published weights (pinned to DICAM main @ c0dba84).
CHECKPOINT_URL = "https://raw.githubusercontent.com/hfarhaditolie/DICAM/c0dba84931533c64eb8597782cf012f4c2a4e6eb/ckpts/UIEB/DICAM_60.pt"
CHECKPOINT_FILE = "DICAM_60.pt"              # local cache filename (upstream name)
CHECKPOINT_SHA256 = "b747fe58a954fa6bd1c22a1e8a08a082506d097cd1814821abc8715fca793b7e"

# DICAM is fully-convolutional (no spatial downsampling) so memory scales with
# resolution; run it at a capped working size and transfer the color correction
# to native res via a multiplicative ratio map (see enhance()).
WORK_LONGEST = 1024      # DICAM runs at this longest-side
RATIO_EPS = 1e-3         # stabilizes the out/input ratio near black
RATIO_CLIP = 10.0        # clamp ratio to avoid blowups from near-zero input

_LOCK = threading.Lock()
_MODEL = None  # cached nn.Module


def reset_singleton_for_test() -> None:
    global _MODEL
    _MODEL = None


def _device():
    import torch
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def _cache_dir() -> Path:
    # Note: a checkpoint cached under a prior tool's cache directory is not
    # reused here. The checkpoint is sha256-pinned, so a re-download costs
    # bandwidth and nothing else — not a correctness risk.
    d = Path.home() / ".cache" / "underwater-color" / "dicam"
    d.mkdir(parents=True, exist_ok=True)
    return d


def checkpoint_path() -> Path:
    """Local cache path for the checkpoint. Does not download."""
    return _cache_dir() / CHECKPOINT_FILE


def _verify_sha256(path: Path) -> bool:
    if CHECKPOINT_SHA256 in ("", "REPLACE_ME"):
        return True  # hash not pinned yet
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest() == CHECKPOINT_SHA256


def _fetch(url: str, out: Path) -> None:
    import requests
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        tmp = out.with_suffix(out.suffix + ".part")
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
        tmp.replace(out)


def download_checkpoint(*, log=print) -> Path:
    """Download the DICAM checkpoint from upstream if absent. Idempotent."""
    dest = checkpoint_path()
    if dest.exists() and _verify_sha256(dest):
        log("DICAM checkpoint already present.")
        return dest
    log(f"Downloading DICAM checkpoint from {CHECKPOINT_URL} …")
    _fetch(CHECKPOINT_URL, dest)
    if not _verify_sha256(dest):
        dest.unlink(missing_ok=True)
        raise RuntimeError("DICAM checkpoint failed sha256 verification.")
    log("DICAM checkpoint ready.")
    return dest


def _build_and_load():
    """Build the vendored network and load the checkpoint onto the device."""
    import torch
    from underwater_color.vendor.dicam.network import build_default_network
    ckpt = checkpoint_path()
    if not ckpt.exists():
        raise FileNotFoundError(f"checkpoint not found at {ckpt}")
    net = build_default_network()
    # weights_only=False: DICAM_60.pt bundles an argparse.Namespace ('opt') and
    # optimizer state beside the weights, which the PyTorch>=2.6 default
    # (weights_only=True) rejects. The checkpoint is sha256-pinned from a trusted
    # MIT upstream, so allowing full unpickling is acceptable here.
    state = torch.load(ckpt, map_location="cpu", weights_only=False)
    # weights live under 'model_state_dict' (verified against the vendored net:
    # zero missing/unexpected keys). Fall back to other common layouts.
    if isinstance(state, dict):
        state = state.get("model_state_dict", state.get("state_dict", state))
    net.load_state_dict(state)
    net.eval().to(_device())
    return net


def _get_model():
    global _MODEL
    if _MODEL is None:
        _MODEL = _build_and_load()
    return _MODEL


def preflight() -> None:
    """Eagerly load the model so all failure modes surface before build work."""
    try:
        _get_model()
    except Exception as e:  # missing file, bad state_dict, device error
        raise RuntimeError(
            f"DICAM checkpoint at {checkpoint_path()} could not be loaded "
            f"({type(e).__name__}: {e}). Run underwater_color.dicam."
            "download_checkpoint() to download the required model before "
            "building."
        ) from e


def work_input(arr: np.ndarray, longest: int = WORK_LONGEST) -> np.ndarray:
    """``arr`` (uint8 HxWx3) resized so its longest side is at most
    ``longest``, as the float32 HxWx3 in [0, 1] that DICAM takes."""
    import cv2
    h, w = arr.shape[:2]
    scale = min(1.0, longest / float(max(h, w)))
    if scale < 1.0:
        wh = (max(1, round(w * scale)), max(1, round(h * scale)))  # cv2 size = (W, H)
        arr = cv2.resize(arr, wh, interpolation=cv2.INTER_AREA)
    return arr.astype(np.float32) / 255.0


def transfer(arr: np.ndarray, small_f: np.ndarray,
             out_small: np.ndarray) -> np.ndarray:
    """Carry DICAM's color from the working resolution back to ``arr``'s:
    the ratio of its output ``out_small`` to its input ``small_f`` (both
    float HxWx3 in [0, 1]) is smooth, so it upsamples cleanly and is applied
    to the full-res original, keeping native detail. Returns uint8 HxWx3."""
    import cv2
    h, w = arr.shape[:2]
    ratio_small = np.clip((out_small + RATIO_EPS) / (small_f + RATIO_EPS), 0.0, RATIO_CLIP)
    ratio_full = cv2.resize(ratio_small, (w, h), interpolation=cv2.INTER_LINEAR)
    enhanced = np.clip(arr.astype(np.float32) * ratio_full, 0, 255)
    return enhanced.astype(np.uint8)


def enhance(arr: np.ndarray) -> np.ndarray:
    """DICAM color correction via ratio-map transfer: DICAM runs on
    work_input(arr), and transfer() applies its color at native resolution.
    uint8 HxWx3 (RGB) in, uint8 HxWx3 out."""
    import torch
    small_f = work_input(arr)
    with _LOCK:
        net = _get_model()
        dev = next(net.parameters()).device if any(True for _ in net.parameters()) else _device()
        t = torch.from_numpy(small_f).permute(2, 0, 1).unsqueeze(0).to(dev)
        with torch.no_grad():
            out = net(t).clamp(0.0, 1.0)
        out_small = out.squeeze(0).permute(1, 2, 0).cpu().numpy()  # HxWx3 in [0,1]
    return transfer(arr, small_f, out_small)
