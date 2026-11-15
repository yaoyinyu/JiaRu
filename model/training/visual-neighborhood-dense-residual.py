"""原39通道保持原序，增加四个原像素径向位置的独立零初始化投影。"""
import torch
from torch import nn
import torch.nn.functional as F

EXTRA_OFFSETS = (-3., -1., 1., 3.)
EXTRA_KEYS = ('dense_project.weight', 'angle_context.dense_project.weight')


def install(model):
    """已加载原权重后安装；旧卷积形状和运算顺序保持。"""
    for block in (model, model.angle_context):
        if hasattr(block, 'dense_project'):
            raise ValueError('dense projection already installed')
        reference = block.project.weight
        block.dense_project = nn.Conv1d(20, block.project.out_channels, 1, bias=False).to(reference)
        nn.init.zeros_(block.dense_project.weight)


def residual(block, features, extra, output_name):
    value = block.project(features) + block.dense_project(extra)
    for convolution, norm in zip(block.convs, block.norms, strict=True):
        dilation = convolution.dilation[0]
        indices = torch.arange(-dilation, value.shape[-1] + dilation, device=value.device).remainder(value.shape[-1])
        value = value + convolution(F.gelu(norm(value)).index_select(-1, indices))
    return getattr(block, output_name)(F.gelu(value))[:, 0]


def forward(model, cache, coarse, angle_bins, distance):
    features, extra = cache['features'], cache['denseFeatures']
    if features.shape[1] != 39 or extra.shape[1] != 20 or features.shape[::2] != extra.shape[::2]:
        raise ValueError('aligned original39 and extra20 channels required')
    correction = residual(model, features, extra, 'head') + residual(model.angle_context, features, extra, 'output')
    radius = torch.minimum(torch.maximum(cache['initial'] + correction, (coarse - 64).clamp_min(0)), coarse + 64)
    mask = (radius.gather(1, angle_bins.reshape(1, -1)).reshape_as(distance) - distance)[:, None]
    return mask, cache['presence'], radius
