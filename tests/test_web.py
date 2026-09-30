# SPDX-License-Identifier: MIT
"""web/glue.py, the Python half of the static page, run under CPython against
the real correct module (Pyodide runs the same file)."""
import importlib.util
from pathlib import Path

import numpy as np
import pytest

from underwater_color import dicam
from underwater_color.correct import DEFAULT_VARIANTS, GENERATED_METHODS

WEB = Path(__file__).resolve().parent.parent / "web"
GLUE = WEB / "glue.py"


@pytest.fixture(scope="module")
def glue():
    spec = importlib.util.spec_from_file_location("glue", GLUE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_page_offers_every_method(glue):
    """A new method shows up on the page automatically. If one also has to
    be left out, UNAVAILABLE and this test should both say so."""
    names = [m["name"] for m in glue.menu()]
    assert set(names) == set(GENERATED_METHODS)
    assert len(names) == len(set(names))


def test_only_dicam_runs_as_a_model_and_its_model_is_committed(glue):
    """worker.js fetches the model relative to web/, and Pages serves the
    repo as committed: a missing file breaks dicam on the published page."""
    models = {m["name"]: m["model"] for m in glue.menu() if m["model"]}
    assert models == {"dicam": "dicam.onnx"}
    assert (WEB / "dicam.onnx").is_file()


def test_only_dicam_is_marked_approximate(glue):
    """The page's dicam runs at DICAM_WEB_LONGEST, not the library's
    WORK_LONGEST; every other method runs the library's own code."""
    marked = {m["name"] for m in glue.menu() if m["approximate"]}
    assert marked == {"dicam"}


def test_the_menu_leads_with_the_defaults_in_precedence_order(glue):
    menu = glue.menu()
    lead = [m["name"] for m in menu[:len(DEFAULT_VARIANTS)]]
    assert lead == list(DEFAULT_VARIANTS)


def test_every_method_links_to_a_committed_doc(glue):
    """The page links each tile to docs/methods/<name>.md on GitHub; a new
    method without a doc would link to a 404."""
    prefix = "https://github.com/fowles/underwater-color/blob/main/"
    root = WEB.parent
    for m in glue.menu():
        assert m["docs"].startswith(prefix)
        assert (root / m["docs"][len(prefix):]).is_file(), m["name"]


def test_correct_round_trips_canvas_rgba(glue):
    h, w = 24, 40
    rng = np.random.default_rng(0)
    rgba = rng.integers(0, 256, size=(h, w, 4), dtype=np.uint8)
    rgb = glue.rgb_from_rgba(memoryview(rgba.tobytes()), w, h)
    assert np.array_equal(rgb, rgba[..., :3])
    out = np.frombuffer(glue.correct("hue-shift", rgb), np.uint8).reshape(h, w, 4)
    assert np.array_equal(out[..., :3], GENERATED_METHODS["hue-shift"](rgba[..., :3]))
    assert (out[..., 3] == 255).all()


def test_dicam_glue_feeds_the_model_nchw_and_transfers_its_output(glue):
    """The worker runs the model between dicam_input/nchw and dicam_finish.
    A fake model that scales each channel differently, on a non-square
    image, catches an HWC/NCHW or height/width mix-up."""
    h, w = 30, 50
    rng = np.random.default_rng(1)
    rgb = rng.integers(1, 256, size=(h, w, 3), dtype=np.uint8)
    small = glue.dicam_input(rgb)
    sh, sw = small.shape[:2]
    gain = np.array([1.6, 0.9, 0.5], dtype=np.float32)
    model_in = np.frombuffer(glue.nchw(small), np.float32).reshape(1, 3, sh, sw)
    model_out = (model_in * gain[None, :, None, None]).astype(np.float32)
    out = np.frombuffer(glue.dicam_finish(rgb, small, model_out.tobytes()),
                        np.uint8).reshape(h, w, 4)
    expected = dicam.transfer(rgb, small, np.clip(small * gain, 0, 1))
    assert np.array_equal(out[..., :3], expected)
    assert (out[..., 3] == 255).all()


def test_dicam_runs_at_the_web_working_size(glue):
    rgb = np.zeros((600, 2000, 3), np.uint8)
    assert glue.dicam_input(rgb).shape == (154, glue.DICAM_WEB_LONGEST, 3)
    assert glue.DICAM_WEB_LONGEST <= dicam.WORK_LONGEST


def test_the_committed_model_was_exported_from_the_pinned_checkpoint():
    """Bumping CHECKPOINT_URL/SHA256 without rerunning web/export_dicam.py
    would leave the page running the old weights."""
    onnx = pytest.importorskip("onnx")
    model = onnx.load(WEB / "dicam.onnx", load_external_data=False)
    props = {p.key: p.value for p in model.metadata_props}
    assert props.get("checkpoint_sha256") == dicam.CHECKPOINT_SHA256


def test_export_matches_torch_at_a_size_other_than_the_trace(tmp_path):
    """export() leaves height and width dynamic, and the ONNX graph computes
    what the torch network does. Random weights keep this hermetic."""
    pytest.importorskip("onnxscript")
    ort = pytest.importorskip("onnxruntime")
    torch = pytest.importorskip("torch")
    spec = importlib.util.spec_from_file_location("export_dicam", WEB / "export_dicam.py")
    export_dicam = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(export_dicam)
    from underwater_color.vendor.dicam.network import build_default_network
    torch.manual_seed(0)
    net = build_default_network().eval()
    out = tmp_path / "m.onnx"
    export_dicam.export(net, out, "abc")
    x = torch.rand(1, 3, 37, 61)
    with torch.no_grad():
        expected = net(x).numpy()
    got = ort.InferenceSession(str(out)).run(None, {"input": x.numpy()})[0]
    assert np.allclose(got, expected, atol=1e-5)
