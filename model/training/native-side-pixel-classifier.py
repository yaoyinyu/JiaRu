"""Native-resolution auxiliary classifier for a fixed, editable side band."""

import torch
from torch import nn
from torch.nn import functional as F

BAND_PX = 8
CONTEXT_RADIUS_PX = 23


def pack_input(rgb, original, distance, editable, *, use_rgb):
    """Make aligned RGB, signed distance, and editable-band channels."""
    if rgb.ndim != 4 or rgb.shape[1] != 3:
        raise ValueError("expected NCHW RGB")
    shape = (rgb.shape[0], 1, *rgb.shape[-2:])
    if any(tensor.shape != shape for tensor in (original, distance, editable)):
        raise ValueError("RGB, mask, distance, and band must share native pixel coordinates")
    if rgb.dtype != torch.uint8 or original.dtype != torch.bool or editable.dtype != torch.bool:
        raise ValueError("expected uint8 RGB and boolean masks")
    if not torch.is_floating_point(distance) or not bool(torch.isfinite(distance).all()) or bool((distance < 0).any()):
        raise ValueError("expected finite unsigned boundary distance")
    distance = (distance.float().clamp(max=BAND_PX) + 1) / (BAND_PX + 1)
    signed = torch.where(original, distance, -distance)
    rgb = rgb.float().div(127.5).sub(1) if use_rgb else torch.zeros_like(rgb, dtype=torch.float32)
    return torch.cat((rgb, signed, editable.to(dtype=torch.float32)), dim=1)


class NativeSidePixelClassifier(nn.Module):
    def __init__(self):
        super().__init__()
        channels = 16
        self.stem = nn.Conv2d(5, channels, 3, padding=1)
        self.layers = nn.ModuleList([
            nn.Sequential(
                nn.Conv2d(channels, channels, 3, padding=dilation, dilation=dilation, groups=channels),
                nn.Conv2d(channels, channels, 1),
                nn.SiLU(),
            )
            for dilation in (1, 3, 7, 11)
        ])
        self.projection = nn.Conv2d(channels, 1, 1)
        nn.init.zeros_(self.projection.weight)
        nn.init.zeros_(self.projection.bias)

    def forward(self, packed):
        if packed.ndim != 4 or packed.shape[1] != 5:
            raise ValueError("expected five aligned input channels")
        features = F.silu(self.stem(packed))
        for layer in self.layers:
            features = features + layer(features)
        return packed[:, 3:4] + self.projection(features)


def side_pixel_loss(logits, truth, editable):
    """Normalize each nail independently and backpropagate within its band."""
    if logits.ndim != 4 or logits.shape[1] != 1 or truth.shape != logits.shape or editable.shape != logits.shape:
        raise ValueError("expected shape-matched N1HW tensors")
    if truth.dtype != torch.bool or editable.dtype != torch.bool:
        raise ValueError("expected boolean truth and editable masks")
    counts = editable.sum(dim=(1, 2, 3))
    if bool((counts == 0).any()):
        raise ValueError("empty eligible band")
    errors = F.binary_cross_entropy_with_logits(logits, truth.to(dtype=logits.dtype), reduction="none")
    eligible = torch.where(editable, errors, 0)
    return (eligible.sum(dim=(1, 2, 3)) / counts).mean()
