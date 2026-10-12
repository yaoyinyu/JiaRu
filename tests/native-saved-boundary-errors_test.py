"""原像素边界分布的分区保真和存储域拒绝。"""
import importlib.util, unittest
from pathlib import Path
import numpy as np
spec=importlib.util.spec_from_file_location('boundary_errors',Path(__file__).resolve().parents[1]/'model/training/analyze-native-saved-boundary-errors.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Tests(unittest.TestCase):
    def test_errors_partition_and_native_radius(self):
        truth=np.zeros((64,64),bool);truth[20:44,20:44]=True
        prediction=truth.copy();prediction[20,25:35]=False;prediction[3,3]=True
        logits=np.where(prediction,4.,-4.).astype(np.float32)
        r=m.boundary_error_distribution(truth,prediction,logits)
        self.assertEqual(r['errorPixels'],11)
        for strip in r['cumulativeOriginalPixelStrips'].values():
            self.assertEqual(strip['errorPixels']+strip['outsideErrorPixels'],11)
        self.assertEqual(r['cumulativeOriginalPixelStrips']['2']['errorPixels'],10)
        self.assertEqual(r['cumulativeOriginalPixelStrips']['8']['outsideErrorPixels'],1)
        self.assertLess(r['cumulativeOriginalPixelStrips']['2']['roiFraction'],r['cumulativeOriginalPixelStrips']['8']['roiFraction'])
    def test_invalid_storage_and_nonfinite_rejected(self):
        truth=np.ones((16,16),bool);logits=np.ones((16,16),np.float32)
        with self.assertRaises(ValueError):m.boundary_error_distribution(truth,truth,logits.astype(np.float64))
        logits[3,3]=np.nan
        with self.assertRaises(ValueError):m.boundary_error_distribution(truth,truth,logits)
if __name__=='__main__':unittest.main()
