"""正常StageB训练的整数增强、拒识、原像素验收和不可覆盖事件反例。"""
import importlib.util
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
import numpy as np
import torch

R=Path(__file__).resolve().parents[1]
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
m=load(R/'model/training/train-reviewed-stage-b-normal-development.py','normal_tests')
net=load(R/'model/training/native-multiscale-conditional-refiner-v3.py','normal_test_net')
band=load(R/'model/training/normal-stage-b-boundary-loss.py','normal_test_band')

class Tests(unittest.TestCase):
    def fixture(self):
        rgb=np.arange(12*16*3,dtype=np.uint8).reshape(12,16,3)
        coarse=np.zeros((12,16),np.uint8);coarse[3:9,4:11]=255
        truth=np.zeros_like(coarse);truth[2:10,3:12]=255
        return rgb,coarse,truth

    def test_all_d4_transforms_preserve_masks_and_rgb_geometry(self):
        rgb,c,t=self.fixture()
        for k in range(4):
            for flip in (False,True):
                r,a,b=m.augment(rgb,c,t,k,flip,1.,1.)
                expected=[np.rot90(x,k,axes=(0,1)) for x in (rgb,c,t)]
                if flip:expected=[np.flip(x,axis=1) for x in expected]
                for actual,target in zip((r,a,b),expected):self.assertTrue(np.array_equal(actual,target))

    def test_photometric_augmentation_never_changes_masks(self):
        rgb,c,t=self.fixture();r,a,b=m.augment(rgb,c,t,0,False,.9,1.1)
        self.assertFalse(np.array_equal(r,rgb));self.assertTrue(np.array_equal(a,c));self.assertTrue(np.array_equal(b,t))

    def test_illegal_resampling_choice_rejected(self):
        with self.assertRaisesRegex(ValueError,'integer augmentation'):m.augment(*self.fixture(),.5,False,1.,1.)

    def test_augmentation_does_not_modify_source_arrays(self):
        values=self.fixture();original=[x.copy() for x in values];m.augment(*values,1,True,1.1,.9)
        for a,b in zip(values,original):self.assertTrue(np.array_equal(a,b))

    def test_reject_objective_has_no_decoder_gradient(self):
        logits=torch.ones((1,1,12,16),requires_grad=True);presence=torch.ones((1,1),requires_grad=True)
        loss=m.objective(logits,presence,torch.zeros_like(logits),False,{'candidateInputs':74,'positiveInputs':71,'rejectInputs':3},band)
        loss.backward();self.assertIsNone(logits.grad);self.assertIsNotNone(presence.grad)

    def test_presence_class_total_weights_are_equal(self):
        self.assertAlmostEqual(71*(74/(2*71)),3*(74/(2*3)))

    def test_positive_full_native_objective_has_finite_gradients(self):
        logits=torch.zeros((1,1,12,16),requires_grad=True);p=torch.zeros((1,1),requires_grad=True)
        t=torch.zeros_like(logits);t[:,:,2:10,3:12]=1
        loss=m.objective(logits,p,t,True,{'candidateInputs':74,'positiveInputs':71,'rejectInputs':3},band);loss.backward()
        self.assertTrue(torch.isfinite(loss));self.assertTrue(torch.isfinite(logits.grad).all());self.assertTrue(torch.isfinite(p.grad).all())

    def test_fresh_model_is_reproducible_and_trainable(self):
        a=m.fresh_model(net,'cpu');b=m.fresh_model(net,'cpu')
        self.assertEqual(m.tensors_sha(a),m.tensors_sha(b));self.assertTrue(all(p.requires_grad for p in a.parameters()))

    def test_native_inverse_mapping_uses_original_canvas(self):
        mask=np.ones((3,5),bool);actual=m.full_canvas(mask,[7,4,12,7],[20,15])
        self.assertEqual(actual.shape,(15,20));self.assertEqual(int(actual.sum()),15);self.assertTrue(actual[4:7,7:12].all())

    def test_bad_inverse_mapping_rejected(self):
        with self.assertRaisesRegex(ValueError,'inverse mapping'):m.full_canvas(np.ones((3,5),bool),[7,4,13,7],[20,15])

    def metrics(self):
        return [{'positive':True,'presenceAccepted':True,'jointPass':True,'iou':.9,'boundaryIoU':.8,'boundaryF1':.95},
                {'positive':False,'presenceAccepted':False,'rejected':True,'outputPixels':0}]

    def test_quality_requires_every_positive_presence(self):
        rows=self.metrics();rows[0]['presenceAccepted']=False
        self.assertFalse(m.summarize(rows)[1])

    def test_quality_rejects_even_one_output_pixel(self):
        rows=self.metrics();rows[1]['outputPixels']=1;rows[1]['rejected']=False
        self.assertFalse(m.summarize(rows)[1])

    def test_quality_preserves_all_positive_denominator(self):
        rows=self.metrics();rows+=[dict(rows[0],jointPass=False)]
        summary,passed=m.summarize(rows);self.assertEqual(summary['positiveCount'],2);self.assertFalse(passed)

    def test_journal_terminal_cannot_be_overwritten(self):
        root=R/'model/reviews/resize-test-temp';root.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as folder:
            path=Path(folder);j=m.Journal(path);j.event('claimed');j.steps=1;j.event('optimizer_confirmed');j.terminal('closed')
            original=(path/'terminal.json').read_bytes()
            with self.assertRaises(FileExistsError):j.terminal('failed')
            self.assertEqual((path/'terminal.json').read_bytes(),original)

    def test_concurrent_progress_reader_does_not_block_unique_event_writes(self):
        root=R/'model/reviews/resize-test-temp';root.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as folder:
            path=Path(folder);j=m.Journal(path);stop=threading.Event();seen=set();errors=[]
            def read():
                while not stop.is_set():
                    for file in (path/'events').glob('*.json'):
                        try:seen.add(json.loads(file.read_bytes())['sequence'])
                        except (OSError,ValueError):pass
                    time.sleep(.001)
            t=threading.Thread(target=read);t.start()
            try:
                for i in range(40):j.steps=i;j.event('progress')
                j.terminal('closed')
            except BaseException as error:errors.append(error)
            finally:stop.set();t.join()
            self.assertEqual(errors,[]);self.assertEqual(len(list((path/'events').glob('*.json'))),41)
            self.assertTrue(seen)
            self.assertEqual(json.loads((path/'terminal.json').read_bytes())['sequence'],41)

if __name__=='__main__':unittest.main()
