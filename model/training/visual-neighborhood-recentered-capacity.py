"""新增容量分支沿本次基座预测轮廓读取条带，采样中心不接收真值。"""
import math
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import torch
import torch.nn.functional as F


def _load(name, filename):
    spec = spec_from_file_location(name, Path(__file__).with_name(filename))
    value = module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


_extra = _load('recentered_capacity_parent', 'visual-neighborhood-extra-capacity.py')
_sampler = _load('recentered_capacity_sampler', 'visual-neighborhood-radial-refiner.py')
attach_extra_capacity = _extra.attach_extra_capacity


@torch.no_grad()
def recentered_features(strip, center, coarse):
    if strip.ndim != 4 or strip.shape[1] != 5 or center.shape != coarse.shape or strip.shape[2] != center.shape[1]:
        raise ValueError('aligned five-channel strip and per-angle radii required')
    local = _sampler.sample_neighborhood(strip, center, coarse, _sampler.VisualNeighborhoodRadialRefiner.offsets)
    theta = (torch.arange(strip.shape[2], device=strip.device, dtype=strip.dtype)+.5)*(2*math.pi/strip.shape[2])
    theta = theta[None].expand_as(coarse)
    geometry = torch.stack((center/256, coarse/256, theta.sin(), theta.cos()), 1)
    return torch.cat((local, geometry), 1)


def forward_with_recentered_capacity(model, cache, coarse, angle_bins, distance):
    value = model.project(cache['features'])
    for convolution, norm in zip(model.convs, model.norms, strict=True):
        dilation = convolution.dilation[0]
        indices = torch.arange(-dilation, value.shape[-1]+dilation, device=value.device).remainder(value.shape[-1])
        value = value+convolution(F.gelu(norm(value)).index_select(-1, indices))
    correction = model.head(F.gelu(value))[:, 0]+model.angle_context(cache['features'])
    center = torch.minimum(torch.maximum(cache['initial']+correction, (coarse-64).clamp_min(0)), coarse+64)
    # 中心随基座预测变化，采样选择本身停止梯度；原基座仍经最终半径直接获得梯度。
    features = recentered_features(cache['strip'], center.detach(), coarse)
    correction = correction+model.extra_capacity(features)
    radius = torch.minimum(torch.maximum(cache['initial']+correction, (coarse-64).clamp_min(0)), coarse+64)
    mask = (radius.gather(1, angle_bins.reshape(1, -1)).reshape_as(distance)-distance)[:, None]
    return mask, cache['presence'], radius
