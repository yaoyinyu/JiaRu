"""周期角度、多尺度径向内容与全域注意力精修；保持原尺寸两头接口。"""
import importlib.util
from pathlib import Path
import math
import torch
from torch import nn
import torch.nn.functional as F

_spec = importlib.util.spec_from_file_location(
    'context_radial_local', Path(__file__).with_name('native-radial-strip-refiner.py'))
_local = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_local)


def periodic_resize(value, size):
    """径向线性插值，角度按像素中心周期插值，跨接缝不复制边缘。"""
    angles, radial = size
    value = F.interpolate(value, size=(value.shape[2], radial), mode='bilinear', align_corners=False)
    position = ((torch.arange(angles, device=value.device, dtype=torch.float32) + .5)
                * (value.shape[2] / angles) - .5)
    lower = position.floor().to(torch.int64)
    weight = (position - lower.to(torch.float32))[None, None, :, None]
    left = value.index_select(2, lower.remainder(value.shape[2]))
    right = value.index_select(2, (lower + 1).remainder(value.shape[2]))
    return left * (1 - weight) + right * weight


class GlobalContentAttention(nn.Module):
    def __init__(self, channels=64, heads=4):
        super().__init__()
        self.heads = heads
        self.norm = nn.LayerNorm(channels)
        self.qkv = nn.Linear(channels, channels * 3)
        self.output = nn.Linear(channels, channels)

    def forward(self, value):
        batch, channels, angles, radial = value.shape
        tokens = value.flatten(2).transpose(1, 2)
        qkv = self.qkv(self.norm(tokens)).reshape(
            batch, angles * radial, 3, self.heads, channels // self.heads)
        q, k, v = qkv.permute(2, 0, 3, 1, 4).unbind(0)
        weights = ((q @ k.transpose(-2, -1)) / math.sqrt(channels // self.heads)).softmax(-1)
        mixed = (weights @ v).transpose(1, 2).reshape(batch, angles * radial, channels)
        return (tokens + self.output(mixed)).transpose(1, 2).reshape_as(value)


def _block(incoming, outgoing):
    return nn.Sequential(_local.AngularConv(incoming, outgoing),
                         _local.AngularConv(outgoing, outgoing))


class NativeContextRadialRefiner(nn.Module):
    """局部训练权重与新增零残差分支共训，输入不含真值或图片身份。"""
    def __init__(self):
        super().__init__()
        self.local = _local.NativeRadialStripRefiner()
        widths = (16, 24, 32, 48, 64)
        self.encoder = nn.ModuleList(_block(5 if i == 0 else widths[i-1], width)
                                     for i, width in enumerate(widths))
        self.attention = GlobalContentAttention(64, 4)
        self.decoder = nn.ModuleList(_block(widths[i+1] + widths[i], widths[i])
                                     for i in range(3, -1, -1))
        self.context_score = nn.Conv2d(16, 1, 1)
        self.context_presence = nn.Linear(64, 1)
        for head in (self.context_score, self.context_presence):
            nn.init.zeros_(head.weight)
            nn.init.zeros_(head.bias)

    def forward(self, strip, coarse_radii, angle_bins, distance):
        mask, presence, _ = self.forward_with_radius(strip, coarse_radii, angle_bins, distance)
        return mask, presence

    def forward_with_radius(self, strip, coarse_radii, angle_bins, distance):
        if strip.ndim != 4 or strip.shape[0] != 1 or strip.shape[1] != 5 or strip.shape[3] != 129:
            raise ValueError('batch1 original-coordinate 5-channel radial strip required')
        if (coarse_radii.shape != (1, strip.shape[2]) or angle_bins.shape != distance.shape
                or angle_bins.ndim != 3 or angle_bins.shape[0] != 1):
            raise ValueError('full candidate radial metadata required')
        features = self.local.features(strip)
        score = self.local.score(features)[:, 0]
        value = F.avg_pool2d(strip, (4, 2), ceil_mode=True, count_include_pad=False)
        skips = []
        for index, encoder in enumerate(self.encoder):
            if index:
                value = F.avg_pool2d(value, 2, ceil_mode=True, count_include_pad=False)
            value = encoder(value)
            skips.append(value)
        value = self.attention(value)
        content = value.mean((2, 3))
        for decoder, skip in zip(self.decoder, reversed(skips[:-1]), strict=True):
            value = decoder(torch.cat((periodic_resize(value, skip.shape[2:]), skip), dim=1))
        score = score + periodic_resize(self.context_score(value), strip.shape[2:])[:, 0]
        probability = F.softmax(score + self.local.prior, dim=-1)
        initial = F.softmax(torch.zeros_like(score) + self.local.prior, dim=-1)
        offset = ((probability - initial) * self.local.offsets).sum(-1).clamp(-64, 64)
        radius = (coarse_radii + offset).clamp_min(0)
        native = radius.gather(1, angle_bins.reshape(1, -1)).reshape_as(distance) - distance
        presence = self.local.presence(features.mean((2, 3))) + self.context_presence(content)
        return native[:, None], presence, radius
