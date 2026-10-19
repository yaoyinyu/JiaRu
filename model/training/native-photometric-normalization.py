"""仅规范化原尺寸条件候选的模型输入；不改变源图、粗mask、真值或采样坐标。"""
import math
import numpy as np


def normalize(rgb):
    values=np.asarray(rgb)
    if values.dtype!=np.uint8 or values.ndim!=3 or values.shape[2]!=3 or min(values.shape[:2])<16 or max(values.shape[:2])>1536:
        raise ValueError('native uint8 RGB sides16..1536 required')
    flat=values.reshape(-1,3);n=len(flat);integers=flat.astype(np.uint64)
    sums=integers.sum(axis=0,dtype=np.uint64);squares=(integers*integers).sum(axis=0,dtype=np.uint64)
    means=np.array([int(s)/n for s in sums],dtype=np.float64)
    scales=np.array([math.sqrt(max(1.,int(q)/n-float(mu)*float(mu))) for q,mu in zip(squares,means)],dtype=np.float64)
    normalized=np.clip(.5+.2*((flat.astype(np.float64)-means)/scales),0.,1.)*255.
    # 先统一为uint8整数格点，再进入原pack；跨语言须保留偶数舍入规则。
    return np.rint(normalized).astype(np.uint8).reshape(values.shape)


class InputAdapter:
    def __init__(self,module):self.module=module
    def __getattr__(self,name):return getattr(self.module,name)
    def pack(self,rgb,coarse):return self.module.pack(normalize(rgb),coarse)
