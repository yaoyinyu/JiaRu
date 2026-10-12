"""候选拒识的最终空输出要求保持；mask梯度与分类梯度显式分支。"""
import importlib.util,unittest
from pathlib import Path
import torch
R=Path(__file__).resolve().parents[1]
def load(n,file):
 sp=importlib.util.spec_from_file_location(n,R/'model/training'/file);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);return m
t=load('reject_loss_trainer','train-native-conditional-capacity-v3.py');old=load('original_loss_trainer','train-native-conditional-capacity.py');m=load('reject_loss_model','native-multiscale-conditional-refiner-v3.py')
torch.set_num_threads(4)
class Tests(unittest.TestCase):
 def plan(self):return {'loss':{'positivePresenceWeight':68/132,'rejectPresenceWeight':17.,'rejectPixelBceWeight':0}}
 def test_positive_loss_unchanged(self):
  logits=torch.rand(1,1,19,23);presence=torch.ones(1,1);truth=(torch.rand_like(logits)>.5).float();plan=self.plan()
  self.assertTrue(torch.equal(t.loss_for(m,logits,presence,truth,True,plan),old.loss_for(m,logits,presence,truth,True,plan)))
 def test_negative_has_presence_gradient_and_no_internal_pixel_gradient(self):
  logits=torch.ones(1,1,19,23,requires_grad=True);presence=torch.ones(1,1,requires_grad=True);truth=torch.zeros_like(logits)
  loss=t.loss_for(m,logits,presence,truth,False,self.plan());loss.backward();self.assertIsNone(logits.grad);self.assertTrue(torch.isfinite(presence.grad).all())
  self.assertFalse(m.decode(logits.detach().numpy()[0,0],-1).any())
if __name__=='__main__':unittest.main()
