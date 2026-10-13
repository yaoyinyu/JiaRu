"""尾链独立数学参考、精度存储边界及预算拒绝路径。"""
import importlib.util
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
R=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('tail_counterfactual_test',R/'model/training/analyze-native-tail-counterfactual.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

class TailCounterfactualTests(unittest.TestCase):
    def test_fp64_gn_preserves_sub_float32_input_and_matches_scalar(self):
        x=np.array([[[[1.,1.+1e-9]],[[2.,3.]]]],np.float64);x.flags.writeable=False
        gamma=np.array([1.,2.],np.float32).reshape(2,1,1);beta=np.array([.2,-.1],np.float32).reshape(2,1,1);epsilon=float(np.float32(1e-5))
        y,stats=m.gn64(x,gamma,beta,1,epsilon);values=x.reshape(-1).tolist();mean=sum(values)/4;variance=sum((v-mean)**2 for v in values)/4
        expected=np.empty(x.shape,np.float64)
        for c in range(2):
            for i in range(2):expected[0,c,0,i]=(float(x[0,c,0,i])-mean)/math.sqrt(variance+epsilon)*float(gamma[c,0,0])+float(beta[c,0,0])
        np.testing.assert_allclose(y,expected,rtol=0,atol=1e-15);self.assertNotEqual(y[0,0,0,0],y[0,0,0,1]);self.assertEqual(stats['inputStorageDomain'],'float64')
    def test_gelu_uses_actual_float32_sqrt2_bits_and_scalar_erf(self):
        x=np.array([-3.,-.1,0.,1.,2.],np.float64);constants={'sqrt2FromOriginalFloat32':float(np.float32(np.sqrt(2))),'oneFromOriginalFloat32':1.,'halfFromOriginalFloat32':.5}
        y,_=m.gelu64(x,constants);expected=np.array([v*(1+math.erf(v/constants['sqrt2FromOriginalFloat32']))*.5 for v in x])
        np.testing.assert_allclose(y,expected,rtol=0,atol=1e-15)
        with self.assertRaises(ValueError):m.gelu64(x,constants|{'sqrt2FromOriginalFloat32':math.sqrt(2)})
    def test_real_delta_bias_and_channels_match_scalar_across_chunks(self):
        x=(np.arange(30,dtype=np.float64).reshape(1,3,2,5)-7)/13;weight=np.array([.3,-.2,.7],np.float32).reshape(1,3,1,1);bias=np.array([.125],np.float32)
        expected=np.array([sum(float(x[0,c,y,z])*float(weight[0,c,0,0]) for c in range(3))+float(bias[0]) for y in range(2) for z in range(5)]).reshape(1,1,2,5)
        y,stats=m.delta64(x,weight,bias,3);np.testing.assert_allclose(y,expected,rtol=0,atol=3e-16);self.assertEqual(stats['coveredOutputPixels'],10);self.assertEqual(stats['chunks'],4)
    def test_single_final_rounding_differs_from_premature_delta_rounding(self):
        seed=np.array([[[[4.]]]],np.float32);delta=np.array([[[[-3.9999999]]]],np.float64)
        mask,_=m.final_mask64(seed,delta);rounded=mask.astype(np.float32)
        self.assertGreater(float(rounded[0,0,0,0]),0);self.assertEqual(float((seed+delta.astype(np.float32))[0,0,0,0]),0)
    def test_original_seed_is_fourth_channel_with_float32_operation_order(self):
        candidate=np.arange(24,dtype=np.float32).reshape(1,4,2,3)/7
        np.testing.assert_array_equal(m.seed32(candidate),candidate[:,3:4]*np.float32(8)-np.float32(4))
        with self.assertRaises(ValueError):m.seed32(candidate.astype(np.float64))
    def test_nonfinite_and_wrong_storage_are_rejected(self):
        x=np.ones((1,1,1,1),np.float64);weight=np.ones((1,1,1,1),np.float32);bias=np.zeros(1,np.float32)
        with self.assertRaises(ValueError):m.delta64(x.astype(np.float32),weight,bias,4)
        with self.assertRaises(ValueError):m.delta64(x,weight,bias,4097)
        with self.assertRaises(ValueError):m.final_mask64(x.astype(np.float32),x*np.nan)
        with self.assertRaises(ValueError):m.gelu64(x*np.nan,{})
    def test_original_comparator_keeps_full_decoded_and_presence_gate(self):
        expected=np.array([-1.,1.],np.float32);presence=np.array([1.],np.float32)
        r=m.comparator.compare_outputs(expected,presence,np.array([1.,1.],np.float32),presence,1,2)
        self.assertEqual(r['decodedMaskPixelDifference'],1);self.assertFalse(r['decodedPixelGatePassed'])
        r=m.comparator.compare_outputs(expected,presence,expected,np.array([-1.],np.float32),1,2);self.assertFalse(r['presenceDecisionMatched'])
    def test_consumed_root_and_partial_denominator_rejected(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'resources',side_effect=RuntimeError('must not reach')) as res:
            with self.assertRaisesRegex(ValueError,'consumed'):m.execute(Path(tmp)/'execution.json',Path(tmp))
            res.assert_not_called()
        with self.assertRaisesRegex(ValueError,'all cases'):m.summarize({'cases':[{'ordinal':1},{'ordinal':2}]},[{'ordinal':1}])

if __name__=='__main__':unittest.main()
