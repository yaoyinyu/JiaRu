"""原像素径向位移原型：RGB/粗mask条带学习半径，输出完整原尺寸mask/presence。"""
import math
import numpy as np
import torch
from torch import nn
import torch.nn.functional as F


def build_strip(rgb, coarse, center, radii):
    """仅读取RGB与同候选粗mask；不接受真值或图片身份。所有采样保持原像素坐标。"""
    if rgb.dtype!=np.uint8 or rgb.ndim!=3 or rgb.shape[2]!=3 or coarse.dtype!=np.bool_ or rgb.shape[:2]!=coarse.shape:
        raise ValueError('native RGB uint8 and aligned binary coarse mask required')
    if radii.ndim!=1 or radii.dtype!=np.float32 or not np.isfinite(radii).all() or np.any(radii<0):
        raise ValueError('finite float32 coarse radii required')
    theta=(np.arange(len(radii),dtype=np.float64)+.5)*(2*math.pi/len(radii))
    offsets=np.arange(-64,65,dtype=np.float32)
    radial=np.maximum(np.float32(0),radii[:,None]+offsets[None,:])
    x=(float(center[0])+np.cos(theta)[:,None]*radial).astype(np.float32)
    y=(float(center[1])+np.sin(theta)[:,None]*radial).astype(np.float32)
    x=np.clip(x,0,rgb.shape[1]-1);y=np.clip(y,0,rgb.shape[0]-1)
    x0=np.floor(x).astype(np.int64);y0=np.floor(y).astype(np.int64)
    x1=np.minimum(x0+1,rgb.shape[1]-1);y1=np.minimum(y0+1,rgb.shape[0]-1)
    wx=(x-x0.astype(np.float32))[:,:,None];wy=(y-y0.astype(np.float32))[:,:,None]
    values=np.concatenate((rgb.astype(np.float32)/np.float32(255),coarse[:,:,None].astype(np.float32)),axis=2)
    top=values[y0,x0]*(1-wx)+values[y0,x1]*wx
    bottom=values[y1,x0]*(1-wx)+values[y1,x1]*wx
    sample=top*(1-wy)+bottom*wy
    sample[:,:,:3]=(sample[:,:,:3]-np.array([.485,.456,.406],np.float32))/np.array([.229,.224,.225],np.float32)
    position=np.broadcast_to(offsets[None,:,None]/np.float32(64),(len(radii),129,1))
    result=np.concatenate((sample,position),axis=2).transpose(2,0,1).copy()
    if not np.isfinite(result).all():raise ValueError('nonfinite original-coordinate sampling')
    return result


class AngularConv(nn.Module):
    def __init__(self,incoming,outgoing):
        super().__init__();self.conv=nn.Conv2d(incoming,outgoing,3,padding=0,bias=False)
        self.norm=nn.GroupNorm(4,outgoing)
    def forward(self,x):
        # 角度为周期轴，半径为非周期轴。
        x=torch.cat((x[:,:,-1:,:],x,x[:,:,:1,:]),dim=2)
        return F.gelu(self.norm(self.conv(F.pad(x,(1,1,0,0)))))


class NativeRadialStripRefiner(nn.Module):
    def __init__(self):
        super().__init__()
        self.features=nn.Sequential(AngularConv(5,16),AngularConv(16,16),AngularConv(16,16))
        self.score=nn.Conv2d(16,1,1)
        self.presence=nn.Linear(16,1)
        nn.init.zeros_(self.score.weight);nn.init.zeros_(self.score.bias)
        nn.init.zeros_(self.presence.weight);nn.init.constant_(self.presence.bias,2.)
        offsets=torch.arange(-64,65,dtype=torch.float32)[None,None,:]
        self.register_buffer('offsets',offsets);self.register_buffer('prior',-.5*(offsets/16).square())

    def forward(self,strip,coarse_radii,angle_bins,distance):
        mask,presence,_=self.forward_with_radius(strip,coarse_radii,angle_bins,distance)
        return mask,presence

    def forward_with_radius(self,strip,coarse_radii,angle_bins,distance):
        """训练可读取半径辅助目标；对外forward保持原尺寸mask/presence两头。"""
        if strip.ndim!=4 or strip.shape[0]!=1 or strip.shape[1]!=5 or strip.shape[3]!=129:
            raise ValueError('batch1 original-coordinate 5-channel radial strip required')
        if coarse_radii.shape!=(1,strip.shape[2]) or angle_bins.shape!=distance.shape or angle_bins.ndim!=3 or angle_bins.shape[0]!=1:
            raise ValueError('full candidate radial metadata required')
        features=self.features(strip);score=self.score(features)[:,0]
        probability=F.softmax(score+self.prior,dim=-1)
        initial=F.softmax(torch.zeros_like(score)+self.prior,dim=-1)
        offset=((probability-initial)*self.offsets).sum(-1).clamp(-64,64)
        radius=(coarse_radii+offset).clamp_min(0)
        native=radius.gather(1,angle_bins.reshape(1,-1)).reshape_as(distance)-distance
        presence=self.presence(features.mean((2,3)))
        return native[:,None],presence,radius
