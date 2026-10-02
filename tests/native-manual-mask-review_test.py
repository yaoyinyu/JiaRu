import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result
audit = load('manual_review', 'model/training/audit-native-manual-mask-review.py')
builder = load('manual_builder', 'model/training/build-native-manual-mask-candidates.py')
geometry = load('manual_geometry', 'model/training/build-reviewed-manual-polygon-repair.py')


class ManualMaskReviewTests(unittest.TestCase):
    def setUp(self):
        def ref(name, char): return {'path': name, 'sha256': char * 64}
        self.record = {'ordinal': 1, 'fileName': 'nail.jpg', 'sourceGroup': 'group',
                       'sourceImage': ref('source', 'a'), 'sourceLabel': ref('old-label', 'b'),
                       'annotation': ref('new-annotation', 'c'), 'completeVisibleNails': 2,
                       'nativeSourceTiles': [{'image': ref('raw', 'd')}],
                       'nailPanels': [{'image': ref('pair1', 'e')}, {'image': ref('pair2', 'f')}]}
        self.decision = {k: copy.deepcopy(v) for k, v in self.record.items() if k not in ('nativeSourceTiles', 'nailPanels')}
        self.decision.update(reviewedNailIndices=[1, 2], failedNailIndices=[], decision=audit.PASS,
                             viewedArtifacts=[r['image'] for r in self.record['nativeSourceTiles'] + self.record['nailPanels']],
                             reviewEvidenceMode='direct_original_pixel_review', trainingUse='prohibited',
                             markerDecision='marker_ablation_pending', reason='whole source and both masks manually reviewed')

    def test_missing_page_reordered_nails_and_source_drift_rejected(self):
        audit.validate_visual(self.record, self.decision, None)
        for key, value in [('viewedArtifacts', self.decision['viewedArtifacts'][1:]),
                           ('reviewedNailIndices', [2, 1]), ('sourceGroup', 'different')]:
            d = copy.deepcopy(self.decision); d[key] = value
            with self.assertRaises(ValueError): audit.validate_visual(self.record, d, None)

    def test_training_promotion_and_failed_mask_pass_rejected(self):
        for key, value in [('trainingUse', 'allowed'), ('failedNailIndices', [1])]:
            d = copy.deepcopy(self.decision); d[key] = value
            with self.assertRaises(ValueError): audit.validate_visual(self.record, d, None)

    def test_prior_review_reuse_needs_exact_annotation_and_prior_pass(self):
        current = copy.deepcopy(self.record); current['annotation']['path'] = 'relocated'
        for r in current['nailPanels']: r['image']['path'] += '-relocated'
        d = copy.deepcopy(self.decision); d['annotation'] = current['annotation']
        d['reviewEvidenceMode'] = 'prior_approved_annotation_and_panels_sha256_identical'
        audit.validate_visual(current, d, self.decision)
        for key, value in [('failedNailIndices', [1]), ('decision', 'label_rework'),
                           ('annotation', {'path': 'prior', 'sha256': '0' * 64})]:
            prior = copy.deepcopy(self.decision); prior[key] = value
            with self.assertRaises(ValueError): audit.validate_visual(current, d, prior)

    def test_new_review_cannot_hide_prior_role_or_shrink_denominator(self):
        row = {k: copy.deepcopy(v) for k, v in self.record.items() if k not in ('nativeSourceTiles', 'nailPanels')}
        row.update(split='train', currentSourceDisposition='label_rework', historicalMaskCount=2,
                   upstreamDevelopmentSplit='train', parents=[{'sha256': '9' * 64}],
                   historicalRoiIds=['fixed1', 'fixed2'], markerStatus='pending', groupMarkerGate=None)
        excluded = {**copy.deepcopy(row), 'ordinal': 2, 'currentSourceDisposition': 'source_quality_excluded'}
        val = {**copy.deepcopy(row), 'ordinal': None, 'split': 'val', 'fileName': 'val.jpg'}
        baseline = {'currentFullSplitRecords': [row, excluded, val]}
        result = audit.apply_reviews(baseline, [self.decision], {})
        self.assertEqual(result[1:], baseline['currentFullSplitRecords'][1:])
        for key in ('parents', 'historicalRoiIds', 'upstreamDevelopmentSplit', 'markerStatus', 'groupMarkerGate'):
            self.assertEqual(result[0][key], row[key])
        self.assertFalse(result[0]['formalTrainingApproved'])
        self.assertEqual(result[0]['trainingUse'], 'prohibited')
        with self.assertRaises(ValueError): audit.apply_reviews({'currentFullSplitRecords': result}, [self.decision], {})
        d = copy.deepcopy(self.decision); d['completeVisibleNails'] = 1
        with self.assertRaises(ValueError): audit.apply_reviews(baseline, [d], {})

    def test_candidate_generation_requires_complete_unique_nails(self):
        source = {k: copy.deepcopy(self.record[k]) for k in ('ordinal', 'fileName', 'sourceGroup', 'sourceImage', 'sourceLabel')}
        source['fullyTraceableNails'] = 2
        drawing = {**copy.deepcopy(source), 'trainingUse': 'prohibited',
                   'nails': [{'truthIndex': i, 'status': 'candidate_only_pending_visual_review',
                              'annotationMethod': 'codex-original-pixel-manual-complete-outline'} for i in (1, 2)]}
        builder.validate_drawing(source, drawing)
        for indices in ([1], [1, 1], [2, 1], [1, 2, 3]):
            d = copy.deepcopy(drawing); d['nails'] = [{**d['nails'][0], 'truthIndex': i} for i in indices]
            with self.assertRaises(ValueError): builder.validate_drawing(source, d)

    def test_geometry_rejects_outside_self_intersection_and_overlap(self):
        def polygon(points): return {'polygon': [{'x': x, 'y': y} for x, y in points]}
        square = polygon([(1, 1), (8, 1), (8, 8), (1, 8)])
        with self.assertRaises(ValueError): geometry.normalize_points([{'x': -1, 'y': 3}] * 3, 10, 10)
        with self.assertRaises(ValueError): geometry.validate_polygons([polygon([(1, 1), (8, 8), (1, 8), (8, 1)])])
        with self.assertRaises(ValueError): geometry.validate_polygons([square, square])
        self.assertEqual(len(geometry.validate_polygons([square])), 1)

    def test_sha_binding_drift_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'report.json'; path.write_text('{}', encoding='utf-8')
            ref = audit.bind(path); audit.checked(ref)
            path.write_text('{"drift":true}', encoding='utf-8')
            with self.assertRaises(ValueError): audit.checked(ref)


if __name__ == '__main__': unittest.main()
