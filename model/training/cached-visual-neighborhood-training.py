"""邻域分支缓存运算；原网络和径向输入保持冻结。"""
import math
import torch
import torch.nn.functional as F

@torch.no_grad()
def features(model,strip,initial,coarse):
    # 使用模型模块中已冻结的采样定义，避免两份采样公式漂移。
    sampler=type(model).forward_with_radius.__globals__['sample_neighborhood']
    local=sampler(strip,initial,coarse,model.offsets)
    theta=(torch.arange(strip.shape[2],device=strip.device,dtype=strip.dtype)+.5)*(2*math.pi/strip.shape[2])
    theta=theta[None].expand_as(coarse)
    return torch.cat((local,torch.stack((initial/256,coarse/256,theta.sin(),theta.cos()),1)),1)

def forward(model,cache,coarse,angle_bins,distance):
    value=model.project(cache['features'])
    for conv,norm in zip(model.convs,model.norms):
        dilation=conv.dilation[0]
        indices=torch.arange(-dilation,value.shape[-1]+dilation,device=value.device).remainder(value.shape[-1])
        value=value+conv(F.gelu(norm(value)).index_select(-1,indices))
    correction=model.head(F.gelu(value))[:,0]
    radius=torch.minimum(torch.maximum(cache['initial']+correction,(coarse-64).clamp_min(0)),coarse+64)
    return (radius.gather(1,angle_bins.reshape(1,-1)).reshape_as(distance)-distance)[:,None],cache['presence'],radius
