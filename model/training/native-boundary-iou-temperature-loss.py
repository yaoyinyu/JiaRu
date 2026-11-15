"""在现行原像素边缘损失中显式控制软边界温度。"""
import importlib.util
import math
from pathlib import Path
import torch

_spec = importlib.util.spec_from_file_location('temperature_boundary_parent', Path(__file__).with_name('native-boundary-iou-loss.py'))
previous = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(previous)


def soft_boundary_iou(logits, truth, temperature=.25):
    if not math.isfinite(temperature) or temperature <= 0:
        raise ValueError('positive finite boundary temperature required')
    if logits.shape != truth.shape or not torch.is_floating_point(logits):
        raise ValueError('aligned floating point mask and truth required')
    target = previous.inner_boundary_band(truth.float())
    if not bool(target.sum() > 0):
        raise ValueError('positive full target boundary required')
    band = previous.inner_boundary_band((logits / temperature).sigmoid())
    intersection = (band * target).sum()
    union = band.sum() + target.sum() - intersection
    return 1 - (intersection + 1e-6) / (union + 1e-6)


def objective(mask, presence, radius, truth, target_radius, boundary_band):
    return previous._previous.objective(mask, presence, radius, truth, target_radius, boundary_band) + 3 * soft_boundary_iou(mask, truth)
