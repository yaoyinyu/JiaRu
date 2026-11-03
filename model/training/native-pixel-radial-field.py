"""以原像素距离格定义径向场；maskLogit=radius[angleBin]-distance，零阈值解码。"""
import math
import numpy as np


def lattice(shape, center, angular_samples=2048):
    if len(shape)!=2 or any(type(x) is not int or x<=0 for x in shape):
        raise ValueError('positive native shape required')
    center=np.asarray(center,np.float64)
    if center.shape!=(2,) or not np.isfinite(center).all() or type(angular_samples) is not int or angular_samples<16:
        raise ValueError('finite center and angular samples >=16 required')
    y,x=np.indices(shape,dtype=np.float64);x-=center[0];y-=center[1]
    bins=np.floor(np.mod(np.arctan2(y,x),2*math.pi)*(angular_samples/(2*math.pi))).astype(np.int32)
    bins=np.minimum(bins,angular_samples-1)
    return bins,np.hypot(x,y).astype(np.float32)


def fit_radius(mask, bins, distance, angular_samples=2048):
    """完整二值甲面给出每角度最外正像素与其外第一个背景像素之间的半径。"""
    if mask.dtype!=np.bool_ or bins.dtype!=np.int32 or distance.dtype!=np.float32 or mask.shape!=bins.shape or mask.shape!=distance.shape or not mask.any():
        raise ValueError('aligned complete boolean mask/int32 bins/float32 distances required')
    if bins.min()<0 or bins.max()>=angular_samples or not np.isfinite(distance).all() or distance.min()<0:
        raise ValueError('finite radial coordinate domain required')
    positive=np.full(angular_samples,-np.inf,np.float32)
    np.maximum.at(positive,bins[mask],distance[mask])
    known=np.flatnonzero(np.isfinite(positive))
    if not len(known):raise ValueError('no foreground radii')
    all_bins=np.arange(angular_samples)
    if len(known)<angular_samples:
        positive=np.interp(all_bins,np.concatenate((known-angular_samples,known,known+angular_samples)),np.tile(positive[known],3)).astype(np.float32)
    next_background=np.full(angular_samples,np.inf,np.float32)
    outside=(~mask)&(distance>positive[bins]);np.minimum.at(next_background,bins[outside],distance[outside])
    outer=np.where(np.isfinite(next_background),next_background,positive+np.float32(1.))
    return (positive+(outer-positive)*np.float32(.5)).astype(np.float32)


def logits(radius, bins, distance):
    if radius.ndim!=1 or radius.dtype!=np.float32 or bins.dtype!=np.int32 or distance.dtype!=np.float32 or bins.shape!=distance.shape:
        raise ValueError('frozen radial storage domains required')
    if bins.min()<0 or bins.max()>=len(radius) or not np.isfinite(radius).all() or np.any(radius<0):
        raise ValueError('invalid radius domain')
    return radius[bins]-distance
