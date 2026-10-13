"""审核输出被篡改、缺字节或含非有限数时，必须在比较前拒绝。"""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

s = importlib.util.spec_from_file_location('precision_buffer_test',Path(__file__).resolve().parents[1]/'model/training/audit-trained-native-precision-v2.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


class Tests(unittest.TestCase):
    def test_truncated_tensor_rejected_even_with_valid_file_hash(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'head.bin';path.write_bytes(np.ones(1,np.float32).tobytes())
            with self.assertRaisesRegex(ValueError,'cardinality'):
                m.buffer(m.d.bind(path),2)

    def test_changed_bytes_rejected_before_numeric_comparison(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'head.bin';path.write_bytes(np.ones(1,np.float32).tobytes());ref=m.d.bind(path)
            path.write_bytes(np.zeros(1,np.float32).tobytes())
            with self.assertRaisesRegex(ValueError,'reconstruction_mismatch'):
                m.buffer(ref,1)

    def test_nonfinite_captured_head_rejected_with_valid_hash(self):
        for number in (np.nan,np.inf,-np.inf):
            with self.subTest(number=number),tempfile.TemporaryDirectory() as root:
                path=Path(root)/'head.bin';path.write_bytes(np.array([number],np.float32).tobytes())
                with self.assertRaisesRegex(ValueError,'nonfinite'):
                    m.buffer(m.d.bind(path),1)

    def test_positive_optimization_budget_rejected_before_resource_loading(self):
        plan={'purpose':'same_weights_full68_strict_fp32_capacity_and_precision','optimizerStepsAllowed':1,'valInputsAllowed':0,'protectedInputsAllowed':0}
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'plan.json';m.d.new(path,plan)
            with patch.object(m.d,'load',side_effect=RuntimeError('must not load training resources')) as loader:
                with self.assertRaisesRegex(ValueError,'zero optimization'):
                    m.resources(path)
                loader.assert_not_called()

    def test_relaxed_numeric_gate_rejected_before_resource_loading(self):
        plan={'purpose':'same_weights_full68_strict_fp32_capacity_and_precision','optimizerStepsAllowed':0,'valInputsAllowed':0,'protectedInputsAllowed':0,
              'cpuTorchInputsAllowed':68,'strictCudaInputsAllowed':68,'requiredMaximumNumericDifference':1e-3,'requiredDecodedPixelDifferences':0}
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'plan.json';m.d.new(path,plan)
            with patch.object(m.d,'load',side_effect=RuntimeError('must not load training resources')) as loader:
                with self.assertRaisesRegex(ValueError,'numeric/pixel contract'):
                    m.resources(path)
                loader.assert_not_called()


if __name__=='__main__':
    unittest.main()
