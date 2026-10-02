"""保存概率的固定域错像素和迁移统计；不执行模型或校准阈值。"""
import numpy as np


def summarize(base, probability, truth, band):
    if base.ndim!=2 or probability.shape!=base.shape or truth.shape!=base.shape or band.shape!=base.shape:
        raise ValueError('native2D matched shapes required')
    if base.dtype!=np.float32 or probability.dtype!=np.float32 or truth.dtype!=bool or band.dtype!=bool:
        raise ValueError('FP32 probabilities and bool truth/band required')
    for value in (base,probability):
        if not np.isfinite(value).all() or np.any((value<0)|(value>1)):raise ValueError('invalid probability')
    before=base>=.5;after=probability>=.5
    old_wrong=before!=truth;wrong=after!=truth
    fp=after&~truth;fn=~after&truth
    result={
        'falsePositiveInsideBand':int((fp&band).sum()),'falseNegativeInsideBand':int((fn&band).sum()),
        'falsePositiveOutsideBand':int((fp&~band).sum()),'falseNegativeOutsideBand':int((fn&~band).sum()),
        'correctedPixels':int((old_wrong&~wrong).sum()),'introducedPixels':int((~old_wrong&wrong).sum()),
        'persistentWrongPixels':int((old_wrong&wrong).sum()),'unchangedCorrectPixels':int((~old_wrong&~wrong).sum()),
        'wrongHighConfidenceFalsePositiveInsideBand':int((fp&band&(probability>=.9)).sum()),
        'wrongHighConfidenceFalseNegativeInsideBand':int((fn&band&(probability<=.1)).sum()),
        'wrongHighConfidenceFalsePositiveOutsideBand':int((fp&~band&(probability>=.9)).sum()),
        'wrongHighConfidenceFalseNegativeOutsideBand':int((fn&~band&(probability<=.1)).sum()),
        'totalPixels':int(truth.size),'oldWrongPixels':int(old_wrong.sum()),'currentWrongPixels':int(wrong.sum()),
    }
    assert result['correctedPixels']+result['persistentWrongPixels']==result['oldWrongPixels']
    assert result['introducedPixels']+result['persistentWrongPixels']==result['currentWrongPixels']
    assert sum(result[k] for k in ('falsePositiveInsideBand','falseNegativeInsideBand','falsePositiveOutsideBand','falseNegativeOutsideBand'))==result['currentWrongPixels']
    return result
