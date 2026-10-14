"""完整重建范围修复必须包含所有三处range，不能缩减实际74输入。"""
import ast
import importlib.util
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('native_range_tests', ROOT/'model/training/audit-reviewed-native-deployment-v2.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


class Tests(unittest.TestCase):
    def test_all_three_upper_bounds_use_full_frozen_denominator(self):
        source = 'def f():\n a=list(range(1,69))\n b=[i for i in range(1,69)]\n c=[i for i in range(1,69)]\n return a,b,c\n'
        tree, sites = m.corrected_reconstructor(source); ns = {'N': 74}; exec(compile(tree, '<fixture>', 'exec'), ns)
        self.assertEqual(len(sites), 3); self.assertEqual(ns['f'](), (list(range(1,75)),)*3)

    def test_partial_repair_or_unknown_source_is_rejected(self):
        for source in ('def f():\n return list(range(1,69))\n', 'def f():\n return list(range(1,74))\n'):
            with self.assertRaises(ValueError): m.corrected_reconstructor(source)

    def test_only_range_end_changes_not_other_constants(self):
        source = 'def f():\n a=69\n return a,[list(range(1,69)),list(range(1,69)),list(range(1,69))]\n'
        tree, sites = m.corrected_reconstructor(source); ns = {'N': 74}; exec(compile(tree, '<fixture>', 'exec'), ns)
        self.assertEqual(ns['f']()[0], 69); self.assertTrue(all(len(x)==74 for x in ns['f']()[1]))


if __name__ == '__main__': unittest.main()
