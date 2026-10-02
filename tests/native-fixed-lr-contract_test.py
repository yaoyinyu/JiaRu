import copy
import importlib.util
from pathlib import Path
import unittest
import torch

spec=importlib.util.spec_from_file_location('fixed_lr_contract_fixture',Path(__file__).resolve().parents[1]/'model/training/native-fixed-lr-contract.py')
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class FixedLearningRateTests(unittest.TestCase):
    def setUp(self):
        self.previous={'learningRate':0.0003,'minimumLearningRate':0.0000015,'epochs':64,'expectedOptimizerSteps':384,'accumulation':8,'seed':1605,'optimizer':'AdamW','weightDecay':0.0001}
        self.current={**self.previous,'minimumLearningRate':0.0003}

    def test_only_floor_changes_without_mutating_reference(self):
        before=copy.deepcopy(self.previous)
        result=m.validate_training_change(self.current,self.previous)
        self.assertEqual(result['optimizerSteps'],384)
        self.assertEqual(self.previous,before)
        for key,value in [('epochs',65),('seed',7),('learningRate',0.0004),('accumulation',9),('weightDecay',0.),('optimizer','SGD')]:
            wrong={**self.current,key:value}
            with self.assertRaises(ValueError):m.validate_training_change(wrong,self.previous)

    def test_actual_scheduler_keeps_all384_step_rates_constant(self):
        parameter=torch.nn.Parameter(torch.tensor(1.))
        optimizer=torch.optim.AdamW([parameter],lr=0.0003)
        scheduler=torch.optim.lr_scheduler.CosineAnnealingLR(optimizer,T_max=64,eta_min=0.0003)
        events=[]
        for epoch in range(64):
            for window in range(6):
                events.append({'optimizerStepInFlight':True,'attemptedNextStep':len(events)+1,'learningRate':optimizer.param_groups[0]['lr']})
                parameter.grad=torch.ones_like(parameter);optimizer.step()
            scheduler.step()
        result=m.verify_recorded_rates(events,m.validate_training_change(self.current,self.previous))
        self.assertEqual(result,{'recordedOptimizerStepCount':384,'uniqueRecordedLearningRates':[0.0003]})
        self.assertEqual(scheduler.get_last_lr(),[0.0003])

    def test_reference_scheduler_reaches_original_endpoint(self):
        parameter=torch.nn.Parameter(torch.tensor(1.))
        optimizer=torch.optim.AdamW([parameter],lr=0.0003)
        scheduler=torch.optim.lr_scheduler.CosineAnnealingLR(optimizer,T_max=64,eta_min=0.0000015)
        for _ in range(64):
            parameter.grad=torch.ones_like(parameter);optimizer.step();scheduler.step()
        self.assertEqual(scheduler.get_last_lr(),[0.0000015])

    def test_recording_rejects_missing_duplicate_or_wrong_rate(self):
        events=[{'optimizerStepInFlight':True,'attemptedNextStep':i+1,'learningRate':0.0003} for i in range(384)]
        expected=m.validate_training_change(self.current,self.previous)
        for bad in [events[:-1],events+[events[-1]],events[:-1]+[{**events[-1],'learningRate':0.0000015}]]:
            with self.assertRaises(ValueError):m.verify_recorded_rates(bad,expected)


if __name__=='__main__':unittest.main()
