"""冻结视觉基线，用原坐标轮廓和边缘内容直接回归半径残差。"""
import importlib.util
import math
from pathlib import Path

import torch
from torch import nn
import torch.nn.functional as F

_spec = importlib.util.spec_from_file_location(
    'geometry_context_base', Path(__file__).with_name('native-context-radial-refiner.py'))
_context = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_context)


class CircularResidual(nn.Module):
    def __init__(self, width, dilation):
        super().__init__()
        self.dilation = dilation
        self.norm = nn.GroupNorm(4, width)
        self.conv = nn.Conv1d(width, width, 3, dilation=dilation)

    def forward(self, value):
        # 索引取模也支持角度数小于膨胀宽度的独立控制。
        indices = torch.arange(-self.dilation, value.shape[-1] + self.dilation,
                               device=value.device).remainder(value.shape[-1])
        padded = F.gelu(self.norm(value)).index_select(-1, indices)
        return value + self.conv(padded)


class NativeGeometryRadialRefiner(nn.Module):
    """推理只读图像、候选粗轮廓和坐标；视觉基线参数保持冻结。"""
    def __init__(self, base=None):
        super().__init__()
        self.base = base if base is not None else _context.NativeContextRadialRefiner()
        self.base.requires_grad_(False)
        self.base.eval()
        self.project = nn.Conv1d(23, 32, 1)
        self.blocks = nn.Sequential(*(CircularResidual(32, d) for d in (1, 4, 16, 64, 256)))
        self.head = nn.Conv1d(32, 1, 1)
        nn.init.zeros_(self.head.weight)
        nn.init.zeros_(self.head.bias)

    def train(self, mode=True):
        super().train(mode)
        self.base.eval()
        return self

    def forward(self, strip, coarse_radii, angle_bins, distance):
        mask, presence, _ = self.forward_with_radius(strip, coarse_radii, angle_bins, distance)
        return mask, presence

    def forward_with_radius(self, strip, coarse_radii, angle_bins, distance):
        with torch.no_grad():
            _, presence, initial = self.base.forward_with_radius(
                strip, coarse_radii, angle_bins, distance)
            local = self.base.local.features(strip)
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
        residual = self.head(F.gelu(self.blocks(self.project(torch.cat((edge, geometry), dim=1)))))[:, 0]
        radius = torch.minimum(torch.maximum(initial + residual, (coarse_radii - 64).clamp_min(0)),
                               coarse_radii + 64)
        native = radius.gather(1, angle_bins.reshape(1, -1)).reshape_as(distance) - distance
        return native[:, None], presence, radius
