import copy
import importlib.util
from pathlib import Path
import random
import unittest

R = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('translation', R/'model/training/marker-safe-roi-translation.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
audit_spec = importlib.util.spec_from_file_location('translation_audit', R/'model/training/audit-saved-marker-safe-roi-translation.py')
audit = importlib.util.module_from_spec(audit_spec); audit_spec.loader.exec_module(audit)


class TranslationTests(unittest.TestCase):
    def test_baseline_requires_complete_replay_not_just_equal_denominators(self):
        baseline={'acceptedCandidateReconstructionIdentical':True,'conclusionsAllowed':True,'counts':{'sources':2,'truthNails':4},'records':[{'identity':'a','candidateSHA':'abc','assignment':[1,2]},{'identity':'b','candidateSHA':'def','assignment':[1,2]}]}
        audit.require_identical_baseline(baseline,copy.deepcopy(baseline))
        for field,value in [('candidateSHA','changed'),('assignment',[2,1]),('identity','wrong')]:
            changed=copy.deepcopy(baseline);changed['records'][0][field]=value
            with self.assertRaisesRegex(ValueError,'reconstruction_mismatch'):audit.require_identical_baseline(baseline,changed)

    def test_identical_failed_fidelity_report_does_not_authorize_conclusions(self):
        bad={'acceptedCandidateReconstructionIdentical':False,'conclusionsAllowed':False}
        with self.assertRaisesRegex(ValueError,'fidelity not established'):audit.require_identical_baseline(bad,copy.deepcopy(bad))

    def test_edge_touch_and_no_marker_preserve_original(self):
        for halos in ([], [[15, 0, 20, 20]]):
            self.assertEqual(m.translate_crop([5, 5, 15, 15], [7, 7, 13, 13], halos, 20, 20)['cropBox'], [5, 5, 15, 15])

    def test_minimum_horizontal_translation_preserves_size_and_anchor(self):
        r = m.translate_crop([10, 10, 30, 30], [15, 15, 22, 22], [[27, 20, 35, 35]], 40, 40)
        self.assertEqual(r, {'decision': 'translated', 'cropBox': [7, 10, 27, 30], 'translation': [-3, 0]})

    def test_anchor_blocked_and_oversize_anchor_are_unreachable(self):
        for anchor, halos in [([17, 17, 23, 23], [[18, 18, 24, 24]]), ([0, 0, 25, 25], [[19, 19, 30, 30]])]:
            r = m.translate_crop([10, 10, 30, 30], anchor, halos, 40, 40)
            self.assertEqual(r['decision'], 'unreachable'); self.assertIsNone(r['cropBox'])

    def test_inputs_immutable_and_invalid_rectangles_rejected(self):
        args = [[10, 10, 30, 30], [15, 15, 22, 22], [[27, 20, 35, 35]]]; old = copy.deepcopy(args)
        m.translate_crop(*args, 40, 40); self.assertEqual(args, old)
        for crop in ([0, 0, 0, 5], [0.5, 0, 5, 5], [-1, 0, 5, 5], [0, 0, 41, 5]):
            with self.assertRaises(ValueError): m.translate_crop(crop, [1, 1, 2, 2], [], 40, 40)

    def test_global_minimum_against_exhaustive_integer_oracle_multiple_obstacles(self):
        rng = random.Random(3817)
        for _ in range(160):
            width, height = 19, 17; cw, ch = rng.randint(4, 10), rng.randint(4, 10)
            x, y = rng.randint(0, width-cw), rng.randint(0, height-ch); crop = [x,y,x+cw,y+ch]
            ax, ay = rng.randint(x,x+cw-2), rng.randint(y,y+ch-2); anchor=[ax,ay,ax+2,ay+2]
            halos=[]
            for j in range(rng.randint(1,4)):
                hx,hy=rng.randrange(width-1),rng.randrange(height-1);halos.append([hx,hy,min(width,hx+rng.randint(1,5)),min(height,hy+rng.randint(1,5))])
            actual=m.translate_crop(crop,anchor,halos,width,height)
            if not any(m.overlap_area(crop,h) for h in halos):
                self.assertEqual(actual['cropBox'],crop);continue
            candidates=[]
            for xx in range(width-cw+1):
                for yy in range(height-ch+1):
                    b=[xx,yy,xx+cw,yy+ch]
                    if not (xx<=anchor[0] and yy<=anchor[1] and b[2]>=anchor[2] and b[3]>=anchor[3]):continue
                    if any(m.overlap_area(b,h) for h in halos):continue
                    dx,dy=xx-x,yy-y;candidates.append(((dx*dx+dy*dy,abs(dx)+abs(dy),abs(dy),dy,dx,yy,xx),b))
            if candidates:self.assertEqual(actual['cropBox'],min(candidates)[1])
            else:self.assertEqual(actual['decision'],'unreachable')

if __name__ == '__main__': unittest.main()
