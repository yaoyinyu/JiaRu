"""GN解析分解的独立数学参考、原存储域及完整分母拒绝路径。"""
import importlib.util
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
R=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('gn_decomposition_test',R/'model/training/analyze-native-groupnorm-decomposition.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

class GroupNormDecompositionTests(unittest.TestCase):
    def test_group_order_and_affine_match_scalar_reference_without_mutating_input(self):
        x=np.arange(64,dtype=np.float32).reshape(1,16,2,2)/7;x.flags.writeable=False
        gamma=np.linspace(.5,1.5,16,dtype=np.float32).reshape(16,1,1);beta=np.linspace(-.1,.2,16,dtype=np.float32).reshape(16,1,1);eps=float(np.float32(1e-5))
        actual,stats=m.gn64(x,gamma,beta,4,eps);expected=np.empty(x.shape,np.float64)
        for group in range(4):
            values=[float(x[0,c,y,z]) for c in range(group*4,group*4+4) for y in range(2) for z in range(2)];mean=sum(values)/len(values);variance=sum((v-mean)**2 for v in values)/len(values)
            for c in range(group*4,group*4+4):
                for y in range(2):
                    for z in range(2):expected[0,c,y,z]=(float(x[0,c,y,z])-mean)/math.sqrt(variance+eps)*float(gamma[c,0,0])+float(beta[c,0,0])
        np.testing.assert_allclose(actual,expected,rtol=0,atol=2e-15)
        self.assertEqual(stats['elementsPerGroup'],16)
        self.assertFalse(x.flags.writeable)
    def test_constant_group_uses_original_epsilon_and_bias(self):
        x=np.full((1,16,3,3),3.5,np.float32);gamma=np.ones((16,1,1),np.float32);beta=np.arange(16,dtype=np.float32).reshape(16,1,1)
        y,stats=m.gn64(x,gamma,beta,4,float(np.float32(1e-5)))
        np.testing.assert_array_equal(y,np.broadcast_to(beta.astype(np.float64),x.shape))
        self.assertEqual(stats['centeredVariance'],[[[0.],[0.],[0.],[0.]]])
    def test_domains_invalid_groups_and_nonfinite_are_rejected(self):
        x=np.ones((1,16,2,2),np.float32);gamma=np.ones((16,1,1),np.float32);beta=np.zeros_like(gamma)
        for groups in (0,3):
            with self.assertRaises(ValueError):m.gn64(x,gamma,beta,groups,1e-5)
        with self.assertRaises(ValueError):m.gn64(x.astype(np.float64),gamma,beta,4,1e-5)
        x[0,0,0,0]=np.nan
        with self.assertRaises(ValueError):m.gn64(x,gamma,beta,4,1e-5)
    def test_signed_decomposition_tracks_the_same_maximum_coordinate(self):
        cx=np.zeros((1,1,1,2),np.float32);wx=cx.copy();cy=np.array([[[[1.,2.]]]],np.float32);wy=np.array([[[[1.25,2.5]]]],np.float32);c64=cy.astype(np.float64)-.125;w64=c64+np.array([[[[.1,.3]]]],np.float64)
        r=m.decomposition(cx,cy,wx,wy,c64,w64,1e-12)
        self.assertEqual(r['actualMaximumCoordinate'],[0,0,0,1]);self.assertEqual(r['actualOutputMaxAbs'],.5)
        at=r['atActualMaximum'];self.assertAlmostEqual(at['upstream']+at['wasmOwnRounding']-at['cudaOwnRounding'],at['actual'],places=14)
        self.assertLessEqual(r['equationResidualMaxAbs'],1e-12)
        with self.assertRaises(ValueError):m.decomposition(cx,cy,wx,wy,c64.astype(np.float32),w64,1e-12)
    def test_raw_reader_checks_dtype_shape_hash_and_all_elements(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'raw.bin';np.array([1,np.nan],np.float64).tofile(path);ref=m.d.bind(path)|{'dtype':'float64','shape':[2]}
            with self.assertRaises(ValueError):m.read_tensor(ref)
            np.array([1,2],np.float64).tofile(path)
            with self.assertRaises(ValueError):m.read_tensor(ref)
            fresh=m.d.bind(path)|{'dtype':'float64','shape':[3]}
            with self.assertRaises(ValueError):m.read_tensor(fresh)
    def test_partial_case_denominator_cannot_produce_summary(self):
        with self.assertRaisesRegex(ValueError,'all cases'):m.summarize({'cases':[{'ordinal':1},{'ordinal':2}]},[{'ordinal':1}])
    def test_consumed_output_blocks_before_loading_or_analytic_evaluation(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(m,'resources',side_effect=RuntimeError('must not reach')) as resources:
            with self.assertRaisesRegex(ValueError,'consumed'):m.execute(Path(temp)/'execution.json',Path(temp))
            resources.assert_not_called()

if __name__=='__main__':unittest.main()
