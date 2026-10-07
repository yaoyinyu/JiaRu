"""显式版本化方形ROI上下文；保留旧0.35，只增加固定0.45对照。"""
import importlib.util
import math
from pathlib import Path
LEGACY_PATH=Path(__file__).with_name('analyze-saved-nail-roi-coverage.py')
s=importlib.util.spec_from_file_location('context_policy_legacy',LEGACY_PATH)
legacy=importlib.util.module_from_spec(s);s.loader.exec_module(legacy)
oracle_allocation=legacy.oracle_allocation
def crop_box(box,width,height,policy):
    if policy in ('native_xyxy_floor_ceil','square_context_035'):
        return legacy.crop_box(box,width,height,policy)
    if policy!='square_context_045':raise ValueError('unknown versioned context policy')
    x0,y0,x1,y1=map(float,box)
    if not all(math.isfinite(v) for v in (x0,y0,x1,y1)) or x1<=x0 or y1<=y0:raise ValueError('invalid box')
    side=max(16,math.ceil(max(x1-x0,y1-y0)*1.9))
    if side>min(width,height):return None
    left=min(max(round((x0+x1)/2-side/2),0),width-side)
    top=min(max(round((y0+y1)/2-side/2),0),height-side)
    return left,top,left+side,top+side
def coverage_matrix(truths,boxes,policy):
    import numpy as np
    height,width=truths.shape[1:];crops=[crop_box(b,width,height,policy) for b in boxes]
    result=np.zeros((len(truths),len(boxes)),np.float64)
    for i,t in enumerate(truths):
        pixels=int(t.sum())
        if not pixels:raise ValueError('empty truth')
        for j,c in enumerate(crops):
            if c:
                x0,y0,x1,y1=c;result[i,j]=int(t[y0:y1,x0:x1].sum())/pixels
    return crops,result
