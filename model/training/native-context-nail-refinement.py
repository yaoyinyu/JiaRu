"""原像素纠正的空间上下文单变量；不改变参数、张量初始化或组合规则。"""
from __future__ import annotations
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('native_context_base', Path(__file__).with_name('native-boundary-nail-refinement.py'))
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)


class NativeBoundaryNailRefiner(base.NativeBoundaryNailRefiner):
    """仅设置既有卷积的 dilation/padding；不创建额外参数或消费随机数。

    卷积空间路径感受野从7变27；GroupNorm仍包含整块ROI统计。
    因此27不是整个网络的唯一上下文边界，也不是质量可达性证明。
    """
    def __init__(self):
        super().__init__()
        for index, dilation in zip((0, 3, 6), (1, 3, 9), strict=True):
            self.features[index].dilation = (dilation, dilation)
            self.features[index].padding = (dilation, dilation)


editable_boundary_band = base.editable_boundary_band
pack_native_input = base.pack_native_input
compose_native_logits = base.compose_native_logits
apply_native_delta = base.apply_native_delta
