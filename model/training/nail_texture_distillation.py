"""甲面实例分割的多信号教师—学生蒸馏。

Ultralytics原生蒸馏只把教师置信度用于多尺度特征L2。本模块保留该项，
并在相同YOLO分割头网格上增加分类软概率、框分布、逐锚软mask与边界梯度。
教师始终冻结；硬polygon真值仍由学生原生损失负责，蒸馏信号不能替代真值。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import torch
import torch.nn.functional as F

from ultralytics.nn.distill_model import DistillationModel
from ultralytics.nn.modules.head import Segment


@dataclass(frozen=True)
class DistillationConfig:
    """训练时固定并写入证据的蒸馏超参数。"""

    contract_version: int = 1
    temperature: float = 2.0
    feature_weight: float = 1.0
    soft_score_weight: float = 0.25
    box_distribution_weight: float = 0.25
    soft_mask_weight: float = 0.50
    boundary_weight: float = 0.25
    topk_anchors: int = 24


_CONFIG = DistillationConfig()


def configure_distillation(config: DistillationConfig) -> None:
    """在Trainer构建包装模型前设置一次本进程蒸馏合同。"""

    global _CONFIG
    if config.temperature <= 0:
        raise ValueError("distillation temperature must be positive")
    if config.topk_anchors <= 0:
        raise ValueError("distillation top-k anchors must be positive")
    weights = (
        config.feature_weight,
        config.soft_score_weight,
        config.box_distribution_weight,
        config.soft_mask_weight,
        config.boundary_weight,
    )
    if any(weight < 0 for weight in weights) or not any(weight > 0 for weight in weights):
        raise ValueError("distillation weights must be non-negative with at least one positive value")
    _CONFIG = config


def current_distillation_contract() -> dict[str, object]:
    """返回可序列化的固定训练合同。"""

    return {
        **asdict(_CONFIG),
        "signals": [
            "teacher-score-weighted-neck-features",
            "bernoulli-soft-class-probabilities",
            "distribution-focal-box-logits",
            "anchor-aligned-soft-instance-masks",
            "soft-mask-boundary-gradients",
        ],
        "hard_truth_remains_authoritative": True,
    }


class JiaRuSegmentationDistillationModel(DistillationModel):
    """适配同网格YOLO分割教师与学生的多信号蒸馏包装器。"""

    def __init__(self, teacher_model, student_model):
        super().__init__(teacher_model=teacher_model, student_model=student_model)
        self.distillation_config = _CONFIG
        student_head = self.student_model.model[-1]
        teacher_head = self.teacher_model.model[-1]
        if not isinstance(student_head, Segment) or not isinstance(teacher_head, Segment):
            raise ValueError("multi-signal nail distillation requires Segment teacher and student heads")
        if student_head.nc != teacher_head.nc:
            raise ValueError("teacher and student class counts differ")
        if student_head.reg_max != teacher_head.reg_max:
            raise ValueError("teacher and student box-distribution widths differ")
        if student_head.nm != teacher_head.nm:
            raise ValueError("teacher and student mask coefficient widths differ")
        if self.get_distill_layers(self.student_model) != self.get_distill_layers(self.teacher_model):
            raise ValueError("teacher and student feature pyramid layer identities differ")

    @staticmethod
    def _prediction_branch(head_output, branch: str = "one2many") -> dict[str, torch.Tensor]:
        if isinstance(head_output, tuple):
            head_output = head_output[1]
        if isinstance(head_output, dict) and branch in head_output:
            head_output = head_output[branch]
        if not isinstance(head_output, dict):
            raise ValueError("distillation head output is not a prediction dictionary")
        required = {"boxes", "scores", "mask_coefficient", "proto"}
        missing = required - set(head_output)
        if missing:
            raise ValueError(f"distillation head output is missing: {sorted(missing)}")
        return head_output

    @staticmethod
    def _topk_indices(scores: torch.Tensor, topk: int) -> tuple[torch.Tensor, torch.Tensor]:
        confidence = scores.sigmoid().amax(dim=1)
        count = min(topk, confidence.shape[-1])
        return torch.topk(confidence, k=count, dim=-1, sorted=False)

    @staticmethod
    def _gather_last(values: torch.Tensor, indices: torch.Tensor) -> torch.Tensor:
        expanded = indices[:, None, :].expand(values.shape[0], values.shape[1], indices.shape[1])
        return values.gather(-1, expanded)

    def _soft_score_loss(self, student: dict[str, torch.Tensor], teacher: dict[str, torch.Tensor]) -> torch.Tensor:
        temperature = self.distillation_config.temperature
        teacher_probability = (teacher["scores"].detach() / temperature).sigmoid()
        # 保留少量背景权重，同时避免数万负锚淹没教师前景信号。
        weight = 0.05 + 0.95 * teacher_probability
        loss = F.binary_cross_entropy_with_logits(
            student["scores"] / temperature,
            teacher_probability,
            reduction="none",
        )
        return (loss * weight).sum() / (weight.sum() + 1e-9) * temperature**2

    def _box_distribution_loss(
        self,
        student: dict[str, torch.Tensor],
        teacher: dict[str, torch.Tensor],
        indices: torch.Tensor,
        confidence: torch.Tensor,
    ) -> torch.Tensor:
        temperature = self.distillation_config.temperature
        student_boxes = self._gather_last(student["boxes"], indices)
        teacher_boxes = self._gather_last(teacher["boxes"].detach(), indices)
        reg_max = student_boxes.shape[1] // 4
        student_boxes = student_boxes.view(student_boxes.shape[0], 4, reg_max, -1)
        teacher_boxes = teacher_boxes.view(teacher_boxes.shape[0], 4, reg_max, -1)
        divergence = F.kl_div(
            F.log_softmax(student_boxes / temperature, dim=2),
            F.softmax(teacher_boxes / temperature, dim=2),
            reduction="none",
        ).sum(dim=2)
        weight = confidence[:, None, :]
        return (divergence * weight).sum() / (weight.sum() * 4 + 1e-9) * temperature**2

    def _soft_mask_losses(
        self,
        student: dict[str, torch.Tensor],
        teacher: dict[str, torch.Tensor],
        indices: torch.Tensor,
        confidence: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        temperature = self.distillation_config.temperature
        student_coeff = self._gather_last(student["mask_coefficient"], indices).transpose(1, 2)
        teacher_coeff = self._gather_last(teacher["mask_coefficient"].detach(), indices).transpose(1, 2)
        student_proto = student["proto"]
        teacher_proto = teacher["proto"].detach()
        if student_proto.shape[-2:] != teacher_proto.shape[-2:]:
            teacher_proto = F.interpolate(
                teacher_proto,
                size=student_proto.shape[-2:],
                mode="bilinear",
                align_corners=False,
            )
        student_masks = torch.einsum("bkc,bchw->bkhw", student_coeff, student_proto)
        teacher_masks = torch.einsum("bkc,bchw->bkhw", teacher_coeff, teacher_proto)
        teacher_probability = (teacher_masks / temperature).sigmoid()
        anchor_weight = confidence[:, :, None, None]
        mask_loss = F.binary_cross_entropy_with_logits(
            student_masks / temperature,
            teacher_probability,
            reduction="none",
        )
        mask_loss = (mask_loss * anchor_weight).sum() / (
            anchor_weight.sum() * teacher_probability.shape[-2] * teacher_probability.shape[-1] + 1e-9
        ) * temperature**2

        student_probability = (student_masks / temperature).sigmoid()
        student_dx = student_probability[..., :, 1:] - student_probability[..., :, :-1]
        teacher_dx = teacher_probability[..., :, 1:] - teacher_probability[..., :, :-1]
        student_dy = student_probability[..., 1:, :] - student_probability[..., :-1, :]
        teacher_dy = teacher_probability[..., 1:, :] - teacher_probability[..., :-1, :]
        weight_x = anchor_weight.expand_as(student_dx)
        weight_y = anchor_weight.expand_as(student_dy)
        boundary_loss = (
            (student_dx - teacher_dx).abs().mul(weight_x).sum()
            + (student_dy - teacher_dy).abs().mul(weight_y).sum()
        ) / (weight_x.sum() + weight_y.sum() + 1e-9)
        return mask_loss, boundary_loss

    def loss(self, batch, preds=None):
        """返回原生硬真值损失与一个汇总蒸馏损失。"""

        zero = torch.zeros(1, device=batch["img"].device)
        if not self.training:
            if preds is None:
                preds = self.student_model(batch["img"])
            regular_loss, regular_detached = self.student_model.loss(batch, preds)
            return torch.cat([regular_loss, zero]), torch.cat([regular_detached, zero])

        self._teacher_feats.clear()
        self._student_feats.clear()
        with torch.no_grad():
            self.teacher_model(batch["img"])
        predictions = self.student_model(batch["img"])
        regular_loss, regular_detached = self.student_model.loss(batch, predictions)

        teacher_head = self._prediction_branch(self._teacher_feats[self.feats_idx[-1]])
        student_head = self._prediction_branch(self._student_feats[self.feats_idx[-1]])
        teacher_scores = teacher_head["scores"]
        neck_features = [self._teacher_feats[idx] for idx in self.feats_idx[:-1]]
        parts = torch.split(teacher_scores, [feature.shape[-2] * feature.shape[-1] for feature in neck_features], dim=-1)
        score_maps = tuple(part.sigmoid().amax(dim=1, keepdim=True) for part in parts)

        feature_loss = zero.clone()
        for level, layer_index in enumerate(self.feats_idx[:-1]):
            teacher_feature = self.decouple_outputs(self._teacher_feats[layer_index]).detach()
            student_feature = self.projector[level](self.decouple_outputs(self._student_feats[layer_index]))
            feature_loss = feature_loss + self.loss_sl2(
                student_feature,
                teacher_feature,
                feat_idx=level,
                teacher_scores=score_maps,
            )

        confidence, indices = self._topk_indices(teacher_scores, self.distillation_config.topk_anchors)
        score_loss = self._soft_score_loss(student_head, teacher_head)
        box_loss = self._box_distribution_loss(student_head, teacher_head, indices, confidence)
        mask_loss, boundary_loss = self._soft_mask_losses(
            student_head,
            teacher_head,
            indices,
            confidence,
        )
        config = self.distillation_config
        distillation_loss = (
            feature_loss * config.feature_weight * self.dis
            + score_loss * config.soft_score_weight
            + box_loss * config.box_distribution_weight
            + mask_loss * config.soft_mask_weight
            + boundary_loss * config.boundary_weight
        )
        detached = distillation_loss.detach()
        distillation_loss = distillation_loss * batch["img"].shape[0]
        return torch.cat([regular_loss, distillation_loss]), torch.cat([regular_detached, detached])
