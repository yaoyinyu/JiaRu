"""新系数只强化正例边界项，不改变拒识目标或存在性权重。"""
import importlib.util,unittest
from pathlib import Path
import torch
R=Path(__file__).resolve().parents[1]
def load(n,file):
 sp=importlib.util.spec_from_file_location(n,R/'model/training'/file);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);return m
t=load('native_weight_trainer','train-native-conditional-capacity-v2.py');m=load('native_weight_model','native-multiscale-conditional-refiner-v3.py')
torch.set_num_threads(4)
class Tests(unittest.TestCase):
 def test_positive_only_extra_boundary_loss(self):
  plan={'loss':{'positivePresenceWeight':.5151515151515151,'rejectPresenceWeight':17.,'nativeBoundaryWeight':.2}}
  logits=torch.randn(1,1,19,23,requires_grad=True);presence=torch.ones(1,1,requires_grad=True);truth=torch.zeros_like(logits);truth[:,:,5:15,7:17]=1
  old=t.loss_for(m,logits,presence,truth,True,plan);plan['loss']['nativeBoundaryWeight']=1.;new=t.loss_for(m,logits,presence,truth,True,plan)
  edge=1-m.candidate_loss.__globals__['boundary'].soft_boundary_iou_per_instance(logits.sigmoid(),truth,{'nearBoundaryKernel':5,'epsilon':1e-6})
  self.assertTrue(torch.allclose(new-old,.8*edge.mean(),atol=1e-6));new.backward();self.assertTrue(torch.isfinite(logits.grad).all())
 def test_empty_loss_identical(self):
  logits=torch.randn(1,1,19,23);presence=torch.ones(1,1);truth=torch.zeros_like(logits);plan={'loss':{'positivePresenceWeight':.5151515151515151,'rejectPresenceWeight':17.,'nativeBoundaryWeight':.2}}
  old=t.loss_for(m,logits,presence,truth,False,plan);plan['loss']['nativeBoundaryWeight']=1.;new=t.loss_for(m,logits,presence,truth,False,plan)
  self.assertTrue(torch.equal(old,new))
if __name__=='__main__':unittest.main()
