"""甲面硬真值边界增强损失。

该模块在 Ultralytics 原生实例 mask BCE 之上，增加由审核通过 polygon
栅格真值直接计算的形态学边界损失。它不生成或修正标签，也不改变检测框、
分类或 DFL 损失；其唯一目标是让预测 mask 的边缘更贴近完整可见甲面边沿。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import torch
import torch.nn.functional as F

from ultralytics.nn.tasks import SegmentationModel
from ultralytics.utils.loss import E2ELoss, v8SegmentationLoss
from ultralytics.utils.ops import crop_mask


@dataclass(frozen=True)
class HardBoundaryConfig:
    """训练前冻结并写入训练摘要的硬边界合同。"""

    contract_version: int = 1
    weight: float = 0.0
    kernel_size: int = 3


_CONFIG = HardBoundaryConfig()
_INSTALLED = False


def configure_hard_boundary_loss(config: HardBoundaryConfig) -> None:
    """校验并冻结当前进程的硬真值边界损失参数。"""

    global _CONFIG
    if config.weight < 0:
        raise ValueError("hard-boundary weight must be non-negative")
    if config.kernel_size < 3 or config.kernel_size % 2 == 0:
        raise ValueError("hard-boundary kernel size must be an odd integer >= 3")
    _CONFIG = config


def current_hard_boundary_contract() -> dict[str, object]:
    """返回用于预注册和训练摘要的稳定合同。"""

    return {
        **asdict(_CONFIG),
        "signal": "reviewed-polygon-morphological-boundary",
        "base_mask_loss": "ultralytics-instance-bce",
        "hard_polygon_truth_remains_authoritative": True,
        "classification_and_box_losses_unchanged": True,
    }


def morphological_boundary(mask: torch.Tensor, kernel_size: int) -> torch.Tensor:
    """以可微膨胀减腐蚀计算每个实例的形态学边界。"""

    padding = kernel_size // 2
    dilated = F.max_pool2d(mask, kernel_size, stride=1, padding=padding)
    eroded = -F.max_pool2d(-mask, kernel_size, stride=1, padding=padding)
    return (dilated - eroded).clamp_(0.0, 1.0)


class JiaRuHardBoundarySegmentationLoss(v8SegmentationLoss):
    """在原生实例 BCE 上叠加完整甲面硬真值边界误差。"""

    def __init__(self, model: torch.nn.Module, tal_topk: int = 10, tal_topk2: int | None = None):
        super().__init__(model, tal_topk, tal_topk2)
        self.hard_boundary_config = _CONFIG

    def single_mask_loss(
        self,
        gt_mask: torch.Tensor,
        pred: torch.Tensor,
        proto: torch.Tensor,
        xyxy: torch.Tensor,
        area: torch.Tensor,
    ) -> torch.Tensor:
        pred_mask = torch.einsum("in,nhw->ihw", pred, proto)
        pixel_bce = F.binary_cross_entropy_with_logits(pred_mask, gt_mask, reduction="none")
        base_loss = (crop_mask(pixel_bce, xyxy).mean(dim=(1, 2)) / area).sum()
        weight = self.hard_boundary_config.weight
        if weight == 0:
            return base_loss

        kernel = self.hard_boundary_config.kernel_size
        pred_boundary = morphological_boundary(pred_mask.sigmoid(), kernel)
        truth_boundary = morphological_boundary(gt_mask, kernel)
        # 在真值甲缘附近给足权重，同时保留少量全框监督以惩罚平行偏移的伪边缘。
        truth_band = F.max_pool2d(truth_boundary, kernel, stride=1, padding=kernel // 2)
        boundary_error = (pred_boundary - truth_boundary).abs() * (0.25 + truth_band)
        boundary_loss = (crop_mask(boundary_error, xyxy).mean(dim=(1, 2)) / area).sum()
        return base_loss + boundary_loss * weight


def install_hard_boundary_criterion() -> None:
    """把当前 Ultralytics 分割模型判据替换为边界增强版本。"""

    global _INSTALLED
    if _INSTALLED:
        return

    def init_criterion(model: SegmentationModel):
        if getattr(model, "end2end", False):
            return E2ELoss(model, JiaRuHardBoundarySegmentationLoss)
        return JiaRuHardBoundarySegmentationLoss(model)

    SegmentationModel.init_criterion = init_criterion
    _INSTALLED = True
