"""原尺寸边缘带困难像素监督；全甲面BCE、Dice和距离目标由调用者保留。"""
import importlib.util
import math
from pathlib import Path

import torch
import torch.nn.functional as F

_spec = importlib.util.spec_from_file_location(
    'native_hard_boundary_reference', Path(__file__).with_name('normal-stage-b-boundary-loss.py'))
reference = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(reference)
soft_boundary = reference.soft_boundary


def hard_boundary_bce(logits, truth, radius=4, fraction=0.25):
    """在每个完整候选的原4px带内，稳定选择最高BCE；不改变真值或候选分母。"""
    if logits.ndim != 4 or logits.shape != truth.shape or logits.shape[:2] != (1, 1):
        raise ValueError('one complete aligned candidate required')
    if radius != 4 or not math.isfinite(fraction) or not 0 < fraction <= 1:
        raise ValueError('original radius4 and fraction in (0,1] required')
    if not bool(torch.isfinite(logits).all()) or not bool(((truth == 0) | (truth == 1)).all()):
        raise ValueError('finite logits and binary truth required')
    band = reference.band.boundary_band(truth, radius).bool()
    pixel_losses = F.binary_cross_entropy_with_logits(logits.float(), truth.float(), reduction='none')[band]
    if not pixel_losses.numel():
        raise ValueError('positive boundary band missing')
    count = max(1, math.ceil(pixel_losses.numel() * fraction))
    # 索引选择不参与微分；相同损失按原行优先次序处理，便于逐字节重放。
    indices = torch.argsort(pixel_losses.detach(), descending=True, stable=True)[:count]
    return pixel_losses[indices].mean()


def boundary_band_bce(logits, truth, radius=4):
    return hard_boundary_bce(logits, truth, radius, 0.25)
