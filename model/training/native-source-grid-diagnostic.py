"""已知图对的固定网格像素诊断；仅内存数值，不证明来源独立或视觉审核通过。"""
import hashlib
import numpy as np
from PIL import Image

KERNELS=('nearest','box','bilinear','bicubic','lanczos')

def grid_boxes(size,rows,columns):
    w,h=size
    if any(type(x) is not int or x<=0 for x in (w,h,rows,columns)) or w%columns or h%rows:
        raise ValueError('grid geometry is not an exact full-source partition')
    dx,dy=w//columns,h//rows
    return [[x*dx,y*dy,(x+1)*dx,(y+1)*dy] for y in range(rows) for x in range(columns)]

def metric(a,b):
    if a.shape!=b.shape or a.dtype!=np.uint8 or b.dtype!=np.uint8 or a.ndim!=3 or a.shape[2]!=3:
        raise ValueError('metrics require matching uint8 RGB domains')
    diff=(a.astype(np.float64)-b.astype(np.float64))/255.0
    return {'maeNormalizedRgb':float(np.mean(np.abs(diff))),'rmseNormalizedRgb':float(np.sqrt(np.mean(diff*diff)))}

def score_grid(target,reference,rows,columns):
    if target.mode!='RGB' or reference.mode!='RGB':
        raise ValueError('explicit native RGB storage domain required')
    boxes=grid_boxes(target.size,rows,columns)
    cells=[]
    for ordinal,box in enumerate(boxes,1):
        roi=target.crop(tuple(box));actual=np.asarray(roi,dtype=np.uint8);variants=[]
        for kernel in KERNELS:
            resized=reference.resize(roi.size,resample=getattr(Image.Resampling,kernel.upper()))
            scores=metric(actual,np.asarray(resized,dtype=np.uint8))
            variants.append({'kernel':kernel,'diagnosticResizeSize':list(roi.size),**scores})
        best=min(variants,key=lambda x:x['maeNormalizedRgb'])
        cells.append({'cellOrdinal':ordinal,'targetOriginalPixelBox':box,'minimumMaeNormalizedRgb':best['maeNormalizedRgb'],'minimumKernel':best['kernel'],'variants':variants})
    ranked=sorted(cells,key=lambda x:(x['minimumMaeNormalizedRgb'],x['cellOrdinal']))
    unique=len(ranked)==1 or ranked[0]['minimumMaeNormalizedRgb']<ranked[1]['minimumMaeNormalizedRgb']
    second=ranked[1]['minimumMaeNormalizedRgb'] if len(ranked)>1 else None
    return {'cells':cells,'bestCellOrdinal':ranked[0]['cellOrdinal'],'bestMaeNormalizedRgb':ranked[0]['minimumMaeNormalizedRgb'],'secondMaeNormalizedRgb':second,'uniqueBestCell':unique,'scoresAreDiagnosticResampledUnitsNotOriginalBoundaryMetrics':True}

def diagnose(target,positive,reference,spec):
    control=score_grid(target,positive,spec['rows'],spec['columns'])
    best=control['bestMaeNormalizedRgb'];second=control['secondMaeNormalizedRgb']
    passed=(control['uniqueBestCell'] and control['bestCellOrdinal']==spec['positiveExpectedCell']
            and best<=spec['positiveMaximumMaeNormalizedRgb']
            and second is not None and best<=spec['positiveMaximumBestToSecondRatio']*second)
    comparison=score_grid(target,reference,spec['rows'],spec['columns']) if passed else None
    return {'positiveControl':control,'positiveControlPassed':passed,
            'candidateComparison':comparison,'candidateComparisonComputed':comparison is not None,
            'candidateHypothesisCell':spec['candidateHypothesisCell'],
            'candidateBestCellMatchesHypothesis':comparison['bestCellOrdinal']==spec['candidateHypothesisCell'] if comparison else None,
            'interpretation':'numerical_source_reuse_clue_only_requires_explicit_pair_review' if passed else 'positive_control_failed_reject_candidate_interpretation',
            'nativeVisualApproved':False,'sourceParentIndependenceQualified':False,'trainingAllowed':False}

def guarded_rgb_sources(layout,pack,sourceEntries,callback=None):
    """守卫成功后才解码，验证完整原RGB；with退出由权威守卫串行清缓存。"""
    result={}
    with layout.guarded_pixels(pack):
        for name,entry in sourceEntries.items():
            im=layout.load_rgb(entry['image'])
            if list(im.size)!=entry['originalSize'] or hashlib.sha256(im.tobytes()).hexdigest()!=entry['originalRgbSha256']:
                raise ValueError('reconstruction_mismatch: native full RGB '+name)
            result[name]=im
        if callback is not None:
            return callback(result)
    return result
