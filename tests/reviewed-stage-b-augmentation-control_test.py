"""去增强对照的原像素/RNG/完整分母与单变量反例。"""
import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
R=Path(__file__).resolve().parents[1]
def load(file,name):
    sp=importlib.util.spec_from_file_location(name,R/'model/training'/file);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);return m
c=load('train-reviewed-stage-b-augmentation-control.py','control_test_train')
v=load('verify-reviewed-stage-b-augmentation-control.py','control_test_verify')

class Tests(unittest.TestCase):
    def arrays(self):
        return np.arange(12*16*3,dtype=np.uint8).reshape(12,16,3),np.ones((12,16),np.uint8)*255,np.ones((12,16),np.uint8)*255
    def test_every_sampled_transform_applies_identity_to_all_pixels(self):
        values=self.arrays()
        for rotation in range(4):
            for flip in (False,True):
                actual=c.identity_augment(*values,rotation,flip,.9,1.1)
                for a,b in zip(actual,values):self.assertEqual(a.tobytes(),b.tobytes());self.assertIsNot(a,b)
    def test_identity_does_not_modify_source_arrays(self):
        values=self.arrays();raw=[a.tobytes() for a in values];actual=c.identity_augment(*values,1,True,1.1,.9);actual[0][:]=0
        self.assertEqual([a.tobytes() for a in values],raw)
    def test_bad_rng_choice_cannot_be_hidden_by_identity(self):
        with self.assertRaisesRegex(ValueError,'RNG'):c.identity_augment(*self.arrays(),.5,False,1.,1.)
    def fixture(self):
        rows=[{'candidateIdentity':{'identity':{'split':'train','fileName':str(i),'imageSha256':str(i)}},'nativePixelSha256':{k:str(i)+k for k in ('nativeRgb','nativeCoarse','nativeTarget')}} for i in range(3)]
        plan={'candidateIdentities':[r['candidateIdentity'] for r in rows],'budget':{'epochs':2,'augmentedTrainingInputs':6},'control':{'rngSeed':20261015}}
        rng=np.random.default_rng(20261015);events=[]
        for epoch in range(2):
            for i in rng.permutation(3):
                row=rows[i];events.append({'phase':'training_input_started','epoch':epoch+1,'candidateIdentity':row['candidateIdentity'],
                    'augmentation':c.choice(rng),'augmentationApplied':c.IDENTITY,'sampledAugmentationNotApplied':True,'appliedNativePixelSha256':row['nativePixelSha256']})
        return copy.deepcopy((events,events,plan,rows))
    def test_complete_rng_and_identity_trace(self):
        events,old,plan,rows=self.fixture();self.assertEqual(v.validate_control_trace(events,old,plan,rows)['trainingInputs'],6)
    def test_changed_candidate_order_rejected(self):
        events,old,plan,rows=self.fixture();events=copy.deepcopy(events);events[0]['candidateIdentity']=rows[2]['candidateIdentity']
        if events[0]['candidateIdentity']==old[0]['candidateIdentity']:events[0]['candidateIdentity']=rows[0]['candidateIdentity']
        with self.assertRaisesRegex(ValueError,'candidate order'):v.validate_control_trace(events,old,plan,rows)
    def test_missing_rng_draw_rejected(self):
        events,old,plan,rows=self.fixture();events=copy.deepcopy(events);events[2]['augmentation']['brightness']=.99999
        with self.assertRaisesRegex(ValueError,'RNG'):v.validate_control_trace(events,old,plan,rows)
    def test_transformed_rgb_even_with_correct_order_rejected(self):
        events,old,plan,rows=self.fixture();events=copy.deepcopy(events);events[0]['appliedNativePixelSha256']['nativeRgb']='changed'
        with self.assertRaisesRegex(ValueError,'native bytes'):v.validate_control_trace(events,old,plan,rows)
    def test_applied_transform_is_not_inferred_from_sampled_choice(self):
        events,old,plan,rows=self.fixture();events=copy.deepcopy(events);events[0]['augmentationApplied']={'rotation':1}
        with self.assertRaisesRegex(ValueError,'identity applied'):v.validate_control_trace(events,old,plan,rows)
    def test_smaller_cohort_cannot_pass(self):
        events,old,plan,rows=self.fixture()
        with self.assertRaisesRegex(ValueError,'full training'):v.validate_control_trace(events[:-1],old,plan,rows)
    def test_engine_hook_persists_actual_pixel_hashes_without_original_source_change(self):
        temp=R/'model/reviews/resize-test-temp';temp.mkdir(exist_ok=True,parents=True)
        with tempfile.TemporaryDirectory(dir=temp) as folder:
            root=Path(folder);plan=root/'plan.json';c.d.new(plan,{'sources':{'baseTrainer':c.d.bind(R/'model/training/train-reviewed-stage-b-normal-development.py')}})
            engine=c.engine(plan);journal=engine.Journal(root);values=self.arrays();actual=engine.augment(*values,rotation=1,flip=True,brightness=.9,contrast=1.1)
            record=journal.event('training_input_started',augmentation={'rotation':1})
            self.assertEqual(record['appliedNativePixelSha256'],c.pixel_hashes(values));self.assertEqual(record['augmentationApplied'],c.IDENTITY)
            self.assertEqual(actual[0].shape,values[0].shape)
            with self.assertRaisesRegex(ValueError,'application'):journal.event('training_input_started')

if __name__=='__main__':unittest.main()
