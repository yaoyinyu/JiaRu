"""同候选粗mask条件的逐甲高分辨率精修；不修改历史RGB网络与权重。"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import torch
from torch import nn
import torch.nn.functional as F


def load_local(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    if spec is None or spec.loader is None:
        raise RuntimeError(filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


base = load_local("conditional_rgb_architecture", "development-cycle-016-bidirectional-highres-model.py")
boundary = load_local("conditional_boundary_loss", "development-cycle-016-soft-boundary-iou.py")


class ConditionalNailRefiner(base.Dinov2BidirectionalHighResSegmenter):
    """输入N×4×384×384；前三通道归一化RGB，第四通道同候选0/1粗mask。"""

    def __init__(self, backbone: nn.Module) -> None:
        super().__init__(backbone)
        self.spatial384 = base.ConvBlock(4, 64)

    def forward(self, candidate_input: torch.Tensor) -> torch.Tensor:
        spatial384 = self.spatial384(candidate_input)
        spatial192 = self.spatial192(spatial384)
        spatial96 = self.spatial96(spatial192)
        # 预训练语义骨干的三通道合同不变；条件信号经空间分支进入融合网络。
        padded = F.pad(candidate_input[:, :3], (4, 4, 4, 4), mode="replicate")
        tokens = self.backbone(pixel_values=padded, interpolate_pos_encoding=True, return_dict=False)[0][:, 1:, :]
        semantic = tokens.transpose(1, 2).reshape(candidate_input.shape[0], 384, 28, 28)
        semantic96 = F.interpolate(self.semantic96(semantic), size=(96, 96), mode="bilinear", align_corners=False)
        fused96 = self.merge96(torch.cat((semantic96, spatial96), dim=1))
        fused192_a = self.top192_a(torch.cat((F.interpolate(fused96, size=(192, 192), mode="bilinear", align_corners=False), spatial192), dim=1))
        fused384_a = self.top384_a(torch.cat((F.interpolate(fused192_a, size=(384, 384), mode="bilinear", align_corners=False), spatial384), dim=1))
        fused192_b = self.down192(torch.cat((fused384_a, spatial384), dim=1)) + fused192_a
        fused96_b = self.down96(torch.cat((fused192_b, spatial192), dim=1)) + fused96
        fused192_c = self.top192_b(torch.cat((F.interpolate(fused96_b, size=(192, 192), mode="bilinear", align_corners=False), fused192_b), dim=1))
        fused384_b = self.top384_b(torch.cat((F.interpolate(fused192_c, size=(384, 384), mode="bilinear", align_corners=False), fused384_a), dim=1))
        return self.output(self.boundary_tower(fused384_b))


def conditional_mask_loss(logits: torch.Tensor, truth: torch.Tensor, *, boundary_weight: float = 0.2):
    """每候选BCE；Dice/边界只对非空目标计算，空目标仍有逐像素拒识梯度。

    边界损失是384栅格可微代理；验收必须在映回原图后使用2原像素指标。
    不将空目标的未定义Boundary IoU当作通过或加入正甲均值。
    """
    logits, truth = logits.float(), truth.float()
    dims = (1, 2, 3)
    positive = (truth.sum(dim=dims) > 0).float()
    count = positive.sum().clamp_min(1)
    probability = logits.sigmoid()
    bce = F.binary_cross_entropy_with_logits(logits, truth, reduction="none").mean()
    intersection = (probability * truth).sum(dim=dims)
    dice_per = 1 - (2 * intersection + 1) / (probability.sum(dim=dims) + truth.sum(dim=dims) + 1)
    boundary_per = 1 - boundary.soft_boundary_iou_per_instance(probability, truth, {"nearBoundaryKernel": 5, "epsilon": 1e-6})
    dice = (dice_per * positive).sum() / count
    edge = (boundary_per * positive).sum() / count
    total = bce + dice + boundary_weight * edge
    return total, {"bce": float(bce.detach()), "positiveDice": float(dice.detach()), "positiveBoundaryProxy": float(edge.detach()), "positiveCount": int(positive.sum().item()), "emptyCount": int((1-positive).sum().item())}
