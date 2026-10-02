"""Windows真实共享锁回归；仅临时JSONfixture，无模型或优化器执行。"""
import ctypes
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def load(name,filename):
    s=importlib.util.spec_from_file_location(name,ROOT/'model/training'/filename)
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


j=load('journal_test','conditional-refinement-execution-journal.py')
t=load('replace_test','train-conditional-nail-refinement-bf16-microfit.py')


class JournalTests(unittest.TestCase):
    @unittest.skipUnless(os.name=='nt','Windows sharing mode regression')
    def test_real_read_lock_blocks_old_replace_but_not_new_events(self):
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.CreateFileW.argtypes=[ctypes.c_wchar_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p]
        kernel.CreateFileW.restype=ctypes.c_void_p
        kernel.CloseHandle.argtypes=[ctypes.c_void_p]
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);old=root/'old.json';t.atomic_json(old,{'steps':0})
            journal=j.ExecutionJournal();progress=root/'progress.json'
            journal.write(progress,{'phase':'training','optimizerSteps':0})
            first=root/'progress-events/000001.json';before=t.a.sha(first)
            handles=[kernel.CreateFileW(str(p),0x80000000,1,None,3,0x80,None) for p in [old,first]]
            try:
                self.assertTrue(all(h not in [None,ctypes.c_void_p(-1).value] for h in handles))
                with self.assertRaises(PermissionError):t.atomic_json(old,{'steps':1})
                for step in range(1,101):journal.write(progress,{'phase':'training','optimizerSteps':step})
                self.assertEqual(t.a.sha(first),before)
                self.assertEqual(len(list((root/'progress-events').glob('*.json'))),101)
                self.assertFalse(progress.exists())
                journal.write(progress,{'phase':'closed','optimizerSteps':100})
                self.assertEqual(t.a.read(progress)['optimizerSteps'],100)
            finally:
                for handle in handles:
                    if handle not in [None,ctypes.c_void_p(-1).value]:kernel.CloseHandle(handle)

    def test_existing_event_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'progress.json';j.ExecutionJournal().write(p,{'phase':'training'})
            first=p.parent/'progress-events/000001.json';before=t.a.sha(first)
            with self.assertRaises(FileExistsError):j.ExecutionJournal().write(p,{'phase':'training','changed':True})
            self.assertEqual(t.a.sha(first),before)

    def test_incomplete_step_journal_cannot_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);state={'phase':'closed','optimizerSteps':0,'optimizerStepInFlight':False}
            j.ExecutionJournal().write(root/'progress.json',state)
            with self.assertRaisesRegex(ValueError,'all384 confirmed steps'):j.verify_events(root,state,[])


if __name__=='__main__':unittest.main()
