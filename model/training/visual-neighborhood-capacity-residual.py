"""在原邻域特征上增加可零初始化的局部容量分支。"""
import torch
from torch import nn
import torch.nn.functional as F


class LocalCapacityResidual(nn.Module):
    """只消费现行39通道视觉/几何缓存；零输出保留原半径。"""
    def __init__(self, width=64):
        super().__init__()
        if width < 8 or width % 8:
            raise ValueError('width must be a positive multiple of eight')
        self.project = nn.Conv1d(39, width, 1)
        self.convs = nn.ModuleList(nn.Conv1d(width, width, 3, dilation=d) for d in (1, 2, 4, 8))
        self.norms = nn.ModuleList(nn.GroupNorm(width // 8, width) for _ in self.convs)
        self.output = nn.Conv1d(width, 1, 1)
        nn.init.zeros_(self.output.weight)
        nn.init.zeros_(self.output.bias)

    def forward(self, features):
        value = self.project(features)
        for convolution, norm in zip(self.convs, self.norms, strict=True):
            dilation = convolution.dilation[0]
            indices = torch.arange(-dilation, value.shape[-1] + dilation, device=value.device).remainder(value.shape[-1])
            value = value + convolution(F.gelu(norm(value)).index_select(-1, indices))
        return self.output(F.gelu(value))[:, 0]


def forward_with_capacity(model, cache, coarse, angle_bins, distance):
    value = model.project(cache['features'])
    for convolution, norm in zip(model.convs, model.norms, strict=True):
        dilation = convolution.dilation[0]
        indices = torch.arange(-dilation, value.shape[-1] + dilation, device=value.device).remainder(value.shape[-1])
        value = value + convolution(F.gelu(norm(value)).index_select(-1, indices))
    correction = model.head(F.gelu(value))[:, 0] + model.angle_context(cache['features'])
    radius = torch.minimum(torch.maximum(cache['initial'] + correction, (coarse - 64).clamp_min(0)), coarse + 64)
    mask = (radius.gather(1, angle_bins.reshape(1, -1)).reshape_as(distance) - distance)[:, None]
    return mask, cache['presence'], radius
