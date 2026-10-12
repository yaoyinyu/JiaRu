"""二值adaptive平均的导出替代须保留窗口、奇数尺寸和参数。"""
import importlib.util,unittest
from pathlib import Path
import torch
import torch.nn.functional as F
R=Path(__file__).resolve().parents[1]
def load(n,file):
 sp=importlib.util.spec_from_file_location(n,R/'model/training'/file);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);return m
old=load('old_native_pool_test','native-multiscale-conditional-refiner.py');new=load('new_native_pool_test','native-multiscale-conditional-refiner-v2.py')
torch.set_num_threads(4)
class Tests(unittest.TestCase):
 def test_binary_adaptive_pool_exact_same_windows(self):
  for h,w in [(16,16),(31,37),(333,341),(721,719)]:
   torch.manual_seed(h*1000+w);seed=(torch.rand(1,1,h,w)>.5).float();reference=F.interpolate(seed,size=(h//4,w//4),mode='area')
   actual=new.pool_binary_seed(seed,h//4,w//4)
   self.assertTrue(torch.equal(actual,reference),(h,w,float((actual-reference).abs().max())))
 def test_initial_parameter_and_output_equality(self):
  torch.manual_seed(22);a=old.NativeConditionalMaskRefiner();torch.manual_seed(22);b=new.NativeConditionalMaskRefiner()
  self.assertTrue(all(torch.equal(a.state_dict()[k],b.state_dict()[k]) for k in a.state_dict()))
  x=torch.rand(1,4,31,37);x[:,3]=(x[:,3]>.5).float();y,p=a(x);z,q=b(x)
  self.assertTrue(torch.equal(y,z));self.assertTrue(torch.equal(p,q))
if __name__=='__main__':unittest.main()
