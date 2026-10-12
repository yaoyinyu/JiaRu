"""只切断存在性损失到编码器的梯度；同参数/同非零前向/同解码。"""
import importlib.util
from pathlib import Path
import torch
import torch.nn.functional as F
s=importlib.util.spec_from_file_location('detached_native_base',Path(__file__).with_name('native-multiscale-conditional-refiner-v3.py'))
base=importlib.util.module_from_spec(s);s.loader.exec_module(base)
class NativeConditionalMaskRefiner(base.NativeConditionalMaskRefiner):
 def forward(self,values):
  e1=self.enc1(values);e2=self.enc2(F.avg_pool2d(e1,2));e3=self.enc3(F.avg_pool2d(e2,2))
  d2=self.dec2(torch.cat([F.interpolate(e3,size=e2.shape[2:],mode='bilinear',align_corners=False),e2],dim=1))
  d1=self.dec1(torch.cat([F.interpolate(d2,size=e1.shape[2:],mode='bilinear',align_corners=False),e1],dim=1))
  seed=base.pool_binary_seed(values[:,3:4],e3.shape[2],e3.shape[3])
  local=(e3*seed).sum((2,3))/seed.sum((2,3)).clamp_min(1)
  presence=self.presence(torch.cat([local,e3.mean((2,3))],dim=1).detach())
  return values[:,3:4]*8-4+self.delta(d1),presence
candidate_loss=base.candidate_loss
pack=base.pack
decode=base.decode
