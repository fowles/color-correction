# SPDX-License-Identifier: MIT
import pytest

torch = pytest.importorskip("torch")


def test_vendored_network_forward_shape():
    from underwater_color.vendor.dicam.network import build_default_network  # adapter added in Step 4
    net = build_default_network().eval()
    x = torch.rand(1, 3, 64, 64)
    with torch.no_grad():
        y = net(x)
    # if the network requires a specific divisible size, use that here instead of 64
    assert y.shape == (1, 3, 64, 64)
