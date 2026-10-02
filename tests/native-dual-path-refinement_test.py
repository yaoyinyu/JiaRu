import importlib.util
from pathlib import Path
import unittest
import torch

spec=importlib.util.spec_from_file_location('dual_path_fixture',Path(__file__).resolve().parents[1]/'model/training/native-dual-path-nail-refinement.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class DualPathTests(unittest.TestCase):
    def setUp(self):torch.set_num_threads(2)

    def test_context_initialization_and_outer_rng_are_unchanged(self):
        torch.manual_seed(1605);reference=m.context_module.NativeBoundaryNailRefiner();rng=torch.random.get_rng_state().clone()
        torch.manual_seed(1605);head=m.NativeBoundaryNailRefiner()
        self.assertTrue(torch.equal(torch.random.get_rng_state(),rng))
        for key,value in reference.state_dict().items():self.assertTrue(torch.equal(value,head.context.state_dict()[key]))
        self.assertEqual(sum(p.numel() for p in head.parameters()),40770)
        self.assertEqual([head.local.features[i].dilation for i in (0,3,6)],[(1,1)]*3)
        self.assertEqual([head.context.features[i].dilation for i in (0,3,6)],[(1,1),(3,3),(9,9)])

    def test_zero_output_and_nonzero_branch_additivity_at_dynamic_shapes(self):
        torch.manual_seed(1605);head=m.NativeBoundaryNailRefiner()
        for height,width in [(17,19),(32,25),(41,43)]:
            data=torch.rand(1,6,height,width)
            self.assertEqual(tuple(head(data).shape),(1,1,height,width))
            self.assertEqual(int(torch.count_nonzero(head(data))),0)
        with torch.no_grad():head.context.output.bias.fill_(.2);head.local.output.bias.fill_(-.1)
        data=torch.rand(1,6,23,29)
        self.assertTrue(torch.equal(head(data),head.context(data)+head.local(data)))
        self.assertTrue(torch.isfinite(head(data)).all())

    def test_both_output_branches_receive_gradients_at_initialization(self):
        head=m.NativeBoundaryNailRefiner();result=head(torch.rand(1,6,19,21));(result-1).square().mean().backward()
        for branch in (head.context,head.local):
            self.assertGreater(int(torch.count_nonzero(branch.output.weight.grad)),0)
            for name,param in branch.named_parameters():
                self.assertIsNotNone(param.grad);self.assertTrue(torch.isfinite(param.grad).all())
                if name.startswith('features.'):self.assertEqual(int(torch.count_nonzero(param.grad)),0)


if __name__=='__main__':unittest.main()
