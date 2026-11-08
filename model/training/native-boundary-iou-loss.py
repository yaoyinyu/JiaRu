"""直接约束原像素内侧边缘带的重叠，沿用现行2px评分几何。"""
import importlib.util
from pathlib import Path
import torch
import torch.nn.functional as F

_spec=importlib.util.spec_from_file_location('native_biou_previous',Path(__file__).with_name('native-radial-boundary-loss.py'))
_previous=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(_previous)


def inner_boundary_band(probability, tolerance=2):
    """二值输入与原评分器的内轮廓→膨胀→乘前景逐像素一致。"""
    if probability.ndim!=4 or probability.shape[:2]!=(1,1) or tolerance!=2:
        raise ValueError('one original-pixel mask and fixed tolerance2 required')
    eroded=-F.max_pool2d(-probability,3,stride=1,padding=1)
    edge=(probability-eroded).clamp(0,1)
    near=F.max_pool2d(edge,2*tolerance+1,stride=1,padding=tolerance)
    return probability*near


def soft_boundary_iou(logits, truth):
    if logits.shape!=truth.shape or not torch.is_floating_point(logits):
        raise ValueError('aligned floating point mask and truth required')
    target=inner_boundary_band(truth.float())
    if not bool(target.sum()>0):
        raise ValueError('positive full target boundary required')
    band=inner_boundary_band((logits/.5).sigmoid())
    intersection=(band*target).sum()
    union=band.sum()+target.sum()-intersection
    return 1-(intersection+1e-6)/(union+1e-6)


def objective(mask,presence,radius,truth,target_radius,boundary_band):
    return _previous.objective(mask,presence,radius,truth,target_radius,boundary_band)+3*soft_boundary_iou(mask,truth)
