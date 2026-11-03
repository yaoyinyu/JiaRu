"""保留原径向监督并强化完整原图生成的原像素边缘带。"""
import importlib.util
from pathlib import Path
import torch
import torch.nn.functional as F


def _load(name, file):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_base = _load('radial_boundary_base', 'native-radial-training-loss.py')
_band = _load('radial_boundary_full_band', 'native-boundary-band-bce.py')


def boundary_band_for_crop(full_truth, crop):
    """先按完整原图生成radius4带，再提取原ROI并返回全图带像素数。"""
    if full_truth.ndim != 4 or full_truth.shape[:2] != (1, 1):
        raise ValueError('one complete source truth required')
    x0, y0, x1, y1 = crop
    if not (0 <= x0 < x1 <= full_truth.shape[3] and 0 <= y0 < y1 <= full_truth.shape[2]):
        raise ValueError('native crop outside full source')
    band = _band.boundary_band(full_truth, 4)
    return band[:, :, y0:y1, x0:x1].clone(), float(band.sum())


def objective(mask, presence, radius, truth, target_radius, boundary_band):
    if boundary_band.shape != truth.shape or boundary_band.dtype != torch.float32:
        raise ValueError('aligned float32 full-source boundary band required')
    if not bool(torch.isfinite(boundary_band).all()) or not bool((boundary_band >= 0).all()) or not bool((boundary_band <= 1).all()):
        raise ValueError('finite binary boundary band required')
    count = boundary_band.sum()
    if not bool(count > 0):
        raise ValueError('positive complete boundary band required')
    pixel = F.binary_cross_entropy_with_logits(mask, truth, reduction='none')
    boundary = (pixel * boundary_band).sum() / count
    return _base.objective(mask, presence, radius, truth, target_radius) + 2 * boundary
