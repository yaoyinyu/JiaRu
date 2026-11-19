"""以冻结训练目标哈希选择正权重，保留原侧缘目标与全部训练样本。"""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import hashlib
import math
import torch

_spec = spec_from_file_location('sample_weighted_previous', Path(__file__).with_name('native-side-boundary-loss.py'))
previous = module_from_spec(_spec)
_spec.loader.exec_module(previous)
_configured = None


class FrozenSampleWeightedObjective:
    def __init__(self, weights, base_objective=None):
        if not weights:
            raise ValueError('nonempty frozen training weights required')
        self.weights = dict(weights)
        for key, value in self.weights.items():
            if (not isinstance(key, str) or len(key) != 64 or any(c not in '0123456789abcdef' for c in key)
                    or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0):
                raise ValueError('finite positive weights and SHA-256 target keys required')
        self.base_objective = base_objective or previous.objective

    def multiplier(self, target_radius):
        if (target_radius.dtype != torch.float32 or target_radius.shape != (1, 2048)
                or not bool(torch.isfinite(target_radius).all())):
            raise ValueError('one finite float32 2048-bin training target required')
        key = hashlib.sha256(target_radius.detach().cpu().contiguous().numpy().tobytes()).hexdigest()
        if key not in self.weights:
            raise ValueError('training target absent from frozen weight recipe')
        return self.weights[key]

    def objective(self, mask, presence, radius, truth, target_radius, boundary_band):
        weight = self.multiplier(target_radius)
        value = self.base_objective(mask, presence, radius, truth, target_radius, boundary_band)
        return value * value.new_tensor(weight)


def configure(weights):
    global _configured
    _configured = FrozenSampleWeightedObjective(weights)


def multiplier(target_radius):
    if _configured is None:
        raise RuntimeError('frozen weight recipe must be configured before training')
    return _configured.multiplier(target_radius)


def objective(*args):
    if _configured is None:
        raise RuntimeError('frozen weight recipe must be configured before training')
    return _configured.objective(*args)
