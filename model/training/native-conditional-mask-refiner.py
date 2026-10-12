"""原像素RGB+同候选粗mask精修：全ROI可修正，另有候选拒识输出。"""
import importlib.util
from pathlib import Path
import torch
from torch import nn
import torch.nn.functional as F
sp=importlib.util.spec_from_file_location('native_full_boundary_loss',Path(__file__).with_name('development-cycle-016-soft-boundary-iou.py'))
boundary=importlib.util.module_from_spec(sp);sp.loader.exec_module(boundary)
class NativeConditionalMaskRefiner(nn.Module):
 def __init__(self):
  super().__init__();layers=[]
  for incoming,dilation in [(4,1),(24,3),(24,9)]:
   layers.extend([nn.Conv2d(incoming,24,3,padding=dilation,dilation=dilation,bias=False),nn.GroupNorm(4,24),nn.GELU()])
  self.features=nn.Sequential(*layers);self.delta=nn.Conv2d(24,1,1);self.presence=nn.Linear(48,1)
  nn.init.zeros_(self.delta.weight);nn.init.zeros_(self.delta.bias);nn.init.zeros_(self.presence.weight);nn.init.constant_(self.presence.bias,2.)
 def forward(self,values):
  features=self.features(values);coarse=values[:,3:4]
  local=(features*coarse).sum((2,3))/coarse.sum((2,3)).clamp_min(1)
  global_features=features.mean((2,3))
  presence=self.presence(torch.cat([local,global_features],dim=1))
  # 初态为同候选粗mask有限logits；所有原像素可学习，未限定4像素编辑带。
  return (coarse*8-4)+self.delta(features),presence
def candidate_loss(logits,presence_logits,truth,presence_target):
 logits=logits.float();truth=truth.float();positive=presence_target.float().reshape(-1)
 probability=logits.sigmoid();dims=(1,2,3)
 bce=F.binary_cross_entropy_with_logits(logits,truth)
 intersection=(probability*truth).sum(dims)
 dice=1-(2*intersection+1)/(probability.sum(dims)+truth.sum(dims)+1)
 edge=1-boundary.soft_boundary_iou_per_instance(probability,truth,{'nearBoundaryKernel':5,'epsilon':1e-6})
 denominator=positive.sum().clamp_min(1)
 return bce+(dice*positive).sum()/denominator+.2*(edge*positive).sum()/denominator+.5*F.binary_cross_entropy_with_logits(presence_logits.reshape(-1),positive)
def pack(rgb,coarse):
 import numpy as np
 if rgb.dtype!=np.uint8 or coarse.dtype!=np.uint8 or rgb.shape[:2]!=coarse.shape or not set(np.unique(coarse)).issubset({0,255}):raise ValueError('native input domain')
 normalized=((rgb.astype(np.float64)/255-np.array([.485,.456,.406]))/np.array([.229,.224,.225])).transpose(2,0,1).astype(np.float32)
 return np.concatenate([normalized,(coarse.astype(np.float32)/255)[None]],axis=0)
def decode(logits,presence_logit):
 import numpy as np
 if not np.isfinite(logits).all() or not np.isfinite(presence_logit):raise ValueError('nonfinite output')
 return np.zeros(logits.shape,dtype=bool) if presence_logit<0 else logits>=0
