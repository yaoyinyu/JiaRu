"""合成数据验证归一化、空带与明确传带；不依赖真实素材或训练产物。"""
import importlib.util
from pathlib import Path
import unittest
import torch
import torch.nn.functional as F


def module(name, filename):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).resolve().parents[1]/'model/training'/filename)
    result=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


m=module('band_loss_fixture','native-band-objective-loss.py')
h=module('band_loss_head_fixture','native-context-nail-refinement.py')
torch.set_num_threads(2)


class NativeBandObjectiveTests(unittest.TestCase):
    def fixture(self):
        logits=torch.linspace(-2,2,60).reshape(1,1,6,10).requires_grad_(True)
        target=torch.zeros_like(logits)
        target[:,:,2:5,3:7]=1
        band=torch.zeros_like(logits,dtype=torch.bool)
        band[:,:,1:5,2:8]=True
        return logits,target,band

    def test_only_bce_domain_changes(self):
        logits,target,band=self.fixture()
        old,old_parts=m.previous.conditional_mask_loss(logits,target,boundary_weight=.2)
        new,parts=m.conditional_mask_loss(logits,target,editable_band=band,boundary_weight=.2)
        for key in ('positiveDice','positiveBoundaryProxy','positiveCount','emptyCount'):
            self.assertEqual(parts[key],old_parts[key])
        pixels=F.binary_cross_entropy_with_logits(logits,target,reduction='none')
        self.assertAlmostEqual(parts['bce'],pixels[band].mean().item(),places=7)
        self.assertTrue(torch.allclose(new-old,pixels[band].mean()-pixels.mean(),atol=1e-7,rtol=0))

    def test_exact_bce_gradient_scaling(self):
        logits,target,band=self.fixture()
        pixels=F.binary_cross_entropy_with_logits(logits,target,reduction='none')
        full_grad=torch.autograd.grad(pixels.mean(),logits,retain_graph=True)[0]
        band_grad=torch.autograd.grad(pixels[band].mean(),logits)[0]
        factor=logits.numel()/band.sum().item()
        self.assertTrue(torch.allclose(band_grad[band],full_grad[band]*factor,atol=1e-7,rtol=0))
        self.assertEqual(torch.count_nonzero(band_grad[~band]).item(),0)

    def test_empty_band_preserves_original_objective(self):
        logits,target,_=self.fixture()
        target.zero_()
        band=torch.zeros_like(logits,dtype=torch.bool)
        old,_=m.previous.conditional_mask_loss(logits,target,boundary_weight=.2)
        new,parts=m.conditional_mask_loss(logits,target,editable_band=band,boundary_weight=.2)
        self.assertTrue(torch.equal(old,new))
        old_grad=torch.autograd.grad(old,logits,retain_graph=True)[0]
        new_grad=torch.autograd.grad(new,logits)[0]
        self.assertTrue(torch.equal(old_grad,new_grad))
        self.assertEqual(parts['editablePixelsPerCandidate'],[0])

    def test_composition_preserves_zero_outside_delta_gradient(self):
        logits,target,band=self.fixture()
        base=logits.detach().sigmoid()
        delta=torch.zeros_like(logits,requires_grad=True)
        composed=h.compose_native_logits(base,delta,band)
        loss,_=m.conditional_mask_loss(composed,target,editable_band=band,boundary_weight=.2)
        loss.backward()
        self.assertTrue(torch.isfinite(delta.grad).all())
        self.assertEqual(torch.count_nonzero(delta.grad[~band]).item(),0)
        self.assertGreater(torch.count_nonzero(delta.grad[band]).item(),0)

    def test_mixed_batch_uses_per_candidate_band_and_empty_fallback(self):
        logits,target,band=self.fixture()
        batch=torch.cat((logits,logits+1),dim=0)
        truth=torch.cat((target,torch.zeros_like(target)),dim=0)
        bands=torch.cat((band,torch.zeros_like(band)),dim=0)
        _,parts=m.conditional_mask_loss(batch,truth,editable_band=bands)
        pixels=F.binary_cross_entropy_with_logits(batch,truth,reduction='none')
        expected=(pixels[0][bands[0]].mean()+pixels[1].mean())/2
        self.assertAlmostEqual(parts['bce'],expected.item(),places=7)

    def test_invalid_band_and_nonfinite_rejected(self):
        logits,target,band=self.fixture()
        for bad in (band.float(),band[:,:,:,:-1]):
            with self.assertRaises(ValueError):
                m.conditional_mask_loss(logits,target,editable_band=bad)
        invalid=logits.detach().clone()
        invalid[0,0,0,0]=float('nan')
        with self.assertRaises(ValueError):
            m.conditional_mask_loss(invalid,target,editable_band=band)


if __name__=='__main__':
    unittest.main()
