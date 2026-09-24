#!/usr/bin/env python3
"""循环016严格内边界带IoU的可微代理；只替换训练期边界项。"""

from __future__ import annotations

from typing import Any

import torch
import torch.nn.functional as F


def inner_boundary_band(value: torch.Tensor, *, near_kernel: int = 5) -> torch.Tensor:
    """与正式Boundary IoU的3×3内边缘、5×5邻域及甲面内带同构。"""
    value = value.float()
    eroded = -F.max_pool2d(-value, kernel_size=3, stride=1, padding=1)
    inner_edge = torch.clamp(value - eroded, min=0.0, max=1.0)
    near_edge = F.max_pool2d(inner_edge, kernel_size=near_kernel, stride=1, padding=near_kernel // 2)
    return value * near_edge


def soft_boundary_iou_per_instance(probability: torch.Tensor, truth: torch.Tensor, config: dict[str, Any]) -> torch.Tensor:
    predicted_band = inner_boundary_band(probability, near_kernel=int(config["nearBoundaryKernel"]))
    truth_band = inner_boundary_band(truth, near_kernel=int(config["nearBoundaryKernel"]))
    dimensions = (1, 2, 3)
    intersection = (predicted_band * truth_band).sum(dim=dimensions)
    union = (predicted_band + truth_band - predicted_band * truth_band).sum(dim=dimensions)
    epsilon = float(config["epsilon"])
    return (intersection + epsilon) / (union + epsilon)


def soft_boundary_iou_loss(logits: torch.Tensor, truth: torch.Tensor, config: dict[str, Any]) -> tuple[torch.Tensor, dict[str, float]]:
    logits_fp32 = logits.float()
    truth_fp32 = truth.float()
    bce = F.binary_cross_entropy_with_logits(logits_fp32, truth_fp32)
    probability = torch.sigmoid(logits_fp32)
    dimensions = (1, 2, 3)
    intersection = (probability * truth_fp32).sum(dim=dimensions)
    dice = 1.0 - ((2.0 * intersection + 1.0) / (probability.sum(dim=dimensions) + truth_fp32.sum(dim=dimensions) + 1.0)).mean()
    boundary = 1.0 - soft_boundary_iou_per_instance(probability, truth_fp32, config).mean()
    total = bce + dice + float(config["boundaryWeight"]) * boundary
    return total, {"bce": float(bce.detach()), "dice": float(dice.detach()), "softBoundaryIouLoss": float(boundary.detach())}
