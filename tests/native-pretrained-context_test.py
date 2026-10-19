"""冻结骨干、原图坐标和零残差继承；fixture不依赖真实权重或图片。"""
import importlib.util,json,sys,unittest
from pathlib import Path
import numpy as np
import torch
from torch import nn
import torch.nn.functional as F
P=Path(__file__).resolve().parents[1]/'model/training/native-pretrained-context-refiner.py'
s=importlib.util.spec_from_file_location('pretrained_context_test',P);net=importlib.util.module_from_spec(s);s.loader.exec_module(net)
COUNTS={'oldForwards':0,'newForwards':0,'guardRejections':0}

class ToyBackbone(nn.Module):
    channels=(4,8,8);strides=(8,16,32)
    def __init__(self):
        super().__init__();self.stages=nn.ModuleList([nn.Sequential(nn.Conv2d(3,c,1),nn.BatchNorm2d(c)) for c in self.channels])
    def forward(self,rgb):return tuple(layer(F.avg_pool2d(rgb,s)) for layer,s in zip(self.stages,self.strides,strict=True))

class PretrainedContextTests(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(2);torch.manual_seed(20261019);self.old=net.base.NativeConditionalMaskRefiner().float()
        with torch.no_grad():self.old.delta.weight.uniform_(-.05,.05);self.old.delta.bias.fill_(.17);self.old.presence.weight.uniform_(-.03,.03)
        self.new=net.NativeConditionalMaskRefiner(ToyBackbone()).float();self.new.load_refiner_state(self.old.state_dict())
    def sample(self,h,w):
        rng=np.random.default_rng(h*1000+w);rgb=rng.integers(0,256,(h,w,3),dtype=np.uint8);seed=(rng.random((h,w))>.6).astype(np.uint8)*255
        return torch.from_numpy(net.pack(rgb,seed))[None]
    def call(self,which,values):
        result=getattr(self,which)(values);COUNTS[which+'Forwards']+=1;return result
    def test_zero_residual_exact_on_minimum_and_odd_sizes(self):
        for h,w in [(16,16),(33,47),(64,64),(129,131)]:
            x=self.sample(h,w)
            with torch.inference_mode():a=self.call('old',x);b=self.call('new',x)
            self.assertTrue(all(torch.equal(u,v) for u,v in zip(a,b)));self.assertEqual(tuple(b[0].shape),(1,1,h,w))
    def test_nonzero_semantic_path_changes_mask_only(self):
        with torch.no_grad():
            for p in self.new.semantic_projections:p.weight.uniform_(-.1,.1)
        x=self.sample(65,79)
        with torch.inference_mode():a=self.call('old',x);b=self.call('new',x)
        self.assertFalse(torch.equal(a[0],b[0]));self.assertTrue(torch.equal(a[1],b[1]))
    def test_positive_gradients_and_frozen_bn_survive_train_and_requires_grad(self):
        self.new.train().requires_grad_(True);before={k:v.clone() for k,v in self.new.semantic_backbone.state_dict().items()};a,b=self.call('new',self.sample(65,79));(F.binary_cross_entropy_with_logits(a,torch.ones_like(a))+b.square().mean()).backward();trainable=[p for p in self.new.parameters() if p.requires_grad]
        self.assertEqual(len(trainable),60);self.assertTrue(all(p.grad is not None and torch.isfinite(p.grad).all() for p in trainable));self.assertTrue(all(p.grad is None and not p.requires_grad for p in self.new.semantic_backbone.parameters()));self.assertFalse(self.new.semantic_backbone.training)
        self.assertTrue(all(torch.equal(v,self.new.semantic_backbone.state_dict()[k]) for k,v in before.items()));self.assertTrue(all(bool(p.weight.grad.abs().max()>0) for p in self.new.semantic_projections))
    def test_reject_does_not_train_decoder_or_semantic_residual(self):
        self.new.train().requires_grad_(True);a,b=self.call('new',self.sample(65,79));b.square().mean().backward();used=unused=0
        for name,p in self.new.named_parameters():
            if not p.requires_grad:self.assertIsNone(p.grad)
            elif name.startswith(('enc1.','enc2.','enc3.','presence.')):self.assertIsNotNone(p.grad);used+=1
            else:self.assertIsNone(p.grad);unused+=1
        self.assertEqual((used,unused),(20,40))
    def test_all_rgb_integer_values_roundtrip_without_resizing(self):
        rgb=np.stack([np.arange(256,dtype=np.uint8).reshape(16,16)]*3,axis=2);packed=net.pack(rgb,np.zeros((16,16),np.uint8));recovered=(net.semantic_rgb(torch.from_numpy(packed)[None])*255).round().to(torch.uint8)
        self.assertTrue(torch.equal(recovered[0],torch.from_numpy(rgb.transpose(2,0,1))))
    def test_coordinate_ramp_is_independent_of_padding_extent(self):
        y=torch.arange(7)*4+1.5;x=torch.arange(7)*4+1.5;expected=(y[:,None]+x[None,:])[None,None]
        for stride in [8,16,32]:
            values=[]
            for extent in [64,96]:
                a=torch.arange(extent//stride,dtype=torch.float32)*stride;feature=(a[:,None]+a[None,:])[None,None];values.append(net.sample_at_native_quarter(feature,stride,7,7))
            self.assertTrue(torch.equal(values[0],expected));self.assertTrue(torch.equal(values[0],values[1]))
    def test_bad_weight_state_rejected_without_mutation(self):
        before={k:v.clone() for k,v in self.new.state_dict().items()};bad=dict(self.old.state_dict());bad['delta.weight']=torch.zeros(5)
        with self.assertRaises(ValueError):self.new.load_refiner_state(bad)
        self.assertTrue(all(torch.equal(v,self.new.state_dict()[k]) for k,v in before.items()))
    def test_invalid_domain_rejected_before_backbone(self):
        for shape in [(1,4,15,32),(2,4,32,32),(1,3,32,32),(1,4,1537,16)]:
            with self.assertRaises(ValueError):self.new(torch.zeros(shape))
            COUNTS['guardRejections']+=1

if __name__=='__main__':
    result=unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(PretrainedContextTests));print(json.dumps({'tests':result.testsRun,'counts':COUNTS,'ok':result.wasSuccessful()}),flush=True);sys.exit(0 if result.wasSuccessful() else 1)
