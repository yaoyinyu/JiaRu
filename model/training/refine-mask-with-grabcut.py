"""原尺寸、受限边界带的 GrabCut 开发工具；不接受真值，不改变模型 RAW。

使用方须串行调用：OpenCV 的线程和 RNG 设置是进程级状态。
算法失败抛错，缺少可靠种子则显式 abstained；均不得冒充自动成功。
"""
import cv2
import numpy as np
from scipy.ndimage import binary_dilation, binary_erosion


def constraints(mask, radius=8):
    if mask.dtype != np.bool_ or mask.ndim != 2 or min(mask.shape) < 1:
        raise ValueError('mask must be a nonempty boolean HW array')
    if type(radius) is not int or not 1 <= radius <= 32:
        raise ValueError('radius must be an integer in 1..32 original pixels')
    square = np.ones((3, 3), bool)
    inner = binary_erosion(mask, square, iterations=radius, border_value=0)
    outer = binary_dilation(mask, square, iterations=radius, border_value=0)
    return inner, outer


def refine(rgb, mask, *, presence_accepted, radius=8, iterations=3):
    if rgb.dtype != np.uint8 or rgb.shape != (*mask.shape, 3):
        raise ValueError('expected original RGB uint8 HWC aligned with mask')
    if type(presence_accepted) is not bool or type(iterations) is not int or not 1 <= iterations <= 10:
        raise ValueError('invalid presence or iteration contract')
    inner, outer = constraints(mask, radius)
    if not presence_accepted:
        return np.zeros_like(mask), 'rejected'
    if not mask.any():
        return mask.copy(), 'empty'
    # 至少保留五个确定的两类样本，拒绝凭空制造种子或将执行失败当作空目标。
    if inner.sum() < 5 or (~outer).sum() < 5:
        return mask.copy(), 'abstained_missing_hard_seeds'
    labels = np.where(mask, cv2.GC_PR_FGD, cv2.GC_PR_BGD).astype(np.uint8)
    labels[inner] = cv2.GC_FGD
    labels[~outer] = cv2.GC_BGD
    cv2.setNumThreads(1)
    cv2.ocl.setUseOpenCL(False)
    cv2.setRNGSeed(0)
    background = np.zeros((1, 65), np.float64)
    foreground = np.zeros((1, 65), np.float64)
    cv2.grabCut(np.ascontiguousarray(rgb[..., ::-1]), labels, None,
                background, foreground, iterations, cv2.GC_INIT_WITH_MASK)
    result = (labels == cv2.GC_FGD) | (labels == cv2.GC_PR_FGD)
    if not result[inner].all() or result[~outer].any():
        raise RuntimeError('GrabCut violated hard seeds')
    return result, 'refined'
