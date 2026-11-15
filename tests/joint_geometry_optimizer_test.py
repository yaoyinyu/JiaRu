import importlib.util
from pathlib import Path
import unittest
import torch

path = Path(__file__).resolve().parents[1] / 'model/training/joint-geometry-optimizer.py'
spec = importlib.util.spec_from_file_location('joint_optimizer', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Model(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.previous = torch.nn.Module()
        self.previous.base = torch.nn.ParameterList([torch.nn.Parameter(torch.tensor([1.]), requires_grad=False) for _ in range(79)])
        self.previous.geometry = torch.nn.ParameterList([torch.nn.Parameter(torch.tensor([1.])) for _ in range(24)])
        self.current = torch.nn.ParameterList([torch.nn.Parameter(torch.tensor([1.])) for _ in range(40)])


class Tests(unittest.TestCase):
    def setUp(self):
        self.plan = dict(learningRate=.003, weightDecay=.0001, geometryLearningRateMultiplier=.1)

    def test_actual_adam_update_and_roundtrip(self):
        model = Model()
        optimizer = module.build(model, self.plan)
        for value in model.parameters():
            if value.requires_grad:
                value.grad = torch.ones_like(value)
        optimizer.step()
        geometry = 1 - float(model.previous.geometry[0].detach())
        current = 1 - float(model.current[0].detach())
        self.assertAlmostEqual(geometry / current, .1, places=4)
        self.assertTrue(all(float(v.detach()) == 1 for v in model.previous.base))
        module.verify_groups(optimizer.state_dict(), self.plan, 1)
        restored = module.build(Model(), self.plan)
        restored.load_state_dict(optimizer.state_dict())
        module.verify_groups(restored.state_dict(), self.plan, 1)
        self.assertEqual(len(restored.state), 64)

    def test_all_schedule_transitions_and_tamper(self):
        optimizer = module.build(Model(), self.plan)
        for epoch in range(1, 129):
            module.start_epoch(optimizer, self.plan, epoch)
            module.verify_groups(optimizer.state_dict(), self.plan, epoch * 80)
            event = dict(learningRate=optimizer.param_groups[1]['lr'], geometryLearningRate=optimizer.param_groups[0]['lr'])
            self.assertTrue(module.verify_event(event, self.plan, epoch * 80))
        optimizer.param_groups[0]['lr'] *= 2
        with self.assertRaises(AssertionError):
            module.verify_groups(optimizer.state_dict(), self.plan, 10240)

    def test_frozen_visual_required(self):
        model = Model()
        model.previous.base[0].requires_grad_(True)
        with self.assertRaises(AssertionError):
            module.build(model, self.plan)


if __name__ == '__main__':
    unittest.main()
