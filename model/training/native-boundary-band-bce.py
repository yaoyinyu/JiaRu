"""在完整ROI像素损失之外强化固定原像素甲缘带；不裁减任何目标。"""
import torch
import torch.nn.functional as F

def boundary_band(truth, radius=4):
    if radius != 4:raise ValueError('frozen original-pixel radius4')
    value=truth.float()
    eroded=-F.max_pool2d(-value,3,stride=1,padding=1)
    edge=(value-eroded).clamp(0,1)
    return F.max_pool2d(edge,2*radius+1,stride=1,padding=radius)

def boundary_band_bce(logits,truth,radius=4):
    band=boundary_band(truth,radius)
    if not bool((band.sum()>0).detach()):raise ValueError('positive boundary band missing')
    pixel=F.binary_cross_entropy_with_logits(logits.float(),truth.float(),reduction='none')
    return (pixel*band).sum()/band.sum()
