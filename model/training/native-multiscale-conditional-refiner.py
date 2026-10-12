"""原尺寸条件U-Net：多尺度语义与原像素跳连，保留强粗mask先验/拒识语义。"""
import importlib.util
from pathlib import Path
import torch
from torch import nn
import torch.nn.functional as F
sp=importlib.util.spec_from_file_location('multiscale_native_original',Path(__file__).with_name('native-conditional-mask-refiner.py'))
original=importlib.util.module_from_spec(sp);sp.loader.exec_module(original)
def block(incoming,outgoing):
 return nn.Sequential(nn.Conv2d(incoming,outgoing,3,padding=1,bias=False),nn.GroupNorm(4,outgoing),nn.GELU(),
                      nn.Conv2d(outgoing,outgoing,3,padding=1,bias=False),nn.GroupNorm(4,outgoing),nn.GELU())
class NativeConditionalMaskRefiner(nn.Module):
 def __init__(self):
  super().__init__();self.enc1=block(4,16);self.enc2=block(16,32);self.enc3=block(32,64)
  self.dec2=block(96,32);self.dec1=block(48,16);self.delta=nn.Conv2d(16,1,1);self.presence=nn.Linear(128,1)
  nn.init.zeros_(self.delta.weight);nn.init.zeros_(self.delta.bias);nn.init.zeros_(self.presence.weight);nn.init.constant_(self.presence.bias,2.)
 def forward(self,values):
  e1=self.enc1(values);e2=self.enc2(F.avg_pool2d(e1,2));e3=self.enc3(F.avg_pool2d(e2,2))
  d2=self.dec2(torch.cat([F.interpolate(e3,size=e2.shape[2:],mode='bilinear',align_corners=False),e2],dim=1))
  d1=self.dec1(torch.cat([F.interpolate(d2,size=e1.shape[2:],mode='bilinear',align_corners=False),e1],dim=1))
  seed=F.interpolate(values[:,3:4],size=e3.shape[2:],mode='area')
  local=(e3*seed).sum((2,3))/seed.sum((2,3)).clamp_min(1)
  presence=self.presence(torch.cat([local,e3.mean((2,3))],dim=1))
  return values[:,3:4]*8-4+self.delta(d1),presence
candidate_loss=original.candidate_loss
pack=original.pack
decode=original.decode
