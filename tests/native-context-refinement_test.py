"""合成fixture验证空间上下文单变量，无真实训练图或质量结论。"""
import importlib.util
from pathlib import Path
import unittest
import torch

spec = importlib.util.spec_from_file_location('context_test_head', Path(__file__).resolve().parents[1] / 'model/training/native-context-nail-refinement.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
torch.set_num_threads(2)


class NativeContextTests(unittest.TestCase):
    def test_identical_initial_tensors_and_only_operator_attributes_change(self):
        torch.manual_seed(1605)
        old = h.base.NativeBoundaryNailRefiner()
        torch.manual_seed(1605)
        new = h.NativeBoundaryNailRefiner()
        self.assertEqual(sum(p.numel() for p in new.parameters()), 20385)
        self.assertEqual(old.state_dict().keys(), new.state_dict().keys())
        for key, tensor in old.state_dict().items():
            self.assertTrue(torch.equal(tensor, new.state_dict()[key]), key)
        for index, dilation in zip((0, 3, 6), (1, 3, 9), strict=True):
            self.assertEqual(new.features[index].dilation, (dilation, dilation))
            self.assertEqual(new.features[index].padding, (dilation, dilation))

    def test_native_shapes_zero_initial_and_nonzero_operator_control(self):
        torch.manual_seed(1605)
        old = h.base.NativeBoundaryNailRefiner().eval()
        new = h.NativeBoundaryNailRefiner().eval()
        new.load_state_dict(old.state_dict())
        values = torch.randn(1, 6, 37, 53)
        with torch.inference_mode():
            zero = new(values)
            self.assertEqual(tuple(zero.shape), (1, 1, 37, 53))
            self.assertEqual(torch.count_nonzero(zero).item(), 0)
            old.output.weight.fill_(.01)
            new.output.weight.copy_(old.output.weight)
            before, after = old(values), new(values)
            self.assertTrue(torch.isfinite(after).all())
            self.assertGreater((before - after).abs().max().item(), 1e-6)


if __name__ == '__main__':
    unittest.main()
