"""卷积数学参考、原图全域分块和冻结预算拒绝路径。"""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
R=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('conv_decomposition_test',R/'model/training/analyze-native-convolution-decomposition.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

def scalar_reference(x,k):
    n,c,h,w=x.shape;y=np.zeros((n,k.shape[0],h,w),np.float64)
    for b in range(n):
        for o in range(k.shape[0]):
            for row in range(h):
                for col in range(w):
                    total=0.
                    for ch in range(c):
                        for ky in range(3):
                            for kx in range(3):
                                iy=row+ky-1;ix=col+kx-1
                                if 0<=iy<h and 0<=ix<w:total+=float(x[b,ch,iy,ix])*float(k[o,ch,ky,kx])
                    y[b,o,row,col]=total
    return y

class ConvolutionDecompositionTests(unittest.TestCase):
    def test_asymmetric_kernel_channel_order_batches_and_full_padding_match_scalar(self):
        x=(np.arange(60,dtype=np.float32).reshape(2,2,3,5)-13)/7
        k=(np.arange(54,dtype=np.float32).reshape(3,2,3,3)-17)/11
        x.flags.writeable=False;k.flags.writeable=False
        y,stats=m.conv64(x,k,4)
        np.testing.assert_allclose(y,scalar_reference(x,k),rtol=0,atol=4e-14)
        self.assertEqual(stats['coveredOutputPixelsPerChannel'],30);self.assertEqual(stats['chunks'],8)
        self.assertFalse(x.flags.writeable);self.assertFalse(k.flags.writeable)
    def test_chunk_boundary_neighborhood_is_not_cropped(self):
        x=np.zeros((1,1,3,7),np.float32);x[0,0,1,3]=1
        k=np.arange(9,dtype=np.float32).reshape(1,1,3,3)
        for size in (1,4,4096):
            y,stats=m.conv64(x,k,size);np.testing.assert_array_equal(y,scalar_reference(x,k));self.assertTrue(stats['wholeNativeOutputCovered'])
    def test_constant_input_has_true_zero_padding_and_no_added_bias(self):
        y,_=m.conv64(np.ones((1,1,3,3),np.float32),np.ones((1,1,3,3),np.float32),2)
        np.testing.assert_array_equal(y,np.array([[[[4,6,4],[6,9,6],[4,6,4]]]],np.float64))
    def test_dtype_nonfinite_and_chunk_relaxation_rejected(self):
        x=np.ones((1,1,2,2),np.float32);k=np.ones((1,1,3,3),np.float32)
        for size in (0,4097,1.5,True):
            with self.assertRaises(ValueError):m.conv64(x,k,size)
        with self.assertRaises(ValueError):m.conv64(x.astype(np.float64),k,4)
        x[0,0,0,0]=np.inf
        with self.assertRaises(ValueError):m.conv64(x,k,4)
    def test_multithread_runtime_cannot_consume_analytic_scope(self):
        with patch.object(m.threadpoolctl,'threadpool_info',return_value=[{'user_api':'blas','num_threads':2}]):
            with self.assertRaisesRegex(ValueError,'single-thread'):m.runtime_binding()
    def test_signed_decomposition_uses_same_coordinate_and_conv_diagnostic_name(self):
        x=np.zeros((1,1,1,2),np.float32);cy=np.array([[[[1,2]]]],np.float32);wy=cy+np.array([[[[.25,.5]]]],np.float32)
        r=m.decomposition(x,cy,x,wy,cy.astype(np.float64)-.125,wy.astype(np.float64)-.1,1e-12)
        a=r['atActualMaximum'];self.assertEqual(r['actualMaximumCoordinate'],[0,0,0,1])
        self.assertAlmostEqual(a['upstream']+a['wasmOwnRounding']-a['cudaOwnRounding'],a['actual'],places=14)
        self.assertIn('hypotheticalExactConvOnWasmInputAgainstOriginalCudaMaxAbs',r)
        self.assertNotIn('hypotheticalExactGnOnWasmInputAgainstOriginalCudaMaxAbs',r)
    def test_partial_denominator_cannot_summarize(self):
        with self.assertRaisesRegex(ValueError,'all cases'):m.summarize({'cases':[{'ordinal':1},{'ordinal':2}]},[{'ordinal':1}])
    def test_consumed_root_rejected_before_any_resource_or_mathematical_evaluation(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'resources',side_effect=RuntimeError('must not reach')) as res:
            with self.assertRaisesRegex(ValueError,'consumed'):m.execute(Path(tmp)/'execution.json',Path(tmp))
            res.assert_not_called()

if __name__=='__main__':unittest.main()
