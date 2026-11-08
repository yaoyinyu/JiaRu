"""冻结现有轮廓，在预测边缘内外读取原输入条带并学习局部残差。"""
import math
import torch
from torch import nn
import torch.nn.functional as F


def sample_neighborhood(strip, radius, coarse, offsets):
    """同一角度内线性采样；偏移单位沿用原图径向像素。"""
    features=[]
    for offset in offsets:
        location=(radius-coarse+64+offset).clamp(0,strip.shape[-1]-1)
        lower=location.floor().long();upper=(lower+1).clamp_max(strip.shape[-1]-1)
        index=lower[:,None,:,None].expand(-1,strip.shape[1],-1,1)
        lo=strip.gather(-1,index).squeeze(-1)
        hi=strip.gather(-1,upper[:,None,:,None].expand_as(index)).squeeze(-1)
        features.append(lo+(hi-lo)*(location-lower)[:,None])
    return torch.cat(features,dim=1)


class VisualNeighborhoodRadialRefiner(nn.Module):
    """previous为已冻结网络；新分支零初始化，不使用真值或图片身份。"""
    offsets=(-8.,-4.,-2.,0.,2.,4.,8.)
    def __init__(self, previous):
        super().__init__();self.previous=previous.requires_grad_(False).eval()
        self.project=nn.Conv1d(39,32,1)
        self.convs=nn.ModuleList(nn.Conv1d(32,32,3,dilation=d) for d in (1,2,4,8))
        self.norms=nn.ModuleList(nn.GroupNorm(4,32) for _ in self.convs)
        self.head=nn.Conv1d(32,1,1);nn.init.zeros_(self.head.weight);nn.init.zeros_(self.head.bias)

    def train(self, mode=True):
        super().train(mode);self.previous.eval();return self

    def forward_with_radius(self,strip,coarse,angle_bins,distance):
        with torch.no_grad():
            _,presence,initial=self.previous.forward_with_radius(strip,coarse,angle_bins,distance)
            local=sample_neighborhood(strip,initial,coarse,self.offsets)
            theta=(torch.arange(strip.shape[2],device=strip.device,dtype=strip.dtype)+.5)*(2*math.pi/strip.shape[2])
            theta=theta[None].expand_as(coarse)
            geometry=torch.stack((initial/256,coarse/256,theta.sin(),theta.cos()),1)
        value=self.project(torch.cat((local,geometry),1))
        for conv,norm in zip(self.convs,self.norms):
            dilation=conv.dilation[0]
            indices=torch.arange(-dilation,value.shape[-1]+dilation,device=value.device).remainder(value.shape[-1])
            value=value+conv(F.gelu(norm(value)).index_select(-1,indices))
        correction=self.head(F.gelu(value))[:,0]
        radius=torch.minimum(torch.maximum(initial+correction,(coarse-64).clamp_min(0)),coarse+64)
        mask=(radius.gather(1,angle_bins.reshape(1,-1)).reshape_as(distance)-distance)[:,None]
        return mask,presence,radius

    def forward(self,strip,coarse,angle_bins,distance):
        mask,presence,_=self.forward_with_radius(strip,coarse,angle_bins,distance)
        return mask,presence
