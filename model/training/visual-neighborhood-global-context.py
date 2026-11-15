"""用整圈视觉/几何统计调制局部轮廓网络；零输出初始化保持原预测。"""
import torch
from torch import nn
import torch.nn.functional as F


class GlobalContext(nn.Module):
    def __init__(self, widths=(32, 64), hidden=64):
        super().__init__()
        self.widths = tuple(widths)
        self.encoder = nn.Linear(78, hidden)
        self.output = nn.Linear(hidden, 2 * sum(widths))
        nn.init.zeros_(self.output.weight)
        nn.init.zeros_(self.output.bias)

    def forward(self, features):
        if features.ndim != 3 or features.shape[1] != 39:
            raise ValueError('original39-channel angular features required')
        mean = features.mean(dim=-1)
        std = (features.var(dim=-1, unbiased=False) + 1e-6).sqrt()
        return self.output(F.gelu(self.encoder(torch.cat((mean, std), dim=1))))


def install(model):
    if hasattr(model, 'global_context'):
        raise ValueError('global context already installed')
    widths = (model.project.out_channels, model.angle_context.project.out_channels)
    model.global_context = GlobalContext(widths).to(model.project.weight)


def residual(block, features, conditioning, output_name):
    value = block.project(features)
    scale, bias = conditioning.chunk(2, dim=1)
    value = value + value * scale[:, :, None] + bias[:, :, None]
    for convolution, norm in zip(block.convs, block.norms, strict=True):
        dilation = convolution.dilation[0]
        indices = torch.arange(-dilation, value.shape[-1] + dilation, device=value.device).remainder(value.shape[-1])
        value = value + convolution(F.gelu(norm(value)).index_select(-1, indices))
    return getattr(block, output_name)(F.gelu(value))[:, 0]


def forward(model, cache, coarse, angle_bins, distance):
    features = cache['features']
    context = model.global_context(features)
    split = 2 * model.project.out_channels
    correction = residual(model, features, context[:, :split], 'head')
    correction = correction + residual(model.angle_context, features, context[:, split:], 'output')
    radius = torch.minimum(torch.maximum(cache['initial'] + correction, (coarse - 64).clamp_min(0)), coarse + 64)
    mask = (radius.gather(1, angle_bins.reshape(1, -1)).reshape_as(distance) - distance)[:, None]
    return mask, cache['presence'], radius
