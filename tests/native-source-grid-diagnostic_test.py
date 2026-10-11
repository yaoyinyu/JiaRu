import contextlib,hashlib,importlib.util,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
R=Path(__file__).resolve().parents[1]
sp=importlib.util.spec_from_file_location('grid_fixture',R/'model/training/native-source-grid-diagnostic.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)

class GridDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.tiles=[Image.new('RGB',(16,24),(20*n,10*n,5*n)) for n in range(9)]
        self.target=Image.new('RGB',(48,72))
        for n,tile in enumerate(self.tiles):self.target.paste(tile,((n%3)*16,(n//3)*24))
        self.spec={'rows':3,'columns':3,'positiveExpectedCell':2,'positiveMaximumMaeNormalizedRgb':12/255,'positiveMaximumBestToSecondRatio':0.5,'candidateHypothesisCell':1}
    def test_known_exact_cells_and_original_buffers_preserved(self):
        before=self.target.tobytes();r=m.diagnose(self.target,self.tiles[1],self.tiles[0],self.spec)
        self.assertTrue(r['positiveControlPassed']);self.assertEqual(r['candidateComparison']['bestCellOrdinal'],1)
        self.assertEqual(r['candidateComparison']['bestMaeNormalizedRgb'],0);self.assertFalse(r['nativeVisualApproved']);self.assertFalse(r['trainingAllowed']);self.assertEqual(self.target.tobytes(),before)
    def test_failed_positive_stops_candidate_scoring(self):
        with patch.object(m,'score_grid',wraps=m.score_grid) as score:
            r=m.diagnose(self.target,self.tiles[8],self.tiles[0],self.spec)
        self.assertFalse(r['positiveControlPassed']);self.assertIsNone(r['candidateComparison']);self.assertEqual(score.call_count,1)
    def test_tied_control_never_passes(self):
        r=m.diagnose(Image.new('RGB',(48,72)),Image.new('RGB',(16,24)),self.tiles[0],self.spec)
        self.assertFalse(r['positiveControl']['uniqueBestCell']);self.assertFalse(r['positiveControlPassed'])
    def test_uint8_difference_does_not_wrap(self):
        a=np.zeros((2,2,3),dtype=np.uint8);b=np.full((2,2,3),255,dtype=np.uint8)
        self.assertEqual(m.metric(a,b),{'maeNormalizedRgb':1.0,'rmseNormalizedRgb':1.0})
    def test_geometry_and_storage_domain_reject_drift(self):
        for size in [(49,72),(48,73)]:
            with self.assertRaises(ValueError):m.grid_boxes(size,3,3)
        with self.assertRaises(ValueError):m.score_grid(self.target.convert('L'),self.tiles[0],3,3)
        with self.assertRaises(ValueError):m.metric(np.zeros((2,2),dtype=np.uint8),np.zeros((2,2),dtype=np.uint8))
    def test_guard_failure_precedes_pixel_decode(self):
        class Fake:
            @contextlib.contextmanager
            def guarded_pixels(self,report):raise RuntimeError('guard installation failed');yield
            def load_rgb(self,ref):raise AssertionError('pixel decode attempted')
        with self.assertRaisesRegex(RuntimeError,'guard installation failed'):m.guarded_rgb_sources(Fake(),{}, {'target':{}})
    def test_cleanup_follows_all_pixel_scoring(self):
        events=[];im=self.tiles[0]
        class Fake:
            @contextlib.contextmanager
            def guarded_pixels(self,report):
                events.append('guard')
                try:yield
                finally:events.append('cleanup')
            def load_rgb(self,ref):events.append('decode');return im
        entry={'image':{},'originalSize':[16,24],'originalRgbSha256':hashlib.sha256(im.tobytes()).hexdigest()}
        def score(images):events.append('score');return images['target'].size
        self.assertEqual(m.guarded_rgb_sources(Fake(),{}, {'target':entry},score),(16,24))
        self.assertEqual(events,['guard','decode','score','cleanup'])

if __name__=='__main__':unittest.main()
