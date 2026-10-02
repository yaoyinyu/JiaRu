"""仅改变BCE平均域；编辑带必须由同候选冻结基底提供，禁止从真值生成。"""
from __future__ import annotations
import importlib.util
from pathlib import Path
import torch
import torch.nn.functional as F

spec = importlib.util.spec_from_file_location('band_objective_previous_loss', Path(__file__).with_name('conditional-nail-refinement-model.py'))
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)


def conditional_mask_loss(logits, truth, *, editable_band, boundary_weight=0.2):
    """非空带按带内像素平均BCE；空带保留原全ROI BCE。

    正Dice和0.2边界代理保留全ROI域，训练组合另确保带外delta零梯度。
    显式传入band，避免从输出/真值反推可编辑范围。
    """
    if logits.ndim != 4 or logits.shape[1] != 1 or truth.shape != logits.shape:
        raise ValueError('native loss N1HW shape')
    if editable_band.shape != logits.shape or editable_band.dtype != torch.bool or editable_band.device != logits.device:
        raise ValueError('explicit fixed native bool band shape/device')
    logits, truth = logits.float(), truth.float()
    if not torch.isfinite(logits).all() or not torch.isfinite(truth).all() or torch.any((truth < 0) | (truth > 1)):
        raise ValueError('nonfinite/invalid native loss input')
    dims = (1, 2, 3)
    positive = (truth.sum(dim=dims) > 0).float()
    count = positive.sum().clamp_min(1)
    probability = logits.sigmoid()
    pixel_bce = F.binary_cross_entropy_with_logits(logits, truth, reduction='none')
    editable_count = editable_band.sum(dim=dims)
    band_bce = (pixel_bce * editable_band).sum(dim=dims) / editable_count.clamp_min(1)
    bce = torch.where(editable_count > 0, band_bce, pixel_bce.mean(dim=dims)).mean()
    intersection = (probability * truth).sum(dim=dims)
    dice_per = 1 - (2 * intersection + 1) / (probability.sum(dim=dims) + truth.sum(dim=dims) + 1)
    boundary_per = 1 - previous.boundary.soft_boundary_iou_per_instance(probability, truth, {'nearBoundaryKernel':5, 'epsilon':1e-6})
    dice = (dice_per * positive).sum() / count
    edge = (boundary_per * positive).sum() / count
    total = bce + dice + boundary_weight * edge
    return total, {'bce':float(bce.detach()), 'positiveDice':float(dice.detach()),
                   'positiveBoundaryProxy':float(edge.detach()), 'positiveCount':int(positive.sum().item()),
                   'emptyCount':int((1-positive).sum().item()), 'editablePixelsPerCandidate':editable_count.tolist(),
                   'bceDomain':'fixed_band_mean_nonempty_else_original_full_roi_mean'}
