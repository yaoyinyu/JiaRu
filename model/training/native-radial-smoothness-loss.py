"""半径角度域平滑性正则：惩罚相邻 bin 的高频抖动，保留上一轮全部损失。

背景（cycle096 实测，634 甲）：真值半径的相邻 bin 抖动 std 仅 0.165px，模型原生半径
3.14px（19 倍）。根因是逐 bin 独立的 smooth_l1 没有邻域耦合，而 BCE/Dice 只看面积、
小幅抖动不被惩罚。本模块加一项二阶差分平方均值，把「相邻 bin 连续」显式写进目标。

为什么是二阶而非一阶（TV）：光滑圆的半径一阶差分约 ρ·Δθ≈0.21px，二阶约 ρ·Δθ²≈6.6e-4px；
二阶对整体形状（椭圆度、倾斜、大小）几乎零惩罚、保角，一阶会把形状往圆里拉。

上游为已关闭的第90次配方 `native-side-boundary-loss.py`，不引入额外权重配方，
保证与基线相比只有一个训练变量（λ）。缺省 `smoothness_weight = 0` 时**直接返回上游
损失对象本身**，与未接入本模块逐位一致。
"""

import importlib.util
import math
from pathlib import Path

import torch

_spec = importlib.util.spec_from_file_location(
    'radial_smoothness_previous', Path(__file__).with_name('native-side-boundary-loss.py'))
previous = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(previous)

SMOOTHNESS_SCALE = 8.0
_state = {'weight': 0.0}


def radial_smoothness_penalty(radius, scale=SMOOTHNESS_SCALE):
    """循环二阶差分平方均值；在 radius/scale 空间计算，与上游 radial 项同尺度。"""
    if not torch.is_tensor(radius):
        raise ValueError('radius tensor required')
    if radius.dim() != 2 or radius.shape[1] < 3:
        raise ValueError('radial [batch, bins>=3] required')
    if not bool(torch.isfinite(radius).all()):
        raise ValueError('finite radius required')
    if not isinstance(scale, (int, float)) or not math.isfinite(scale) or scale <= 0:
        raise ValueError('positive finite scale required')
    values = radius / scale
    second = torch.roll(values, 1, 1) - 2 * values + torch.roll(values, -1, 1)
    return (second ** 2).mean()


def configure(smoothness_weight=0.0):
    """设定平滑正则强度；上游无权重配方，只需登记 λ。"""
    if not isinstance(smoothness_weight, (int, float)) or not math.isfinite(smoothness_weight) or smoothness_weight < 0:
        raise ValueError('nonnegative finite smoothness weight required')
    _state['weight'] = float(smoothness_weight)


def objective(mask, presence, radius, truth, target_radius, boundary_band, smoothness_weight=None):
    base = previous.objective(mask, presence, radius, truth, target_radius, boundary_band)
    weight = _state['weight'] if smoothness_weight is None else float(smoothness_weight)
    if weight == 0.0:
        return base
    return base + base.new_tensor(weight) * radial_smoothness_penalty(radius)
