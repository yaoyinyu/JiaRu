"""解码尾链FP64卷积与独立七阶段端点参考。"""
import importlib.util
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
R=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('decoder_counterfactual_test',R/'model/training/analyze-native-decoder-counterfactual.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
def conv_reference(x,k):
    n,c,h,w=x.shape;out=np.zeros((n,k.shape[0],h,w),np.float64)
    for b in range(n):
        for o in range(k.shape[0]):
            for y in range(h):
                for z in range(w):
                    for ch in range(c):
                        for ky in range(3):
                            for kz in range(3):
                                iy=y+ky-1;iz=z+kz-1
                                if 0<=iy<h and 0<=iz<w:out[b,o,y,z]+=float(x[b,ch,iy,iz])*float(k[o,ch,ky,kz])
    return out
def gn_reference(x):
    out=np.empty_like(x);eps=float(np.float32(1e-5))
    for group in range(4):
        values=x[0,group*4:group*4+4].reshape(-1).tolist();mean=sum(values)/len(values);var=sum((v-mean)**2 for v in values)/len(values)
        out[0,group*4:group*4+4]=(x[0,group*4:group*4+4]-mean)/math.sqrt(var+eps)
    return out
def gelu_reference(x):
    denominator=float(np.float32(math.sqrt(2)))
    return np.array([float(v)*(1+math.erf(float(v)/denominator))*.5 for v in x.reshape(-1)],np.float64).reshape(x.shape)

class DecoderCounterfactualTests(unittest.TestCase):
    def test_asymmetric_fp64_convolution_matches_independent_scalar(self):
        x=(np.arange(60,dtype=np.float64).reshape(2,2,3,5)-13)/7+1e-9;k=(np.arange(54,dtype=np.float32).reshape(3,2,3,3)-17)/11
        x.flags.writeable=False;y,stats=m.conv64(x,k,4)
        np.testing.assert_allclose(y,conv_reference(x,k),rtol=0,atol=5e-14);self.assertEqual(stats['coveredOutputPixelsPerChannel'],30);self.assertFalse(x.flags.writeable)
    def test_sub_float32_information_survives_propagated_convolution(self):
        x=np.array([[[[1.,1.+1e-9]]]],np.float64);k=np.zeros((1,1,3,3),np.float32);k[0,0,1,1]=1
        y,_=m.conv64(x,k,1);np.testing.assert_array_equal(y,x);self.assertNotEqual(y[0,0,0,0],y[0,0,0,1])
    def test_invalid_domains_chunks_and_nonfinite_are_rejected(self):
        x=np.ones((1,1,2,2),np.float64);k=np.ones((1,1,3,3),np.float32)
        for bad in (0,4097,True):
            with self.assertRaises(ValueError):m.conv64(x,k,bad)
        with self.assertRaises(ValueError):m.conv64(x.astype(np.float32),k,4)
        with self.assertRaises(ValueError):m.conv64(x,k.astype(np.float64),4)
        with self.assertRaises(ValueError):m.conv64(x*np.nan,k,4)
    def test_seven_stage_endpoint_matches_independent_scalar_chain(self):
        x=np.linspace(-1,1,64,dtype=np.float32).reshape(1,16,2,2);kernel=np.zeros((16,16,3,3),np.float32)
        for c in range(16):kernel[c,c,1,1]=.1;kernel[c,(c+1)%16,0,1]=.01
        dw=np.linspace(-.2,.3,16,dtype=np.float32).reshape(1,16,1,1);bias=np.array([-.05],np.float32)
        z=gelu_reference(gn_reference(x.astype(np.float64)));z=gelu_reference(gn_reference(conv_reference(z,kernel)))
        delta=np.array([sum(float(z[0,c,y,a])*float(dw[0,c,0,0]) for c in range(16))+float(bias[0]) for y in range(2) for a in range(2)]).reshape(1,1,2,2)
        seed=np.array([[[[4.,4.],[-4.,-4.]]]],np.float32);expected=(seed.astype(np.float64)+delta).astype(np.float32)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);write=lambda name,a:m.t.save(root/name,a)
            candidate=np.zeros((1,4,2,2),np.float32);candidate[:,3:4]=(seed+4)/8
            presence=write('presence.bin',np.array([[1.]],np.float32));mask=write('reference.bin',expected);inputref=write('input.bin',x);delta_ref=write('delta-reference.bin',delta.astype(np.float32))
            c={'ordinal':1,'candidateInput':write('candidate.bin',candidate),'candidateIdentity':{'identity':{'split':'train'}},'originalCudaHeads':{'mask':mask,'presence':presence},'originalCudaDelta':delta_ref,'branches':{'wasm_dec1_0':{'firstGnInput':inputref,'presence':presence}}}
            gn={'groups':4,'epsilon':float(np.float32(1e-5))};p={'firstGroupNorm':gn,'lastGroupNorm':gn,'gelu':{'sqrt2FromOriginalFloat32':float(np.float32(math.sqrt(2))),'oneFromOriginalFloat32':1.,'halfFromOriginalFloat32':.5},'maximumOutputPixelsPerChunk':3}
            params={'firstGamma':np.ones((16,1,1),np.float32),'firstBeta':np.zeros((16,1,1),np.float32),'gamma':np.ones((16,1,1),np.float32),'beta':np.zeros((16,1,1),np.float32),'convWeight':kernel,'deltaWeight':dw,'deltaBias':bias};stages=[]
            def run(branch,stage,inputs,fn):
                stages.append(stage);a,stats=fn();return write(stage+'.bin',a),stats
            result=m.evaluate_case(c,p,params,run)['branches'][0]
            np.testing.assert_array_equal(m.read_tensor(result['mask32']),expected);self.assertTrue(result['counterfactualNumericPixelAndPresenceGatesPassed'])
            self.assertEqual(stages,['firstGn64','firstGelu64','conv64','lastGn64','lastGelu64','delta64','finalMaskAdd64','mask32'])
    def test_consumed_root_rejected_before_loading_any_inputs(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'resources',side_effect=RuntimeError('must not reach')) as res:
            with self.assertRaisesRegex(ValueError,'consumed'):m.execute(Path(tmp)/'execution.json',Path(tmp))
            res.assert_not_called()

if __name__=='__main__':unittest.main()
