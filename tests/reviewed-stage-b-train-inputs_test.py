"""验证扩充原尺寸输入不会漏真值、回流val或把候选拒识当整块背景。"""
import copy
import importlib.util
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

R = Path(__file__).resolve().parents[1]
sp = importlib.util.spec_from_file_location('train_input_tests', R/'model/training/materialize-reviewed-stage-b-train-inputs.py')
m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m)


class Tests(unittest.TestCase):
    def cohort(self):
        identity = {'split': 'train', 'fileName': 'source.png', 'imageSha256': 'image'}
        source = {'identity': identity, 'sourceGroup': 'g', 'sourceImage': {'path': 'image', 'sha256': 'image'},
                  'annotation': {'path': 'annotation', 'sha256': 'ann'}, 'maskCount': 1, 'size': [20, 18]}
        prediction = {'path': 'prediction.npz', 'sha256': 'prediction'}
        diagnostic = {'identity': identity, 'sourceGroup': 'g', 'annotation': source['annotation'], 'size': [20, 18],
                      'truthNails': 1, 'truthMaskSha256': ['truth1'], 'candidates': 2,
                      'prediction': prediction, 'predictionMaskSha256': ['coarse1', 'coarse2'],
                      'primaryAssignment': [{'truthIndex': 1, 'predictionIndex': 1, 'roiFullTruthCoverage': True,
                                             'coarseMaskSeedValid': True}]}
        targets = [{'kind': 'complete_reviewed_nail_mask', 'truthIndex': 1, 'truthMaskSha256': 'truth1'},
                   {'kind': 'reject_same_candidate_only', 'truthIndex': None, 'emptyTargetIsNotNoNailsInRgbRoi': True}]
        records = [{'candidateIdentity': {'identity': identity, 'prediction': prediction, 'predictionIndex': j,
                                          'coarseMaskSha256': 'coarse'+str(j)},
                    'currentSplit': 'train', 'target': targets[j-1],
                    **{name: source[name] for name in ('sourceImage', 'annotation', 'sourceGroup', 'size')}}
                   for j in (1, 2)]
        plan = {'records': records, 'counts': {'train': {'sources': 1, 'sourceGroups': 1, 'truthNails': 1,
                                                       'candidateInputs': 2, 'positiveInputs': 1, 'rejectInputs': 1}},
                'fullTruthDenominator': 1, 'missingTruthsPreserved': [],
                'reachability': {'primaryFullRoiNails': 1, 'oracleFullRoiNails': 1, 'trainRatio': 1.0,
                                 'geometryOnlyNotSegmentationQuality': True}}
        return plan, [source], [diagnostic], {m.d.key(identity): [2]}

    def pixels(self):
        rgb = np.arange(20*24*3, dtype=np.uint8).reshape(20, 24, 3)
        coarse = np.zeros((20, 24), bool); coarse[7:12, 8:15] = True
        target = np.zeros_like(coarse); target[6:13, 7:16] = True
        return rgb, coarse, target

    def test_full_cohort(self):
        args = self.cohort()
        self.assertEqual(m.validate_cohort(*args), args[0]['counts'])

    def test_val_record_is_rejected(self):
        args = self.cohort(); args[0]['records'][0]['currentSplit'] = 'val'
        with self.assertRaisesRegex(ValueError, 'split drift'): m.validate_cohort(*args)

    def test_val_source_is_rejected_even_if_counts_match(self):
        args = copy.deepcopy(self.cohort()); args[1][0]['identity']['split'] = 'val'
        with self.assertRaisesRegex(ValueError, 'source denominator|non-train source'): m.validate_cohort(*args)

    def test_missing_truth_not_hidden_by_reduced_candidate_count(self):
        args = self.cohort(); args[2][0]['truthNails'] = args[1][0]['maskCount'] = 2
        args[2][0]['truthMaskSha256'].append('truth2')
        with self.assertRaisesRegex(ValueError, 'one-to-one truth assignment'): m.validate_cohort(*args)

    def test_two_candidates_cannot_claim_one_truth(self):
        args = self.cohort(); args[2][0]['primaryAssignment'].append(
            {'truthIndex': 1, 'predictionIndex': 2, 'roiFullTruthCoverage': True, 'coarseMaskSeedValid': True})
        with self.assertRaisesRegex(ValueError, 'one-to-one truth assignment'): m.validate_cohort(*args)

    def test_unreviewed_rejection_not_promoted(self):
        args = self.cohort(); args[3].clear()
        with self.assertRaisesRegex(ValueError, 'same-candidate rejection'): m.validate_cohort(*args)

    def test_candidate_seed_drift_is_rejected(self):
        args = self.cohort(); args[0]['records'][0]['candidateIdentity']['coarseMaskSha256'] = 'wrong'
        with self.assertRaisesRegex(ValueError, 'candidate identity/order/seed'): m.validate_cohort(*args)

    def test_duplicate_stable_source_identity_rejected(self):
        args = self.cohort(); args[1].append(copy.deepcopy(args[1][0]))
        with self.assertRaisesRegex(ValueError, 'source identity collision'): m.validate_cohort(*args)

    def test_reject_requires_candidate_only_meaning(self):
        args = self.cohort(); args[0]['records'][1]['target']['emptyTargetIsNotNoNailsInRgbRoi'] = False
        with self.assertRaisesRegex(ValueError, 'target or split drift'): m.validate_cohort(*args)

    def test_counts_cannot_be_copied_from_old_scope(self):
        args = self.cohort(); args[0]['counts']['train']['truthNails'] = 50
        with self.assertRaisesRegex(ValueError, 'truth/counts contract'): m.validate_cohort(*args)

    def test_native_rgb_and_full_truth_roundtrip(self):
        rgb, coarse, truth = self.pixels(); values = m.crop_native(rgb, coarse, truth, (5, 4, 18, 15), True)
        self.assertTrue(np.array_equal(values['nativeRgb'], rgb[4:15, 5:18]))
        self.assertEqual(int((values['nativeTarget'] > 0).sum()), int(truth.sum()))
        self.assertEqual(set(np.unique(values['nativeCoarse'])), {0, 255})

    def test_partial_truth_crop_rejected(self):
        rgb, coarse, truth = self.pixels()
        with self.assertRaisesRegex(ValueError, 'full truth lost'): m.crop_native(rgb, coarse, truth, (8, 7, 17, 14), True)

    def test_false_positive_seed_cannot_be_positive_truth(self):
        rgb, coarse, truth = self.pixels(); coarse[:] = False; coarse[1:3, 1:3] = True
        with self.assertRaisesRegex(ValueError, 'seed intersection'): m.crop_native(rgb, coarse, truth, (0, 0, 24, 20), True)

    def test_reject_keeps_rgb_with_neighbor_nail(self):
        rgb, coarse, truth = self.pixels()
        values = m.crop_native(rgb, coarse, np.zeros_like(truth), (5, 4, 18, 15), False)
        self.assertTrue(truth[4:15, 5:18].any())
        self.assertTrue(np.array_equal(values['nativeRgb'], rgb[4:15, 5:18]))
        self.assertFalse(values['nativeTarget'].any()); self.assertTrue(values['nativeCoarse'].any())

    def test_reject_cannot_hide_true_target(self):
        rgb, coarse, truth = self.pixels()
        with self.assertRaisesRegex(ValueError, 'rejection target'): m.crop_native(rgb, coarse, truth, (5, 4, 18, 15), False)

    def test_storage_domain_and_fractional_roi_rejected(self):
        rgb, coarse, truth = self.pixels()
        with self.assertRaisesRegex(ValueError, 'bool full-source'): m.crop_native(rgb, coarse, truth.astype(np.uint8), (5, 4, 18, 15), True)
        with self.assertRaisesRegex(ValueError, 'integer ROI'): m.crop_native(rgb, coarse, truth, (5.0, 4, 18, 15), True)

    def test_native_png_replay_detects_pixel_change(self):
        rgb, coarse, truth = self.pixels(); values = m.crop_native(rgb, coarse, truth, (5, 4, 18, 15), True)
        temp_root = R/'model/reviews/resize-test-temp'; temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as folder:
            path = Path(folder)/'native.png'; original = values['nativeTarget']
            first = m.native_file(path, original, False)
            self.assertEqual(m.native_file(path, original, True), first)
            changed = original.copy(); changed[0, 0] = 255
            Image.fromarray(changed).save(path)
            with self.assertRaisesRegex(ValueError, 'native pixel reconstruction'): m.native_file(path, original, True)


if __name__ == '__main__': unittest.main()
