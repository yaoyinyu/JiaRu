"""原尺寸RGB光照增强；不改变粗mask、真值、坐标或原始素材。"""
import numpy as np


def parameters(epoch, ordinal):
    if not (1 <= epoch <= 60 and 1 <= ordinal <= 154):
        raise ValueError('frozen training scope')
    if ((epoch - 1) // 3 + ordinal - 1) % 3 == 0:
        return {'brightness': 1., 'contrast': 1., 'gains': [1., 1., 1.]}
    rng = np.random.default_rng(np.random.SeedSequence([20261020, epoch, ordinal]))
    return {'brightness': float(rng.uniform(.7, 1.3)),
            'contrast': float(rng.uniform(.85, 1.15)),
            'gains': rng.uniform(.9, 1.1, 3).tolist()}


STRESS = {
    'dim_warm': {'brightness': .72, 'contrast': .9, 'gains': [1.08, 1., .92]},
    'bright_cool': {'brightness': 1.22, 'contrast': 1.1, 'gains': [.94, 1., 1.06]},
}


def apply(rgb, spec):
    if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError('native uint8 RGB required')
    b, c = spec['brightness'], spec['contrast']
    gains = np.asarray(spec['gains'], dtype=np.float32)
    if not (.7 <= b <= 1.3 and .85 <= c <= 1.15 and gains.shape == (3,) and
            np.isfinite(gains).all() and (gains >= .9).all() and (gains <= 1.1).all()):
        raise ValueError('photometric policy')
    if b == c == 1. and np.array_equal(gains, np.ones(3, dtype=np.float32)):
        return rgb.copy()
    v = rgb.astype(np.float32)
    v = ((v - np.float32(127.5)) * np.float32(c) + np.float32(127.5))
    v = v * np.float32(b) * gains[None, None, :]
    return np.rint(v).clip(0, 255).astype(np.uint8)
