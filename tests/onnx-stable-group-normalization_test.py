"""分块统计转换保留epsilon和非平凡学习仿射；拒绝非预期InstanceNorm。"""
import importlib.util,tempfile,unittest
from pathlib import Path
import torch
from torch import nn
import numpy as np
import onnxruntime as ort
R=Path(__file__).resolve().parents[1]
sp=importlib.util.spec_from_file_location('stable_gn_tests',R/'model/training/onnx-stable-group-normalization.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
torch.set_num_threads(4)
class Norms(nn.Module):
 def __init__(self,groups=4):
  super().__init__();self.norms=nn.ModuleList([nn.GroupNorm(groups,16) for _ in range(10)])
  with torch.no_grad():
   for i,n in enumerate(self.norms):n.weight.copy_(torch.linspace(.3,1.7,16));n.bias.copy_(torch.linspace(-.2,.4,16)+i*.01)
 def forward(self,x):
  for norm in self.norms:x=norm(x)
  return x
class Tests(unittest.TestCase):
 def test_all10_affine_normalizations_preserved(self):
  with tempfile.TemporaryDirectory() as folder:
   torch.manual_seed(42);model=Norms().eval();x=torch.randn(1,16,31,37);path=Path(folder)/'norms.onnx'
   torch.onnx.export(model,x,str(path),opset_version=18,dynamo=False,input_names=['x'])
   rewritten=m.rewrite(path);self.assertEqual(len(rewritten),10)
   options=ort.SessionOptions();options.log_severity_level=3
   actual=ort.InferenceSession(str(path),sess_options=options,providers=['CPUExecutionProvider']).run(None,{'x':x.numpy()})[0]
   with torch.no_grad():expected=model(x).numpy()
   self.assertLessEqual(float(np.abs(actual-expected).max()),1e-4)
 def test_wrong_inner_group_contract_rejected(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'wrong.onnx';torch.onnx.export(Norms(groups=2).eval(),torch.rand(1,16,16,16),str(path),opset_version=18,dynamo=False)
   original=path.read_bytes()
   with self.assertRaises(ValueError):m.rewrite(path)
   self.assertEqual(path.read_bytes(),original)
if __name__=='__main__':unittest.main()
