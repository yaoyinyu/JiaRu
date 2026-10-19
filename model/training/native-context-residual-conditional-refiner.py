"""在原生精修器mask路径增加1/8、1/16空间上下文；原图输出与拒识语义保持。"""
import importlib.util
from pathlib import Path
import torch
from torch import nn
import torch.nn.functional as F

spec=importlib.util.spec_from_file_location('native_context_original',Path(__file__).with_name('native-multiscale-conditional-refiner-v3.py'))
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)


class NativeConditionalMaskRefiner(base.NativeConditionalMaskRefiner):
    def __init__(self):
        super().__init__()
        self.context_down=base.block(64,64)
        self.context_deep=base.block(64,64)
        self.context_up=base.block(128,64)
        self.context_projection=nn.Conv2d(64,64,1)
        nn.init.zeros_(self.context_projection.weight)
        nn.init.zeros_(self.context_projection.bias)

    def load_base_state(self,state):
        """严格继承原权重并归零新增残差投影；先验/旧两头不变。"""
        own=self.state_dict()
        required={name for name in own if not name.startswith('context_')}
        if set(state)!=required:
            raise ValueError('base weight keys mismatch')
        for name,value in state.items():
            if value.shape!=own[name].shape or value.dtype!=own[name].dtype or not torch.isfinite(value).all():
                raise ValueError('base weight tensor mismatch: '+name)
        self.load_state_dict({**own,**state},strict=True)
        with torch.no_grad():
            self.context_projection.weight.zero_()
            self.context_projection.bias.zero_()

    def forward(self,values):
        if values.ndim!=4 or values.shape[0]!=1 or values.shape[1]!=4 or min(values.shape[-2:])<16:
            raise ValueError('native context input requires batch1/4channels/minimum side16')
        e1=self.enc1(values)
        e2=self.enc2(F.avg_pool2d(e1,2))
        e3=self.enc3(F.avg_pool2d(e2,2))
        down=self.context_down(F.avg_pool2d(e3,2))
        deep=self.context_deep(F.avg_pool2d(down,2))
        context=self.context_up(torch.cat([F.interpolate(deep,size=down.shape[-2:],mode='bilinear',align_corners=False),down],dim=1))
        enhanced=e3+F.interpolate(self.context_projection(context),size=e3.shape[-2:],mode='bilinear',align_corners=False)
        d2=self.dec2(torch.cat([F.interpolate(enhanced,size=e2.shape[-2:],mode='bilinear',align_corners=False),e2],dim=1))
        d1=self.dec1(torch.cat([F.interpolate(d2,size=e1.shape[-2:],mode='bilinear',align_corners=False),e1],dim=1))
        # 拒识仍取原e3；新增空间上下文只改变mask路径。
        seed=base.pool_binary_seed(values[:,3:4],e3.shape[2],e3.shape[3])
        local=(e3*seed).sum((2,3))/seed.sum((2,3)).clamp_min(1)
        presence=self.presence(torch.cat([local,e3.mean((2,3))],dim=1))
        return values[:,3:4]*8-4+self.delta(d1),presence


pack=base.pack
decode=base.decode
candidate_loss=base.candidate_loss
