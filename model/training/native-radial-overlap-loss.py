"""以单调的边界位移惩罚替换软形态学IoU项，保留其余原监督。"""
import importlib.util
from pathlib import Path
import torch

_spec=importlib.util.spec_from_file_location('radial_overlap_parent',Path(__file__).with_name('native-boundary-iou-loss.py'))
previous=importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(previous)


def displacement_penalty(radius,target_radius):
    """平滑绝对位移的有界单调代理，近零斜率对应3px边缘带。"""
    if radius.shape!=target_radius.shape or radius.ndim!=2 or radius.shape[-1]!=2048:
        raise ValueError('aligned2048-bin radii required')
    error=torch.sqrt((radius-target_radius).square()+.05**2)-.05
    return (2*error/(3+2*error)).mean()


def objective(mask,presence,radius,truth,target_radius,boundary_band):
    return previous._previous.objective(mask,presence,radius,truth,target_radius,boundary_band)+3*displacement_penalty(radius,target_radius)
