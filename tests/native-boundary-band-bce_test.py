"""原像素4px带与权威形态学一致，完整ROI监督仍存在。"""
import importlib.util,unittest
from pathlib import Path
import cv2,numpy as np,torch
import torch.nn.functional as F
R=Path(__file__).resolve().parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,R/path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
m=load('native_band_bce','model/training/native-boundary-band-bce.py')
class Tests(unittest.TestCase):
    def test_original_pixel_band_matches_frozen_morphology(self):
        truth=np.zeros((31,37),np.uint8);truth[0:24,8:27]=1
        edge=truth & ~cv2.erode(truth,np.ones((3,3),np.uint8))
        expected=cv2.dilate(edge,np.ones((9,9),np.uint8))
        actual=m.boundary_band(torch.tensor(truth)[None,None]).numpy()[0,0]
        np.testing.assert_array_equal(actual,expected)
    def test_band_normalization_and_global_gradient_retained(self):
        truth=torch.zeros(1,1,64,64);truth[:,:,20:44,20:44]=1
        logits=torch.zeros_like(truth,requires_grad=True)
        loss=F.binary_cross_entropy_with_logits(logits,truth)+m.boundary_band_bce(logits,truth)
        loss.backward();self.assertAlmostEqual(float(loss.detach()),2*np.log(2),places=6)
        self.assertGreater(float(logits.grad[0,0,3,3]),0)
        self.assertGreater(abs(float(logits.grad[0,0,20,25])),abs(float(logits.grad[0,0,3,3])))
    def test_empty_or_changed_radius_rejected(self):
        truth=torch.zeros(1,1,16,16)
        with self.assertRaises(ValueError):m.boundary_band_bce(truth,truth)
        with self.assertRaises(ValueError):m.boundary_band(truth,8)
    def test_trainer_positive_adds_only_band_and_reject_unchanged(self):
        old=load('band_old_trainer','model/training/train-native-conditional-capacity-v3.py')
        new=load('band_new_trainer','model/training/train-native-conditional-capacity-v4.py')
        net=load('band_train_model','model/training/native-multiscale-conditional-refiner-v3.py')
        plan={'loss':{'positivePresenceWeight':68/132,'rejectPresenceWeight':17.,'rejectPixelBceWeight':0,
                     'nativeBoundaryBandBce':{'radiusOriginalPixels':4,'coefficient':1.0}}}
        truth=torch.zeros(1,1,32,32);truth[:,:,10:23,10:23]=1
        logits=torch.zeros_like(truth);presence=torch.ones(1,1)
        expected=old.loss_for(net,logits,presence,truth,True,plan)+m.boundary_band_bce(logits,truth)
        self.assertTrue(torch.equal(new.loss_for(net,logits,presence,truth,True,plan),expected))
        self.assertTrue(torch.equal(new.loss_for(net,logits,presence,truth*0,False,plan),old.loss_for(net,logits,presence,truth*0,False,plan)))
    def test_next_coefficient_only_and_reject_unchanged(self):
        old=load('band_next_old','model/training/train-native-conditional-capacity-v4.py')
        new=load('band_next_new','model/training/train-native-conditional-capacity-v5.py')
        net=load('band_next_model','model/training/native-multiscale-conditional-refiner-v3.py')
        loss={'positivePresenceWeight':68/132,'rejectPresenceWeight':17.,'rejectPixelBceWeight':0,
              'nativeBoundaryBandBce':{'radiusOriginalPixels':4,'coefficient':1.0}}
        before={'loss':loss};after={'loss':dict(loss,nativeBoundaryBandBce={'radiusOriginalPixels':4,'coefficient':2.0})}
        truth=torch.zeros(1,1,32,32);truth[:,:,8:25,9:23]=1
        logits=torch.ones_like(truth)*.25;presence=torch.ones(1,1)
        expected=old.loss_for(net,logits,presence,truth,True,before)+m.boundary_band_bce(logits,truth)
        self.assertTrue(torch.allclose(new.loss_for(net,logits,presence,truth,True,after),expected,rtol=0,atol=2e-7))
        self.assertTrue(torch.equal(new.loss_for(net,logits,presence,truth*0,False,after),old.loss_for(net,logits,presence,truth*0,False,before)))
    def test_coefficient4_retains_global_gradient_and_negative_objective(self):
        old=load('band4_old','model/training/train-native-conditional-capacity-v5.py')
        new=load('band4_new','model/training/train-native-conditional-capacity-v6.py')
        net=load('band4_model','model/training/native-multiscale-conditional-refiner-v3.py')
        loss={'positivePresenceWeight':68/132,'rejectPresenceWeight':17.,'rejectPixelBceWeight':0,
              'nativeBoundaryBandBce':{'radiusOriginalPixels':4,'coefficient':2.0}}
        before={'loss':loss};after={'loss':dict(loss,nativeBoundaryBandBce={'radiusOriginalPixels':4,'coefficient':4.0})}
        truth=torch.zeros(1,1,64,64);truth[:,:,20:44,20:44]=1
        logits=torch.zeros_like(truth,requires_grad=True);presence=torch.ones(1,1,requires_grad=True)
        base=old.loss_for(net,logits,presence,truth,True,before)
        final=new.loss_for(net,logits,presence,truth,True,after)
        self.assertTrue(torch.allclose(final,base+2*m.boundary_band_bce(logits,truth),rtol=0,atol=5e-7))
        final.backward();self.assertGreater(float(logits.grad[0,0,3,3]),0)
        self.assertTrue(torch.equal(new.loss_for(net,logits,presence,truth*0,False,after),old.loss_for(net,logits,presence,truth*0,False,before)))
if __name__=='__main__':unittest.main()
