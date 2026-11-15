import importlib.util
from pathlib import Path
import unittest
import torch

path = Path(__file__).resolve().parents[1] / 'model/training/joint-geometry-optimizer-v2.py'
spec = importlib.util.spec_from_file_location('joint_optimizer', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FrozenVisual(torch.nn.ParameterList):
    def __init__(self):
        super().__init__([torch.nn.Parameter(torch.tensor([1.]), requires_grad=False) for _ in range(77)])
        self.register_buffer('offsets', torch.zeros(1))
        self.register_buffer('prior', torch.zeros(1))


class Model(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.previous = torch.nn.Module()
        self.previous.base = FrozenVisual()
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

    def test_actual_model_state_and_parameter_groups(self):
        root = Path(__file__).resolve().parents[1]
        def load(filename):
            target = root / 'model/training' / filename
            source = importlib.util.spec_from_file_location(filename, target)
            value = importlib.util.module_from_spec(source)
            source.loader.exec_module(value)
            return value
        joint = load('visual-neighborhood-joint-geometry.py')
        context = load('native-context-radial-refiner.py')
        geometry = load('native-geometry-radial-refiner.py')
        model = joint._sampler.VisualNeighborhoodRadialRefiner(geometry.NativeGeometryRadialRefiner(context.NativeContextRadialRefiner()))
        model.angle_context = joint._capacity.LocalCapacityResidual()
        joint.enable_joint_geometry(model)
        self.assertEqual(len(list(model.previous.base.parameters())), 77)
        self.assertEqual(len(model.previous.base.state_dict()), 79)
        self.assertEqual(len(model.state_dict()), 143)
        optimizer = module.build(model, self.plan)
        module.verify_groups(optimizer.state_dict(), self.plan, 0)
        self.assertEqual([len(g['params']) for g in optimizer.param_groups], [24, 40])


if __name__ == '__main__':
    unittest.main()
