"""冻结StageA视觉骨干给原生精修mask提供语义残差；原四通道/两头保持。"""
import importlib.util
from pathlib import Path
import torch
from torch import nn
import torch.nn.functional as F

s=importlib.util.spec_from_file_location('pretrained_context_base',Path(__file__).with_name('native-context-residual-conditional-refiner.py'))
base=importlib.util.module_from_spec(s);s.loader.exec_module(base)


def semantic_rgb(values):
    """按现行pack存储域恢复原RGB整数格点，再转YOLO的float32/255域。"""
    mean=values.new_tensor([.485,.456,.406])[None,:,None,None]
    std=values.new_tensor([.229,.224,.225])[None,:,None,None]
    return ((values[:,:3]*std+mean)*255).round().clamp(0,255)/255


def sample_at_native_quarter(feature,stride,out_h,out_w):
    """以原图坐标(4*i+1.5)采样，骨干中心stride*i；pad不压缩进原坐标。"""
    y=(torch.arange(out_h,device=feature.device,dtype=torch.float32)*4+1.5)/stride
    x=(torch.arange(out_w,device=feature.device,dtype=torch.float32)*4+1.5)/stride
    fy=y.floor();fx=x.floor();wy=(y-fy)[None,None,:,None];wx=(x-fx)[None,None,None,:]
    y0=fy.long().clamp(0,feature.shape[2]-1);y1=(fy.long()+1).clamp(0,feature.shape[2]-1)
    x0=fx.long().clamp(0,feature.shape[3]-1);x1=(fx.long()+1).clamp(0,feature.shape[3]-1)
    top=feature.index_select(2,y0);bottom=feature.index_select(2,y1)
    top=top.index_select(3,x0)*(1-wx)+top.index_select(3,x1)*wx
    bottom=bottom.index_select(3,x0)*(1-wx)+bottom.index_select(3,x1)*wx
    return top*(1-wy)+bottom*wy


class FrozenStageAFeatures(nn.Module):
    def __init__(self,layers,selected,channels,strides):
        super().__init__();self.layers=nn.ModuleList(layers);self.selected=tuple(selected)
        self.channels=tuple(channels);self.strides=tuple(strides)
        if len(self.selected)!=len(self.channels) or len(self.selected)!=len(self.strides) or self.selected!=tuple(sorted(set(self.selected))):
            raise ValueError('invalid frozen feature specification')
        self.requires_grad_(False);self.eval()

    def train(self,mode=True):
        return super().train(False)

    def forward(self,rgb):
        features=[]
        for index,layer in enumerate(self.layers):
            rgb=layer(rgb)
            if index in self.selected:features.append(rgb)
        return tuple(features)


def load_stage_a_backbone(path,architecture):
    """仅读取调用者已校验的本机checkpoint；不下载、不fuse、不运行模型。"""
    checkpoint=torch.load(path,map_location='cpu',weights_only=False)
    model=checkpoint['ema'] if checkpoint.get('ema') is not None else checkpoint['model']
    end=architecture['backboneEndExclusive'];layers=list(model.model.children())[:end]
    if len(layers)!=end or end!=len(model.yaml['backbone']):raise ValueError('backbone length mismatch')
    for row,layer in zip(architecture['layers'],layers,strict=True):
        if layer.i!=row['index'] or layer.f!=row['from'] or type(layer).__module__+'.'+type(layer).__name__!=row['class']:
            raise ValueError('actual backbone layout mismatch')
    result=FrozenStageAFeatures(layers,architecture['selectedFeatureIndices'],architecture['selectedFeatureChannels'],[architecture['layers'][i]['cumulativeStride'] for i in architecture['selectedFeatureIndices']]).float()
    if not all(torch.isfinite(v).all() for v in result.state_dict().values()):raise ValueError('nonfinite backbone weights')
    return result


class NativeConditionalMaskRefiner(base.NativeConditionalMaskRefiner):
    def __init__(self,backbone):
        super().__init__();self.semantic_backbone=backbone
        self.semantic_projections=nn.ModuleList([nn.Conv2d(c,64,1) for c in backbone.channels])
        for projection in self.semantic_projections:
            nn.init.zeros_(projection.weight);nn.init.zeros_(projection.bias)
        self.semantic_backbone.requires_grad_(False);self.semantic_backbone.eval()

    def train(self,mode=True):
        super().train(mode);self.semantic_backbone.eval();return self

    def requires_grad_(self,requires_grad=True):
        super().requires_grad_(requires_grad);self.semantic_backbone.requires_grad_(False);return self

    def load_refiner_state(self,state):
        own=self.state_dict();required={k for k in own if not k.startswith('semantic_')}
        if set(state)!=required:raise ValueError('refiner weight keys mismatch')
        for name,value in state.items():
            if value.shape!=own[name].shape or value.dtype!=own[name].dtype or not torch.isfinite(value).all():raise ValueError('refiner tensor mismatch: '+name)
        self.load_state_dict({**own,**state},strict=True)
        with torch.no_grad():
            for projection in self.semantic_projections:projection.weight.zero_();projection.bias.zero_()

    def forward(self,values):
        if values.ndim!=4 or values.shape[0]!=1 or values.shape[1]!=4 or min(values.shape[-2:])<16 or max(values.shape[-2:])>1536:
            raise ValueError('native pretrained input requires batch1/channels4/side16..1536')
        e1=self.enc1(values);e2=self.enc2(F.avg_pool2d(e1,2));e3=self.enc3(F.avg_pool2d(e2,2))
        down=self.context_down(F.avg_pool2d(e3,2));deep=self.context_deep(F.avg_pool2d(down,2))
        context=self.context_up(torch.cat([F.interpolate(deep,size=down.shape[-2:],mode='bilinear',align_corners=False),down],dim=1))
        enhanced=e3+F.interpolate(self.context_projection(context),size=e3.shape[-2:],mode='bilinear',align_corners=False)
        with torch.no_grad():
            rgb=semantic_rgb(values);height,width=values.shape[-2:]
            rgb=F.pad(rgb,(0,(-width)%32,0,(-height)%32),value=114/255)
            features=self.semantic_backbone(rgb)
        for feature,projection,stride in zip(features,self.semantic_projections,self.semantic_backbone.strides,strict=True):
            enhanced=enhanced+sample_at_native_quarter(projection(feature),stride,e3.shape[2],e3.shape[3])
        d2=self.dec2(torch.cat([F.interpolate(enhanced,size=e2.shape[-2:],mode='bilinear',align_corners=False),e2],dim=1))
        d1=self.dec1(torch.cat([F.interpolate(d2,size=e1.shape[-2:],mode='bilinear',align_corners=False),e1],dim=1))
        seed=base.base.pool_binary_seed(values[:,3:4],e3.shape[2],e3.shape[3])
        local=(e3*seed).sum((2,3))/seed.sum((2,3)).clamp_min(1)
        presence=self.presence(torch.cat([local,e3.mean((2,3))],dim=1))
        return values[:,3:4]*8-4+self.delta(d1),presence


pack=base.pack
decode=base.decode
candidate_loss=base.candidate_loss
