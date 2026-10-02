"""执行可靠性回归；临时fixture，无模型推理或优化步，不消费实验预算。"""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('bf16_execution_test',ROOT/'model/training/train-conditional-nail-refinement-bf16-microfit.py')
t=importlib.util.module_from_spec(spec);spec.loader.exec_module(t)


class ExecutionTests(unittest.TestCase):
    def test_atomic_json_replaces_and_removes_temporary_files(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'progress.json'
            t.atomic_json(p,{'optimizerSteps':0})
            t.atomic_json(p,{'optimizerSteps':1,'说明':'已确认'})
            self.assertEqual(t.a.read(p),{'optimizerSteps':1,'说明':'已确认'})
            self.assertEqual([x.name for x in p.parent.iterdir()],['progress.json'])

    def test_failed_initialization_is_terminal_and_cannot_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);plan=root/'plan.json';plan.write_text(json.dumps({'inputs':{}}),encoding='utf-8')
            output=root/'attempt'
            with patch.object(t,'validate',return_value=([],{})),patch.object(t.torch.cuda,'is_bf16_supported',return_value=False):
                with self.assertRaisesRegex(RuntimeError,'BF16 unavailable'):t.train(plan,output)
                failure=t.a.read(output/'execution-failure-report.json')
                self.assertTrue(failure['attemptConsumed']);self.assertFalse(failure['restartAllowed'])
                self.assertEqual(failure['qualityDecision'],'unavailable')
                self.assertEqual(failure['state']['optimizerSteps'],0)
                self.assertFalse(failure['state']['optimizerStepInFlight'])
                self.assertEqual(failure['state']['phase'],'execution-failed')
                before={p.name:t.a.sha(p) for p in output.iterdir()}
                with self.assertRaises(FileExistsError):t.train(plan,output)
                self.assertEqual(before,{p.name:t.a.sha(p) for p in output.iterdir()})
                self.assertFalse((output/'microfit-report.json').exists())


if __name__=='__main__':unittest.main()
