"""架构容量实验不能连带改变优化预算、抽样或阈值配置。"""
import importlib.util
from pathlib import Path
import unittest

path=Path(__file__).resolve().parents[1]/'model/training/train-native-dual-path-microfit.py'
spec=importlib.util.spec_from_file_location('dual_capacity_contract_test',path)
t=importlib.util.module_from_spec(spec);spec.loader.exec_module(t)


class Contract(unittest.TestCase):
    def setUp(self):
        self.previous={'initialization':'previous context head','epochs':64,'expectedOptimizerSteps':384,
                       'learningRate':.0003,'minimumLearningRate':.0003,'seed':1605,'accumulation':8,'precision':'float32'}
        self.current={**self.previous,'initialization':'fresh seeded40770param dual zero-output head; old context seed1605, independent local seed1606, no prior corrective weights'}

    def test_same_optimization_recipe_allowed(self):
        self.assertEqual(t.training_contract(self.current,self.previous)['optimizerSteps'],384)

    def test_budget_schedule_sampler_and_precision_changes_rejected(self):
        for key,value in [('epochs',65),('expectedOptimizerSteps',390),('learningRate',.0004),
                          ('minimumLearningRate',1.5e-6),('seed',1606),('accumulation',4),('precision','bf16')]:
            with self.subTest(key=key),self.assertRaises(ValueError):t.training_contract({**self.current,key:value},self.previous)


if __name__=='__main__':unittest.main()
