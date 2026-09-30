# SPDX-License-Identifier: MIT
"""Export the DICAM network to web/dicam.onnx for the static page.

    uv run underwater-color init        # fetch the checkpoint, if absent
    uv run python web/export_dicam.py

torch has no Pyodide build, so the page runs this ONNX export under
onnxruntime-web instead. It is committed (GitHub Pages serves the repo as-is,
with no build step), and it records the sha256 of the checkpoint it was
exported from, so tests/test_web.py fails if the pinned checkpoint moves and
the export is not redone.
"""
from __future__ import annotations

from pathlib import Path

OUT = Path(__file__).resolve().parent / "dicam.onnx"
SHA_KEY = "checkpoint_sha256"


def export(net, out: Path, checkpoint_sha256: str) -> None:
    """Export ``net`` (a DICAM nn.Module) with dynamic height and width."""
    import onnx
    import torch
    dim = {2: torch.export.Dim("h", min=8, max=4096),
           3: torch.export.Dim("w", min=8, max=4096)}
    torch.onnx.export(
        net.cpu().eval(), (torch.rand(1, 3, 96, 128),), out,
        input_names=["input"], output_names=["output"],
        dynamic_shapes={"input": dim}, dynamo=True, external_data=False)
    model = onnx.load(out)
    onnx.helper.set_model_props(model, {SHA_KEY: checkpoint_sha256})
    onnx.save(model, out)


def main() -> None:
    from underwater_color import dicam
    export(dicam._build_and_load(), OUT, dicam.CHECKPOINT_SHA256)
    print(f"wrote {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
