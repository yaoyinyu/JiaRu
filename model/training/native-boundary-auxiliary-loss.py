"""保留原软边界监督，仅增加低权重单调位移辅助项。"""
import importlib.util
from pathlib import Path

_spec=importlib.util.spec_from_file_location('native_auxiliary_displacement',Path(__file__).with_name('native-radial-overlap-loss.py'))
displacement=importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(displacement)
previous=displacement.previous
displacement_penalty=displacement.displacement_penalty


def objective(mask,presence,radius,truth,target_radius,boundary_band):
    return previous.objective(mask,presence,radius,truth,target_radius,boundary_band)+.5*displacement_penalty(radius,target_radius)
