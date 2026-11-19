"""按完整甲面长轴定位侧缘，增加原像素侧缘监督，保留原损失。"""
import importlib.util
from pathlib import Path

import torch
import torch.nn.functional as F

_spec = importlib.util.spec_from_file_location(
    'side_boundary_previous', Path(__file__).with_name('native-boundary-auxiliary-loss.py'))
previous = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(previous)


def side_weights(truth):
    """仅训练真值定义PCA长轴；两端符号对称，无甲根方向假设。"""
    if truth.ndim != 4 or truth.shape[:2] != (1, 1):
        raise ValueError('one complete native truth required')
    if not bool(torch.isfinite(truth).all()) or not bool(((truth == 0) | (truth == 1)).all()):
        raise ValueError('finite binary truth required')
    coordinates = truth[0, 0].nonzero().to(dtype=torch.float32)
    if len(coordinates) < 3:
        raise ValueError('nonempty complete nail required')
    centered = coordinates - coordinates.mean(0)
    covariance = centered.T @ centered / len(coordinates)
    values, vectors = torch.linalg.eigh(covariance)
    # 近圆形甲没有稳定长轴，采用均匀权重。
    if bool(values[-1] <= values[0] * 1.1):
        return torch.ones_like(truth)
    axis = vectors[:, -1]
    projection = centered @ axis
    midpoint = (projection.max() + projection.min()) * .5
    half_length = (projection.max() - projection.min()) * .5
    y, x = torch.meshgrid(
        torch.arange(truth.shape[-2], device=truth.device, dtype=torch.float32),
        torch.arange(truth.shape[-1], device=truth.device, dtype=torch.float32), indexing='ij')
    axial = ((y - coordinates[:, 0].mean()) * axis[0]
             + (x - coordinates[:, 1].mean()) * axis[1] - midpoint) / half_length
    # 两端仍接受原损失与新增项的监督；侧缘获得双倍新增权重。
    return torch.where(axial.abs() < .7, 1., .5)[None, None]


def side_boundary_penalty(mask, truth, boundary_band):
    if mask.shape != truth.shape or boundary_band.shape != truth.shape:
        raise ValueError('aligned full native arrays required')
    if not bool(torch.isfinite(mask).all()) or not bool(torch.isfinite(boundary_band).all()):
        raise ValueError('finite mask and full-source band required')
    if not bool(((boundary_band == 0) | (boundary_band == 1)).all()):
        raise ValueError('original binary full-source band required')
    weights = side_weights(truth).detach() * boundary_band
    if not bool(weights.sum() > 0):
        raise ValueError('complete full-source boundary band required')
    pixel = F.binary_cross_entropy_with_logits(mask, truth, reduction='none')
    return (pixel * weights).sum() / weights.sum()


def objective(mask, presence, radius, truth, target_radius, boundary_band):
    return previous.objective(mask, presence, radius, truth, target_radius, boundary_band) + .5 * side_boundary_penalty(mask, truth, boundary_band)
