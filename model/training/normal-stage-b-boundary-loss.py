"""正常训练边界目标：完整原尺寸真值与固定4原像素边缘带。"""
import importlib.util
from pathlib import Path
HERE=Path(__file__).resolve().parent
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
band=load(HERE/'native-boundary-band-bce.py','normal_original_band')
boundary=load(HERE/'development-cycle-016-soft-boundary-iou.py','normal_original_boundary')
boundary_band_bce=band.boundary_band_bce
def soft_boundary(probability,truth):
    return (1-boundary.soft_boundary_iou_per_instance(probability.float(),truth.float(),{'nearBoundaryKernel':5,'epsilon':1e-6})).mean()
