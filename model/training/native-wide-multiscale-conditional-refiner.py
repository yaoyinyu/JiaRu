"""仅将原像素条件U-Net宽度翻倍；同强先验、同存在性及原尺寸输出。"""
import importlib.util
from pathlib import Path
import torch
from torch import nn
import torch.nn.functional as F
s=importlib.util.spec_from_file_location('wide_native_base',Path(__file__).with_name('native-multiscale-conditional-refiner-v3.py'))
base=importlib.util.module_from_spec(s);s.loader.exec_module(base)
class NativeConditionalMaskRefiner(nn.Module):
 def __init__(self):
  super().__init__();self.enc1=base.block(4,32);self.enc2=base.block(32,64);self.enc3=base.block(64,128)
  self.dec2=base.block(192,64);self.dec1=base.block(96,32);self.delta=nn.Conv2d(32,1,1);self.presence=nn.Linear(256,1)
  nn.init.zeros_(self.delta.weight);nn.init.zeros_(self.delta.bias);nn.init.zeros_(self.presence.weight);nn.init.constant_(self.presence.bias,2.)
 def forward(self,values):
  e1=self.enc1(values);e2=self.enc2(F.avg_pool2d(e1,2));e3=self.enc3(F.avg_pool2d(e2,2))
  d2=self.dec2(torch.cat([F.interpolate(e3,size=e2.shape[2:],mode='bilinear',align_corners=False),e2],dim=1))
  d1=self.dec1(torch.cat([F.interpolate(d2,size=e1.shape[2:],mode='bilinear',align_corners=False),e1],dim=1))
  seed=base.pool_binary_seed(values[:,3:4],e3.shape[2],e3.shape[3])
  local=(e3*seed).sum((2,3))/seed.sum((2,3)).clamp_min(1)
  presence=self.presence(torch.cat([local,e3.mean((2,3))],dim=1))
  return values[:,3:4]*8-4+self.delta(d1),presence
candidate_loss=base.candidate_loss
pack=base.pack
decode=base.decode
