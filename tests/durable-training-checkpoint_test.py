import importlib.util
from pathlib import Path
import tempfile
import unittest
import numpy as np
import torch

spec = importlib.util.spec_from_file_location('durable_checkpoint', Path(__file__).resolve().parents[1] / 'model/training/durable-training-checkpoint.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


class DurableCheckpointTest(unittest.TestCase):
    def test_optimizer_rng_cursor_resume_exact_and_previous_reader_stays_open(self):
        torch.manual_seed(29)
        net = torch.nn.Linear(3, 1); opt = torch.optim.AdamW(net.parameters(), lr=.01)
        rng = np.random.default_rng(31)
        def step():
            opt.zero_grad(); x = torch.randn(2,3); y = net(x).square().sum(); y.backward(); opt.step()
        step()
        cursor = dict(epoch=1, nextOffset=4, order=[3,2,1,0])
        with tempfile.TemporaryDirectory() as folder:
            a = Path(folder)/'step1.pt'; b = Path(folder)/'step2.pt'
            m.save(a,net,opt,rng,cursor,dict(steps=1),{'sha256':'plan'})
            expected_np = rng.integers(0,999999,8); step()
            expected = {k:v.clone() for k,v in net.state_dict().items()}
            with a.open('rb') as reader:
                m.save(b,net,opt,rng,dict(epoch=1,nextOffset=8,order=[3,2,1,0]),dict(steps=2),{'sha256':'plan'})
                self.assertTrue(reader.read(8)); self.assertTrue(b.exists())
            actual_cursor, counts = m.restore(a,net,opt,rng,{'sha256':'plan'})
            self.assertEqual(actual_cursor,cursor); self.assertEqual(counts,{'steps':1})
            np.testing.assert_array_equal(rng.integers(0,999999,8),expected_np)
            step()
            self.assertTrue(all(torch.equal(v,expected[k]) for k,v in net.state_dict().items()))
            with self.assertRaises(FileExistsError): m.save(a,net,opt,rng,cursor,counts,{'sha256':'plan'})
            with self.assertRaises(ValueError): m.restore(a,net,opt,rng,{'sha256':'other'})


if __name__ == '__main__': unittest.main()
