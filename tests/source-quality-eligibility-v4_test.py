"""资格投影须拒绝被排除记录漂移、缩放实看和覆盖/缺口误写。"""
import importlib.util, json, tempfile, unittest
from pathlib import Path
R = Path(__file__).resolve().parents[1]
sp = importlib.util.spec_from_file_location('source_quality_eligibility', R / 'model/training/audit-source-quality-eligibility-v4.py')
m = importlib.util.module_from_spec(sp)
sp.loader.exec_module(m)

class IntegrityTests(unittest.TestCase):

    def test_reversed_coverage_rejected(self):
        rows = [{'identity': {'split': 'train', 'fileName': f'{i}.jpg', 'imageSha256': str(i)}, 'maskCount': i + 1} for i in range(3)]
        wrong = {'requiredSources': 3, 'requiredNails': 6, 'coveredSources': 2, 'coveredNails': 5, 'missingSources': 1, 'missingNails': 1, 'missingIdentities': [rows[1]['identity'], rows[2]['identity']], 'complete': False}
        with self.assertRaisesRegex(ValueError, 'coverage counter mismatch'):
            m.project_coverage(wrong, rows, rows[:1])

    def fixture(self, root):

        def write(name, x):
            p = root / name
            p.write_text(json.dumps(x), encoding='utf-8')
            return m.bind(p)
        image = root / 'source.jpg'
        image.write_bytes(b'stable-image-fixture')
        ann = root / 'annotation.json'
        ann.write_bytes(b'stable-annotation-fixture')
        identity = {'split': 'train', 'fileName': 'source.jpg', 'imageSha256': m.bind(image)['sha256']}
        row = {'identity': identity, 'sourceGroup': 'source-group', 'sourceImage': m.bind(image), 'annotation': m.bind(ann), 'maskCount': 1}
        role = {'identity': identity, 'sourceGroup': 'source-group', 'trainingUse': 'prohibited', 'formalTrainingApproved': False}
        cov = {'requiredSources': 1, 'requiredNails': 1, 'coveredSources': 0, 'coveredNails': 0, 'missingSources': 1, 'missingNails': 1, 'missingIdentities': [identity], 'complete': False}
        ledger = {'sourceParentQualificationInventory': [row], 'currentCandidateCounts': m.counts([row]), 'nativeInputControls': cov, 'conditionalInputs': cov}
        ready = {'records': [{'identity': identity, 'source': row['sourceImage'], 'annotation': row['annotation'], 'sourceGroup': 'source-group', 'maskCount': 1, 'minimumNativeNailShortSidePixels': 10, 'minimumNativeNailAreaPixels': 100, 'exactPriorNativeView': None}]}
        digest = m.hashlib.sha256(json.dumps(role, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        review = {'identity': identity, 'sourceGroup': 'source-group', 'annotation': row['annotation'], 'maskCountPreserved': 1, 'actuallyViewed': True, 'toolScalingNotice': False, 'nativePixelCoverageComplete': True, 'noResamplingOrReencoding': True, 'wholeSourcePage': {'page': row['sourceImage']}, 'currentRoleRecordSha256Preserved': digest, 'decision': 'source_quality_excluded', 'trainingAllowed': False, 'trainingUse': 'prohibited', 'actualModelImageInputs': 1, 'actualToolEncodedImageBytes': 20}
        return (write, ledger, ready, role, review)

    def run_fixture(self, mutate):
        temp_root = R / 'model/reviews/test-temp'
        temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as tmp:
            root = Path(tmp)
            write, ledger, ready, role, review = self.fixture(root)
            mutate(ready, review)
            refs = {'priorLedger': write('ledger.json', ledger), 'readiness': write('ready.json', ready), 'roles': write('roles.json', {'records': [role]})}
            plan = write('plan.json', {'inputs': refs, 'qualityReviews': [write('review.json', review)]})
            return m.analyze(plan)

    def test_excluded_record_drift_not_hidden(self):
        with self.assertRaisesRegex(ValueError, 'original truth drift'):
            self.run_fixture(lambda ready, review: ready['records'][0].update(maskCount=2))

    def test_scaled_actual_view_not_accepted(self):
        with self.assertRaisesRegex(ValueError, 'missing native visual evidence'):
            self.run_fixture(lambda ready, review: review.update(toolScalingNotice=True))

    def test_exclusion_keeps_original_and_blocks_training(self):
        x = self.run_fixture(lambda ready, review: None)
        self.assertEqual(x['originalCandidateCountsPreserved']['combinedSources'], 1)
        self.assertEqual(x['currentQualityEligibleCounts']['combinedSources'], 0)
        self.assertEqual(len(x['originalCandidateInventoryPreserved']), 1)
        self.assertFalse(x['trainingAllowed'])
        self.assertTrue(x['currentContractMustBindNewEligibilityBeforeTraining'])

    def test_new_stock_separate_from_existing_views(self):
        x = self.run_fixture(lambda ready, review: review.update(newUniqueStockImages=1, newUniqueStockPages=1))
        self.assertEqual(x['newUniqueStockImages'], 1)
        self.assertEqual(x['newUniqueStockPages'], 1)
        self.assertFalse(x['trainingAllowed'])

    def test_runner_identity_drift_rejected(self):
        with tempfile.TemporaryDirectory(dir=R / 'model/reviews/test-temp') as tmp:
            root = Path(tmp)
            fake = root / 'fake-runner.py'
            fake.write_text('different runner', encoding='utf-8')
            plan = root / 'plan.json'
            plan.write_text(json.dumps({'inputs': {'runner': m.bind(fake)}}), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'runner identity'):
                m.analyze(m.bind(plan))

class PageIntegrityTests(unittest.TestCase):

    def fixture(self, root):
        identity = {'split': 'train', 'fileName': 'native.png', 'imageSha256': 'fixture-source'}

        def save(name, value):
            path = root / name
            path.write_text(json.dumps(value), encoding='utf-8')
            return m.bind(path)
        pages = []
        for i in range(2):
            path = root / f'page-{i}.bin'
            path.write_bytes(bytes([i]))
            pages.append({'page': m.bind(path), 'sourceBox': [i, 0, i + 1, 1], 'size': [1, 1], 'pageOrigin': [0, 0], 'fileBytes': 1, 'resampling': False})
        prep = save('prep.json', {'records': [{'identity': identity, 'reviewPages': pages, 'originalSize': [2, 1], 'originalRgbSha256': 'fixture-rgb'}]})
        entries = [{'identity': identity, 'pageOrdinal': i + 1, 'reviewPage': pg, 'inputs': {'preparation': prep}, 'actuallyViewed': True, 'toolScalingNotice': False, 'coordinateOriginsChecked': True, 'actualModelImageInputs': 1, 'actualToolEncodedImageBytes': 1} for i, pg in enumerate(pages)]
        refs = [save(f'actual-{i}.json', entry) for i, entry in enumerate(entries)]
        row = {'identity': identity, 'inputs': {'preparation': prep}, 'reviewPages': pages, 'actualPageBindings': refs, 'originalSize': [2, 1], 'originalRgbSha256': 'fixture-rgb', 'actualToolEncodedImageBytes': 2, 'actualModelImageInputs': 2}
        return (row, entries, save)

    def run_fixture(self, mutation):
        with tempfile.TemporaryDirectory(dir=R / 'model/reviews/test-temp') as tmp:
            row, entries, save = self.fixture(Path(tmp))
            mutation(row, entries, save)
            m.validate_review_page_bindings(row, {'size': [2, 1]})

    def test_all_pages_bound(self):
        self.run_fixture(lambda row, entries, save: None)

    def test_missing_page_cannot_claim_complete(self):
        with self.assertRaisesRegex(ValueError, 'missing actual review pages'):
            self.run_fixture(lambda row, entries, save: row.update(actualPageBindings=row['actualPageBindings'][:1]))

    def test_duplicate_actual_page_rejected(self):
        with self.assertRaisesRegex(ValueError, 'duplicate or wrong actual review page'):
            self.run_fixture(lambda row, entries, save: row.update(actualPageBindings=[row['actualPageBindings'][0]] * 2))

    def test_scaled_subpage_rejected(self):

        def mutate(row, entries, save):
            entries[1]['toolScalingNotice'] = True
            row['actualPageBindings'][1] = save('scaled-actual.json', entries[1])
        with self.assertRaisesRegex(ValueError, 'invalid actual page viewing evidence'):
            self.run_fixture(mutate)

    def test_whole_image_policy_rejects_new_tiles(self):
        def mutate(row, entries, save):
            policy = save('whole-policy.json', {'wholeImageOnly': True, 'singleImageFileAndPayloadLimitBytes': 8388608})
            plan = save('whole-plan.json', {'inputs': {'humanPolicy': policy}})
            prep = m.read(row['inputs']['preparation'])
            prep['inputs'] = {'plan': plan}
            row['inputs']['preparation'] = save('whole-prep.json', prep)
            row['wholeImageOnly'] = True
        with self.assertRaisesRegex(ValueError, 'whole image policy rejects'):
            self.run_fixture(mutate)

    def test_normal_large_whole_transport_metadata_accepted(self):
        # 本用例只验证发送元数据；真实像素保真由生产准备器独立核验。
        with tempfile.TemporaryDirectory(dir=R / 'model/reviews/test-temp') as tmp:
            root = Path(tmp)
            row, entries, save = self.fixture(root)
            binary = root / 'large-whole-metadata-fixture.bin'
            binary.write_bytes(b'a' * (2 * 1024 * 1024))
            pg = {'page': m.bind(binary), 'sourceBox': [0, 0, 2, 1], 'size': [2, 1], 'pageOrigin': [0, 0], 'fileBytes': binary.stat().st_size, 'resampling': False}
            policy = save('policy.json', {'wholeImageOnly': True, 'singleImageFileAndPayloadLimitBytes': 8388608})
            plan = save('plan.json', {'inputs': {'humanPolicy': policy}})
            prep = save('prep-whole.json', {'inputs': {'plan': plan}, 'records': [{'identity': row['identity'], 'reviewPages': [pg], 'originalSize': [2, 1], 'originalRgbSha256': 'fixture-rgb'}]})
            entry = dict(entries[0], reviewPage=pg, inputs={'preparation': prep}, actualToolEncodedImageBytes=pg['fileBytes'])
            row.update(inputs={'preparation': prep}, reviewPages=[pg], actualPageBindings=[save('actual-whole.json', entry)], actualModelImageInputs=1, actualToolEncodedImageBytes=pg['fileBytes'], wholeImageOnly=True)
            m.validate_review_page_bindings(row, {'size': [2, 1]})
if __name__ == '__main__':
    unittest.main()
