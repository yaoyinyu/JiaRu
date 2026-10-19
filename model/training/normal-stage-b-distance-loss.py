"""完整原图坐标中的边界距离辅助监督；不改变部署输出、先验或阈值。"""
import numpy as np
import cv2
import torch
import torch.nn.functional as F


def build_distance_target(full_truth, crop_box, radius=4.0, scale=2.0):
    """完整原图上计算有符号距离，再无缩放取原生ROI；正值代表甲面。"""
    truth=np.asarray(full_truth)
    if truth.ndim!=2 or truth.dtype!=np.bool_ or not truth.any() or truth.all():
        raise ValueError('complete nonempty boolean source truth required')
    if not np.isfinite([radius,scale]).all() or radius<=0 or scale<=0:
        raise ValueError('positive source-pixel radius and scale required')
    if len(crop_box)!=4 or any(type(x) is not int for x in crop_box):
        raise ValueError('integer native crop required')
    x0,y0,x1,y1=crop_box;h,w=truth.shape
    if not (0<=x0<x1<=w and 0<=y0<y1<=h) or int(truth[y0:y1,x0:x1].sum())!=int(truth.sum()):
        raise ValueError('ROI must contain complete assigned truth')
    # 外部补零仅定义图像边界；训练目标与输入仍保持完整原像素域。
    padded=np.pad(truth.astype(np.uint8),1)
    inside=cv2.distanceTransform(padded,cv2.DIST_L2,cv2.DIST_MASK_PRECISE)[1:-1,1:-1]
    outside=cv2.distanceTransform(1-padded,cv2.DIST_L2,cv2.DIST_MASK_PRECISE)[1:-1,1:-1]
    edge=truth&~cv2.erode(truth.astype(np.uint8),np.ones((3,3),np.uint8),borderType=cv2.BORDER_CONSTANT,borderValue=0).astype(bool)
    distance=cv2.distanceTransform((~edge).astype(np.uint8),cv2.DIST_L2,cv2.DIST_MASK_PRECISE)
    target=np.clip((inside-outside)/np.float32(scale),-4,4).astype(np.float32)
    band=distance<=radius
    target=target[y0:y1,x0:x1].copy();band=band[y0:y1,x0:x1].copy()
    if not band.any() or not np.isfinite(target).all():raise ValueError('invalid distance target')
    return target,band


def distance_band_loss(logits, target, band):
    if logits.shape!=target.shape or logits.shape!=band.shape or logits.dtype!=torch.float32 or target.dtype!=torch.float32 or band.dtype!=torch.bool:
        raise ValueError('native float32 logits/target and boolean band must align')
    if not bool(band.any()) or not bool(torch.isfinite(logits).all()) or not bool(torch.isfinite(target).all()):
        raise ValueError('finite nonempty distance band required')
    return F.smooth_l1_loss(logits[band],target[band],beta=1.0)


def objective(logits,presence,truth,positive,counts,base,boundary,target=None,band=None):
    result=base.objective(logits,presence,truth,positive,counts,boundary)
    # 空目标只监督同一个条件候选的presence；不得把RGB内邻甲当背景训练。
    if positive:
        if target is None or band is None:raise ValueError('positive distance supervision missing')
        result=result+0.25*distance_band_loss(logits,target,band)
    return result
