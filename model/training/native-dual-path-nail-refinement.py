"""原尺寸局部与上下文并行纠正原型；不批准训练或正式发布。"""
from __future__ import annotations
import importlib.util
from pathlib import Path
import torch
from torch import nn


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


context_module=module('dual_path_context',Path(__file__).with_name('native-context-nail-refinement.py'))


class NativeBoundaryNailRefiner(nn.Module):
    """同六通道/原尺寸，27像素空间路径与7像素局部路径的残差相加。

    上下文分支沿用既有构造器与初始化；局部分支用独立CPU seed1606，
    不消费外部CPU随机流或修改CUDA随机状态。两个输出层均零初始化。
    GroupNorm仍含全ROI统计；7/27仅表示卷积空间路径，不是网络唯一上下文。
    """
    def __init__(self):
        super().__init__()
        self.context=context_module.NativeBoundaryNailRefiner()
        with torch.random.fork_rng(devices=[]):
            torch.random.default_generator.manual_seed(1606)
            self.local=context_module.base.NativeBoundaryNailRefiner()

    def forward(self,values):return self.context(values)+self.local(values)


editable_boundary_band=context_module.editable_boundary_band
pack_native_input=context_module.pack_native_input
compose_native_logits=context_module.compose_native_logits
apply_native_delta=context_module.apply_native_delta
