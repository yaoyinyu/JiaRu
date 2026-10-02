"""逐候选参数梯度的确定性统计；不执行模型或证明因果。"""
import numpy as np


def summarize(gradients, candidate_ids, positive_flags):
    values=np.asarray(gradients)
    if values.ndim!=2 or values.shape[0]!=len(candidate_ids) or len(positive_flags)!=len(candidate_ids) or len(set(candidate_ids))!=len(candidate_ids):
        raise ValueError('gradient identities/shape')
    if not np.isfinite(values).all():
        raise ValueError('nonfinite gradients')
    flags=np.asarray(positive_flags,dtype=bool)
    if not flags.any() or np.any(values[~flags]!=0):
        raise ValueError('positive denominator/empty gradients')
    positive=values[flags].astype(np.float64)
    norms=np.linalg.norm(positive,axis=1)
    if np.any(norms<=0):
        raise ValueError('positive gradients unexpectedly zero')
    normalized=positive/norms[:,None]
    cosines=np.clip(normalized@normalized.T,-1.,1.)
    pairs=cosines[np.triu_indices(len(positive),k=1)]
    mean=positive.mean(axis=0)
    mean_norm=float(np.linalg.norm(mean))
    # 所有45均值与34正均值只相差比例；空候选梯度零不改变方向。
    against=positive@mean
    aggregate_cosines=against/(norms*mean_norm) if mean_norm>0 else np.zeros_like(norms)
    ids=[identity for identity,flag in zip(candidate_ids,flags,strict=True) if flag]
    return {'positiveCount':int(flags.sum()),'emptyCount':int((~flags).sum()),
            'positiveGradientNormMinimum':float(norms.min()),'positiveGradientNormMedian':float(np.median(norms)),
            'positiveGradientNormMaximum':float(norms.max()),'positiveMeanGradientNorm':mean_norm,
            'meanGradientNormToMeanIndividualNorm':mean_norm/float(norms.mean()),
            'pairCount':len(pairs),'negativePairCount':int((pairs<0).sum()),
            'pairCosineMedian':float(np.median(pairs)) if len(pairs) else None,
            'pairCosineMinimum':float(pairs.min()) if len(pairs) else None,
            'pairCosineMaximum':float(pairs.max()) if len(pairs) else None,
            'positiveIds':ids,'pairwiseCosines':cosines.tolist(),
            'perPositive':[{'id':identity,'gradientNorm':float(norm),'cosineAgainstPositiveMean':float(cosine),
                            'dotAgainstPositiveMean':float(dot)} for identity,norm,cosine,dot in zip(ids,norms,aggregate_cosines,against,strict=True)],
            'opposedToPositiveMeanIds':[identity for identity,dot in zip(ids,against,strict=True) if dot<0],
            'scope':'Instantaneous raw total-loss parameter gradients, no AdamW preconditioning, optimizer step, causal or capacity claim.'}
