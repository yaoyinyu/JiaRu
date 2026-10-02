"""非零控制须实际覆盖双分支；梯度门须拒绝缺失分支与带外泄漏。"""
import importlib.util
from pathlib import Path
import unittest
import torch

path=Path(__file__).resolve().parents[1]/'model/training/audit-native-dual-path-head-feasibility.py'
spec=importlib.util.spec_from_file_location('dual_feasibility_test',path)
d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)


class Gates(unittest.TestCase):
    def test_control_covers_both_branches_and_is_deterministic(self):
        left=d.control_head(d.h,1605);right=d.control_head(d.h,1605)
        self.assertTrue(all(torch.equal(v,right.state_dict()[k]) for k,v in left.state_dict().items()))
        x=torch.linspace(-1,1,6*13*17).reshape(1,6,13,17)
        with torch.no_grad():
            c,l=left.context(x),left.local(x)
            self.assertGreater(float(c.std()),1e-6);self.assertGreater(float(l.std()),1e-6)
            self.assertTrue(torch.equal(left(x),c+l))

    def test_gradient_gate_rejects_missing_branch_and_outside_leak(self):
        head=d.h.NativeBoundaryNailRefiner()
        for p in head.parameters():p.grad=torch.zeros_like(p)
        for branch in (head.context,head.local):branch.output.weight.grad.fill_(1)
        delta=torch.zeros(1,1,3,4,requires_grad=True);delta.grad=torch.zeros_like(delta)
        band=torch.ones_like(delta,dtype=torch.bool);band[0,0,0,0]=False
        self.assertEqual(d.gradient_evidence(head,delta,band,True),{'context':True,'local':True})
        head.local.output.weight.grad.zero_()
        with self.assertRaisesRegex(ValueError,'both output'):d.gradient_evidence(head,delta,band,True)
        head.local.output.weight.grad.fill_(1);delta.grad[0,0,0,0]=1
        with self.assertRaisesRegex(ValueError,'outside-band'):d.gradient_evidence(head,delta,band,True)

    def test_architecture_identity(self):
        self.assertEqual(d.architecture_proof(1605)['parameterCount'],40770)


if __name__=='__main__':
    torch.set_num_threads(2);unittest.main()
