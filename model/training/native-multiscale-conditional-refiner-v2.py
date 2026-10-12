"""原尺寸条件U-Net：多尺度语义与原像素跳连，保留强粗mask先验/拒识语义。"""
import importlib.util
from pathlib import Path
import torch
from torch import nn
import torch.nn.functional as F
sp=importlib.util.spec_from_file_location('multiscale_native_original',Path(__file__).with_name('native-conditional-mask-refiner.py'))
original=importlib.util.module_from_spec(sp);sp.loader.exec_module(original)
def pool_binary_seed(seed,out_h,out_w):
 """二值种子精确积分求和，保持原adaptive平均窗口；不改原图mask。"""
 h,w=seed.shape[-2:];ys=torch.arange(out_h,device=seed.device);xs=torch.arange(out_w,device=seed.device)
 y0=torch.div(ys*h,out_h,rounding_mode='floor');y1=torch.div((ys+1)*h+out_h-1,out_h,rounding_mode='floor')
 x0=torch.div(xs*w,out_w,rounding_mode='floor');x1=torch.div((xs+1)*w+out_w-1,out_w,rounding_mode='floor')
 integral=F.pad(seed.cumsum(2).cumsum(3),(1,0,1,0))
 def take(y,x):return integral.index_select(2,y).index_select(3,x)
 total=take(y1,x1)-take(y0,x1)-take(y1,x0)+take(y0,x0)
 return total/((y1-y0)[:,None]*(x1-x0)[None,:]).to(seed.dtype)[None,None]
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
  seed=pool_binary_seed(values[:,3:4],e3.shape[2],e3.shape[3])
  local=(e3*seed).sum((2,3))/seed.sum((2,3)).clamp_min(1)
  presence=self.presence(torch.cat([local,e3.mean((2,3))],dim=1))
  return values[:,3:4]*8-4+self.delta(d1),presence
candidate_loss=original.candidate_loss
pack=original.pack
decode=original.decode
