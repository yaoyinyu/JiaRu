"""冻结视觉基线的训练缓存；保持现行几何分支运算和部署权重布局。"""
import math
import torch
import torch.nn.functional as F


@torch.no_grad()
def extract(model, strip, coarse_radii, angle_bins, distance):
    _, presence, initial = model.base.forward_with_radius(strip, coarse_radii, angle_bins, distance)
    local = model.base.local.features(strip)
    offset = initial - coarse_radii
    location = (offset + 64).clamp(0, 128)
    lower = location.floor().to(torch.int64)
    upper = (lower + 1).clamp_max(128)
    weight = (location - lower.to(location.dtype))[:, None]
    left = local.gather(-1, lower[:, None, :, None].expand(-1, 16, -1, 1)).squeeze(-1)
    right = local.gather(-1, upper[:, None, :, None].expand(-1, 16, -1, 1)).squeeze(-1)
    edge = left * (1 - weight) + right * weight
    theta = ((torch.arange(strip.shape[2], device=strip.device, dtype=strip.dtype) + .5)
             * (2 * math.pi / strip.shape[2]))[None]
    before = torch.roll(coarse_radii, 1, -1)
    after = torch.roll(coarse_radii, -1, -1)
    geometry = torch.stack((coarse_radii / 256, initial / 256, offset / 64,
                            (after - before) / 32,
                            (after + before - 2 * coarse_radii) / 32,
                            theta.sin(), theta.cos()), dim=1)
    return dict(features=torch.cat((edge, geometry), dim=1), initial=initial, presence=presence)


def forward(model, cache, coarse_radii, angle_bins, distance):
    residual = model.head(F.gelu(model.blocks(model.project(cache['features']))))[:, 0]
    radius = torch.minimum(torch.maximum(cache['initial'] + residual, (coarse_radii - 64).clamp_min(0)),
                           coarse_radii + 64)
    native = radius.gather(1, angle_bins.reshape(1, -1)).reshape_as(distance) - distance
    return native[:, None], cache['presence'], radius
