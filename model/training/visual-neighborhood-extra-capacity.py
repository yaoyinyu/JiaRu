"""在完整已有径向模型上附加独立零初始化容量分支。"""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import torch
import torch.nn.functional as F

_spec = spec_from_file_location('extra_capacity_parent', Path(__file__).with_name('visual-neighborhood-capacity-residual.py'))
_parent = module_from_spec(_spec)
_spec.loader.exec_module(_parent)


def attach_extra_capacity(model, width=128):
    """构造新分支并恢复CPU RNG；已有权重及CUDA RNG保持原样。"""
    if hasattr(model, 'extra_capacity'):
        raise ValueError('extra capacity already attached')
    reference = model.project.weight
    with torch.random.fork_rng(devices=[]):
        branch = _parent.LocalCapacityResidual(width=width)
    model.extra_capacity = branch.to(device=reference.device, dtype=reference.dtype)
    return model


def forward_with_extra_capacity(model, cache, coarse, angle_bins, distance):
    value = model.project(cache['features'])
    for convolution, norm in zip(model.convs, model.norms, strict=True):
        dilation = convolution.dilation[0]
        indices = torch.arange(-dilation, value.shape[-1] + dilation, device=value.device).remainder(value.shape[-1])
        value = value + convolution(F.gelu(norm(value)).index_select(-1, indices))
    correction = model.head(F.gelu(value))[:, 0] + model.angle_context(cache['features'])
    correction = correction + model.extra_capacity(cache['features'])
    radius = torch.minimum(torch.maximum(cache['initial'] + correction, (coarse-64).clamp_min(0)), coarse+64)
    mask = (radius.gather(1, angle_bins.reshape(1, -1)).reshape_as(distance)-distance)[:, None]
    return mask, cache['presence'], radius
