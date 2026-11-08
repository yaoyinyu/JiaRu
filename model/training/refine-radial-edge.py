"""保存半径的产品层处理；原始半径/二值mask由调用方单独保留。"""
import math
import numpy as np
from scipy.ndimage import maximum_filter, minimum_filter


def smooth_radius(radius, arc_pixels=2., max_shift=.5):
    radius = np.asarray(radius)
    if radius.dtype != np.float32 or radius.ndim != 1 or not np.isfinite(radius).all():
        raise ValueError('finite float32 radius required')
    n = len(radius)
    result = radius.copy()
    for i, value in enumerate(radius):
        half = min(15, max(0, int(math.floor(arc_pixels*n/(2*math.pi*max(1., float(value)))/2))))
        if half:
            target = float(np.mean(radius[(np.arange(i-half, i+half+1) % n)].astype(np.float64)))
            result[i] = np.float32(float(value) + max(-max_shift, min(max_shift, target-float(value))))
    return result


def coverage_alpha(radius, center, hard, samples=4):
    if samples not in (2, 4, 8):
        raise ValueError('coverage samples must be 2,4,8')
    if hard.dtype != np.bool_ or hard.ndim != 2 or radius.dtype != np.float32 or not np.isfinite(radius).all():
        raise ValueError('invalid radius or binary mask')
    alpha = hard.astype(np.uint8)*255
    band = maximum_filter(hard, size=3, mode='constant') != minimum_filter(hard, size=3, mode='constant')
    ys, xs = np.nonzero(band)
    count = np.zeros(len(xs), np.int32)
    for oy in (np.arange(samples)+.5)/samples-.5:
        for ox in (np.arange(samples)+.5)/samples-.5:
            dx = xs.astype(np.float64)+ox-float(center[0])
            dy = ys.astype(np.float64)+oy-float(center[1])
            angle = np.mod(np.arctan2(dy, dx), 2*math.pi)
            bins = np.minimum(len(radius)-1, np.floor(angle*(len(radius)/(2*math.pi))).astype(np.int64))
            # JS侧同样使用double亚像素几何，最终alpha采用显式half-up取整。
            count += radius[bins].astype(np.float64) >= np.hypot(dx, dy)
    alpha[ys, xs] = np.floor(count.astype(np.float64)*255/(samples*samples)+.5).astype(np.uint8)
    return alpha
