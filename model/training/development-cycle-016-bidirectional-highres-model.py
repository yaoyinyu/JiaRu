#!/usr/bin/env python3
"""循环016端到端双向多尺度ROI分割网络；仅供train内开发审计。"""

from __future__ import annotations

import torch
import torch.nn.functional as F
from torch import nn


class ResidualBlock(nn.Module):
    def __init__(self, channels: int) -> None:
        super().__init__()
        self.convs = nn.Sequential(
            nn.Conv2d(channels, channels, 3, padding=1, bias=False),
            nn.GroupNorm(8, channels),
            nn.GELU(),
            nn.Conv2d(channels, channels, 3, padding=1, bias=False),
            nn.GroupNorm(8, channels),
        )

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        return F.gelu(value + self.convs(value))


class ConvBlock(nn.Module):
    def __init__(self, input_channels: int, output_channels: int, *, stride: int = 1) -> None:
        super().__init__()
        self.layers = nn.Sequential(
            nn.Conv2d(input_channels, output_channels, 3, stride=stride, padding=1, bias=False),
            nn.GroupNorm(8, output_channels),
            nn.GELU(),
            nn.Conv2d(output_channels, output_channels, 3, padding=1, bias=False),
            nn.GroupNorm(8, output_channels),
            nn.GELU(),
        )

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        return self.layers(value)


class Dinov2BidirectionalHighResSegmenter(nn.Module):
    """DINO语义与384/192/96空间特征经两轮双向融合后逐像素输出。"""

    def __init__(self, backbone: nn.Module) -> None:
        super().__init__()
        self.backbone = backbone
        self.spatial384 = ConvBlock(3, 64)
        self.spatial192 = ConvBlock(64, 96, stride=2)
        self.spatial96 = ConvBlock(96, 128, stride=2)
        self.semantic96 = ConvBlock(384, 128)
        self.merge96 = ConvBlock(256, 128)
        self.top192_a = ConvBlock(128 + 96, 96)
        self.top384_a = ConvBlock(96 + 64, 64)
        self.down192 = ConvBlock(64 + 64, 96, stride=2)
        self.down96 = ConvBlock(96 + 96, 128, stride=2)
        self.top192_b = ConvBlock(128 + 96, 96)
        self.top384_b = ConvBlock(96 + 64, 64)
        self.boundary_tower = nn.Sequential(ResidualBlock(64), ResidualBlock(64))
        self.output = nn.Conv2d(64, 1, 1)

    def forward(self, pixel_values: torch.Tensor) -> torch.Tensor:
        spatial384 = self.spatial384(pixel_values)
        spatial192 = self.spatial192(spatial384)
        spatial96 = self.spatial96(spatial192)
        padded = F.pad(pixel_values, (4, 4, 4, 4), mode="replicate")
        tokens = self.backbone(
            pixel_values=padded,
            interpolate_pos_encoding=True,
            return_dict=False,
        )[0][:, 1:, :]
        semantic = tokens.transpose(1, 2).reshape(pixel_values.shape[0], 384, 28, 28)
        semantic96 = F.interpolate(self.semantic96(semantic), size=(96, 96), mode="bilinear", align_corners=False)
        fused96 = self.merge96(torch.cat((semantic96, spatial96), dim=1))
        fused192_a = self.top192_a(torch.cat((F.interpolate(fused96, size=(192, 192), mode="bilinear", align_corners=False), spatial192), dim=1))
        fused384_a = self.top384_a(torch.cat((F.interpolate(fused192_a, size=(384, 384), mode="bilinear", align_corners=False), spatial384), dim=1))
        fused192_b = self.down192(torch.cat((fused384_a, spatial384), dim=1)) + fused192_a
        fused96_b = self.down96(torch.cat((fused192_b, spatial192), dim=1)) + fused96
        fused192_c = self.top192_b(torch.cat((F.interpolate(fused96_b, size=(192, 192), mode="bilinear", align_corners=False), fused192_b), dim=1))
        fused384_b = self.top384_b(torch.cat((F.interpolate(fused192_c, size=(384, 384), mode="bilinear", align_corners=False), fused384_a), dim=1))
        return self.output(self.boundary_tower(fused384_b))
