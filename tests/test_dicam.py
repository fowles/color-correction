# SPDX-License-Identifier: MIT
import threading
import numpy as np
import pytest

torch = pytest.importorskip("torch")
import underwater_color.dicam as dc


@pytest.fixture(autouse=True)
def _clean():
    dc.reset_singleton_for_test()
    yield
    dc.reset_singleton_for_test()


class _IdentityNet(torch.nn.Module):
    def forward(self, x):
        return x


def test_preflight_missing_checkpoint_hard_fails(monkeypatch, tmp_path):
    # point at a path that does not exist -> _build_and_load must raise
    ckpt = tmp_path / "absent.pth"
    monkeypatch.setattr(dc, "checkpoint_path", lambda: ckpt)
    with pytest.raises(RuntimeError) as e:
        dc.preflight()
    msg = str(e.value)
    assert "download_checkpoint" in msg and "checkpoint" in msg.lower()
    assert str(ckpt) in msg  # message must name the actual checkpoint path


def test_preflight_corrupt_checkpoint_names_path(monkeypatch, tmp_path):
    # a present-but-corrupt checkpoint fails inside torch.load (not FileNotFound);
    # the RuntimeError must still name the path so the user knows which file.
    ckpt = tmp_path / "DICAM_60.pt"
    ckpt.write_bytes(b"not a real checkpoint")
    monkeypatch.setattr(dc, "checkpoint_path", lambda: ckpt)
    with pytest.raises(RuntimeError) as e:
        dc.preflight()
    assert str(ckpt) in str(e.value) and "download_checkpoint" in str(e.value)


def test_enhance_shape_dtype_with_fake_model(monkeypatch):
    monkeypatch.setattr(dc, "_build_and_load", lambda: _IdentityNet().eval())
    arr = (np.random.rand(30, 47, 3) * 255).astype(np.uint8)
    out = dc.enhance(arr)
    assert out.shape == arr.shape and out.dtype == np.uint8


def test_model_loaded_once(monkeypatch):
    calls = {"n": 0}
    def _load():
        calls["n"] += 1
        return _IdentityNet().eval()
    monkeypatch.setattr(dc, "_build_and_load", _load)
    arr = (np.random.rand(16, 16, 3) * 255).astype(np.uint8)
    dc.enhance(arr); dc.enhance(arr)
    assert calls["n"] == 1


def test_enhance_serialized_under_lock(monkeypatch):
    monkeypatch.setattr(dc, "_build_and_load", lambda: _IdentityNet().eval())
    assert isinstance(dc._LOCK, type(threading.Lock()))


def test_download_checkpoint_skips_when_present(monkeypatch, tmp_path):
    dest = tmp_path / "DICAM_60.pt"
    dest.write_bytes(b"already here")
    monkeypatch.setattr(dc, "checkpoint_path", lambda: dest)
    monkeypatch.setattr(dc, "_verify_sha256", lambda p: True)
    def _boom(*a, **k):
        raise AssertionError("should not download when present + valid")
    monkeypatch.setattr(dc, "_fetch", _boom)
    assert dc.download_checkpoint(log=lambda *a: None) == dest


def test_download_checkpoint_fetches_when_absent(monkeypatch, tmp_path):
    dest = tmp_path / "DICAM_60.pt"
    monkeypatch.setattr(dc, "checkpoint_path", lambda: dest)
    calls = {"n": 0}
    def _fetch(url, out):
        calls["n"] += 1
        out.write_bytes(b"downloaded")
    monkeypatch.setattr(dc, "_fetch", _fetch)
    monkeypatch.setattr(dc, "_verify_sha256", lambda p: True)
    dc.download_checkpoint(log=lambda *a: None)
    assert calls["n"] == 1 and dest.exists()
