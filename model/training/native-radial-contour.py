"""原图坐标中的候选条件径向轮廓；只提供几何表示，不作自动质量裁决。"""
import math

import numpy as np
from PIL import Image, ImageDraw


def ray_intersections(polygons, center, angles=2048):
    """每条射线取完整多边形最远交点，并报告非单交点射线。"""
    c = np.asarray(center, np.float64)
    if c.shape != (2,) or not np.isfinite(c).all() or type(angles) is not int or angles < 16:
        raise ValueError('finite center and angular count >=16 required')
    theta = np.arange(angles, dtype=np.float64) * (2 * math.pi / angles)
    directions = np.stack((np.cos(theta), np.sin(theta)), axis=1)
    radii = np.zeros(angles, np.float64)
    counts = np.zeros(angles, np.int64)
    for polygon in polygons:
        points = np.asarray(polygon, np.float64)
        if points.ndim != 2 or points.shape[1] != 2 or len(points) < 3 or not np.isfinite(points).all():
            raise ValueError('finite polygon with >=3 points required')
        start = points - c; edge = np.roll(points, -1, axis=0) - points
        denominator = directions[:, 0:1] * edge[None, :, 1] - directions[:, 1:2] * edge[None, :, 0]
        safe = np.where(np.abs(denominator) > 1e-12, denominator, 1.)
        distance = (start[:, 0] * edge[:, 1] - start[:, 1] * edge[:, 0])[None, :] / safe
        fraction = (start[None, :, 0] * directions[:, 1:2] - start[None, :, 1] * directions[:, 0:1]) / safe
        # 半开边段统一接纳起点；避免顶点交点因三角函数舍入被两条边重复计数。
        valid = (np.abs(denominator) > 1e-12) & (distance >= 0) & (fraction >= -1e-12) & (fraction < 1 - 1e-12)
        radii = np.maximum(radii, np.where(valid, distance, 0.).max(axis=1))
        counts += valid.sum(axis=1)
    return radii, counts


def vertices(center, radii):
    c = np.asarray(center, np.float64); values = np.asarray(radii)
    if c.shape != (2,) or values.ndim != 1 or len(values) < 16 or not np.isfinite(values).all() or np.any(values < 0):
        raise ValueError('valid center and nonnegative radial field required')
    theta = np.arange(len(values), dtype=np.float64) * (2 * math.pi / len(values))
    return np.stack((c[0] + values * np.cos(theta), c[1] + values * np.sin(theta)), axis=1)


def rasterize(center, radii, shape):
    if len(shape) != 2 or any(type(x) is not int or x <= 0 for x in shape):
        raise ValueError('positive native height/width required')
    image = Image.new('L', (shape[1], shape[0]))
    ImageDraw.Draw(image).polygon([tuple(p) for p in vertices(center, radii)], fill=255)
    return np.asarray(image) > 0
