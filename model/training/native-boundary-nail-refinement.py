"""固定基底的原像素窄带纠正头；本模块本身不批准训练或发布。"""
from __future__ import annotations
import cv2
import numpy as np
import torch
from torch import nn


class NativeBoundaryNailRefiner(nn.Module):
    """N×6×H×W输入，输出原尺寸logit残差；H/W保持原ROI像素。

    六通道：ImageNet RGB、冻结基底概率、同候选粗mask、固定4像素编辑带。
    输出层零初始化；不重新训练基底，不把GT用于部署编辑带或提示。
    """
    def __init__(self):
        super().__init__()
        layers=[]
        for incoming in [6,32,32]:
            layers.extend([nn.Conv2d(incoming,32,3,padding=1,bias=False),nn.GroupNorm(4,32),nn.GELU()])
        self.features=nn.Sequential(*layers);self.output=nn.Conv2d(32,1,1)
        nn.init.zeros_(self.output.weight);nn.init.zeros_(self.output.bias)

    def forward(self,values):return self.output(self.features(values))


def editable_boundary_band(base_probability):
    if base_probability.ndim!=2 or base_probability.dtype!=np.float32 or not np.isfinite(base_probability).all() or np.any((base_probability<0)|(base_probability>1)):
        raise ValueError('invalid frozen native probability')
    mask=(base_probability>=.5).astype(np.uint8)
    # 零填充与原图内部ROI的边界语义一致，调用者仍须保存原图坐标。
    padded=np.pad(mask,1);edges=padded-cv2.erode(padded,np.ones((3,3),np.uint8))
    band=cv2.dilate(edges,np.ones((9,9),np.uint8)).astype(bool)[1:-1,1:-1]
    return band


def pack_native_input(rgb,coarse,base_probability):
    if rgb.ndim!=3 or rgb.shape[2]!=3 or rgb.dtype!=np.uint8 or coarse.dtype!=np.uint8 or not set(np.unique(coarse)).issubset({0,255}):raise ValueError('native RGB/coarse contract')
    if rgb.shape[:2]!=coarse.shape or coarse.shape!=base_probability.shape:raise ValueError('native input shape')
    band=editable_boundary_band(base_probability)
    normalized=((rgb.astype(np.float64)/255-np.array([.485,.456,.406]))/np.array([.229,.224,.225])).transpose(2,0,1).astype(np.float32)
    packed=np.concatenate([normalized,base_probability[None],(coarse/255).astype(np.float32)[None],band.astype(np.float32)[None]],axis=0)
    return packed,band


def compose_native_logits(base_probability,delta,band):
    """训练用有限logits；只有编辑带内delta有梯度。"""
    base=base_probability.double().clamp(1e-6,1-1e-6)
    baseline=torch.log(base)-torch.log1p(-base)
    return torch.where(band.bool(),baseline+delta.double(),baseline).float()


def apply_native_delta(base_probability,delta,band):
    """推理组合：原图0.5门不变，编辑带外概率逐bit保留。

    错误必须由调用者转人工，不能回退后计正式识别成功；有效空基底的带为空。
    """
    editable_boundary_band(base_probability)
    if delta.shape!=base_probability.shape or band.shape!=base_probability.shape or band.dtype!=bool or not np.isfinite(delta).all():raise ValueError('native delta/shape/nonfinite error')
    if not np.array_equal(band,editable_boundary_band(base_probability)):raise ValueError('editable band not derived from fixed base')
    clipped=np.clip(base_probability.astype(np.float64),1e-6,1-1e-6)
    logits=np.log(clipped)-np.log1p(-clipped)+delta.astype(np.float64)
    changed=(1/(1+np.exp(-np.clip(logits,-80,80)))).astype(np.float32)
    result=base_probability.copy();result[band]=changed[band]
    return result
