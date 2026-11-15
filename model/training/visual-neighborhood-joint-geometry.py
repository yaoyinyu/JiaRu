"""冻结视觉缓存，联合几何24张量与邻域40张量；输入不含真值。"""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import math
import torch


def _load(name, filename):
    spec = spec_from_file_location(name, Path(__file__).with_name(filename))
    value = module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


_geometry = _load('joint_geometry_cache', 'cached-geometry-training.py')
_sampler = _load('joint_geometry_sampler', 'visual-neighborhood-radial-refiner.py')
_capacity = _load('joint_geometry_capacity', 'visual-neighborhood-capacity-residual.py')


def enable_joint_geometry(model):
    """只开启既有几何和邻域参数；冻结视觉参数及其训练模式。"""
    model.requires_grad_(True)
    model.previous.base.requires_grad_(False).eval()
    trainable = [p for p in model.parameters() if p.requires_grad]
    if len(trainable) != 64:
        raise ValueError('expected existing40 plus geometry24 trainable tensors')
    return trainable


def neighborhood_features(model, strip, initial, coarse):
    """采样位置对几何半径保留梯度，值域/顺序沿用原缓存。"""
    if strip.ndim != 4 or strip.shape[1] != 5 or strip.shape[-1] != 129:
        raise ValueError('original five-channel radial strip required')
    if initial.shape != coarse.shape or initial.shape != (strip.shape[0], strip.shape[2]):
        raise ValueError('radius and original strip angles must align')
    local = _sampler.sample_neighborhood(strip, initial, coarse, model.offsets)
    theta = (torch.arange(strip.shape[2], device=strip.device, dtype=strip.dtype)+.5)*(2*math.pi/strip.shape[2])
    theta = theta[None].expand_as(coarse)
    geometry = torch.stack((initial/256, coarse/256, theta.sin(), theta.cos()), 1)
    return torch.cat((local, geometry), 1)


def forward_with_joint_geometry(model, geometry_cache, strip, coarse, angle_bins, distance):
    _, presence, initial = _geometry.forward(model.previous, geometry_cache, coarse, angle_bins, distance)
    features = neighborhood_features(model, strip, initial, coarse)
    return _capacity.forward_with_capacity(model,
        dict(features=features, initial=initial, presence=presence), coarse, angle_bins, distance)
