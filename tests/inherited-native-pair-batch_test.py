"""合成元数据验证前置检查/保护角色/稳定身份；不模拟真实视觉通过。"""
import contextlib, copy, hashlib, importlib.util, json, os, tempfile, types, unittest
from pathlib import Path
R = Path(__file__).resolve().parents[1]

def module(version):
    p = R / 'model/training' / ('freeze-inherited-native-pair-batch-v2.py' if version == 2 else 'freeze-inherited-native-pair-batch.py')
    sp = importlib.util.spec_from_file_location('batch' + str(version), p)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m

def fixture(root, m, corrupt=False):
    v = root / 'model/reviews'
    v.mkdir(parents=True)
    sha = [x * 64 for x in 'abcd']
    owners = [{'split': 'train', 'fileName': 'owner' + str(i), 'imageSha256': x} for i, x in enumerate([sha[0], sha[2]])]

    def obs(i):
        return {'target': {'imageSha256': sha[2 * i], 'sourceImage': {'path': 'synthetic-' + sha[2 * i], 'sha256': sha[2 * i]}, 'ownerCurrentIdentities': [owners[i]], 'sourceGroups': ['g']}, 'reference': {'image': {'path': 'synthetic-' + sha[2 * i + 1], 'sha256': sha[2 * i + 1]}, 'roles': ['consumedPositiveTest'], 'trainingAllowed': False}}
    original = {'pairs': [{'pairIdentity': sorted([sha[2 * i], sha[2 * i + 1]]), 'observations': [obs(i)]} for i in range(2)]}
    rows = [{'originalQueueOrdinal': i + 1, 'pairIdentity': x['pairIdentity'], 'classification': 'currentCandidateRelated', 'observations': [dict(copy.deepcopy(x['observations'][0]), candidateOwnerIdentities=[owners[i]])]} for i, x in enumerate(original['pairs'])]
    if corrupt:
        rows[1]['observations'][0]['reference']['roles'] = ['tampered_role']

    def store(n, x):
        p = v / n
        p.write_bytes((json.dumps(x, ensure_ascii=False, indent=2) + '\n').encode())
        return m.bind(p)
    ore = store('original.json', original)
    d = {'inputs': {'queue': ore}, 'pendingPairIdentities': [x['pairIdentity'] for x in original['pairs']], 'newActuallyReviewedDecisions': [], 'inheritedDecisions': [], 'currentUncertainPairDecisions': [], 'counts': {}, 'combinedReviewedPairs': 0, 'combinedUniquePairs': 2}
    pr = {'allPendingRecordsPreserved': rows, 'deferredOriginalSevenUncertain': [], 'originalCounts': {}}
    count = {'sources': 2}
    scope = {k: {} for k in ['currentCounts', 'currentSourceParentQualificationIsolation', 'currentTrainingAdmissionEvidence', 'currentI016LocalPixelDiagnostic', 'currentPositiveOnlyRegistration', 'currentAlbumSupplementalProtectedReuse', 'currentAlbumDelta234Governance']}
    scope.update({'groups': [], 'prospectiveCandidateCounts': count, 'inputs': {}})
    ledger = {'currentCandidateCounts': count, 'trainingAllowed': False, 'sourceParentQualificationInventory': [{'identity': x} for x in owners]}
    reg = {'images': []}
    for value in sha:
        image = {'image': {'path': 'synthetic-' + value, 'sha256': value}, 'originalSize': [1, 1], 'originalRgbSha256': hashlib.sha256(b'rgb').hexdigest(), 'pages': []}
        rr = store('view-report-' + value + '.json', {'images': [image]})
        ar = store('actual-' + value + '.json', {'inputs': {'reviewReport': rr}})
        reg['images'].append({'imageSha256': value, 'actualView': ar, 'originalSize': [1, 1], 'originalRgbSha256': image['originalRgbSha256'], 'pages': []})
    refs = {k: store(k + '.json', x) for k, x in {'priority': pr, 'scope': scope, 'disposition': d, 'registry': reg, 'preparation': {'records': [], 'counts': {}, 'nextExecutableMilestone': {}}, 'ledger': ledger, 'audit': {'counts': count, 'gates': {'g': False}}, 'guardPlanReport': {}}.items()}
    manual = [{'queueOrdinal': 1, 'pairIdentity': rows[0]['pairIdentity'], 'decision': 'visually_distinct', 'reason': 'synthetic control-flow-only reason', 'priorPairConclusionNotInherited': True, 'referenceBindingExpected': rows[0]['observations'][0]['reference']}]
    names = {k: 'output-' + k + '.json' for k in ['review', 'disposition', 'scopeIntermediate', 'priority', 'scope', 'preparation']}
    plan = {'inputs': refs, 'maximumPairs': 1, 'selectedOriginalQueueOrdinals': [1], 'manualDecisions': manual, 'outputs': names}
    ref = store('plan.json', plan)
    return (ref, plan, v, original, pr, d, ledger)

class Tests(unittest.TestCase):

    def temp(self):
        base = R / 'model/reviews/test-temp'
        base.mkdir(exist_ok=True)
        return tempfile.TemporaryDirectory(prefix='inherited-batch-', dir=base)

    def fake_pixel_modules(self, m):
        raw = types.SimpleNamespace(size=(1, 1), tobytes=lambda: b'rgb')
        layout = types.SimpleNamespace(guarded_pixels=lambda _: contextlib.nullcontext(), check_pixels=lambda _: None, load_rgb=lambda _: raw)
        reuse = types.SimpleNamespace(validate_record=lambda *_: None)
        m.module = lambda n, p: layout if 'layout' in n else reuse

    def test_nonconsecutive_order(self):
        m = module(2)
        p = {'allPendingRecordsPreserved': [{'originalQueueOrdinal': 51, 'classification': 'currentCandidateRelated'}, {'originalQueueOrdinal': 49, 'classification': 'isolatedGroupRelated'}, {'originalQueueOrdinal': 47, 'classification': 'currentCandidateRelated'}, {'originalQueueOrdinal': 48, 'classification': 'currentCandidateRelated'}]}
        self.assertEqual([x['originalQueueOrdinal'] for x in m.select(p, 3)], [47, 48, 51])
        self.assertRaises(AssertionError, m.select, p, 13)

    def test_hidden_pending_role_drift_rejected_before_pixels_or_output(self):
        m = module(2)
        with self.temp() as tmp:
            m.ROOT = Path(tmp)
            ref, plan, v, *_ = fixture(m.ROOT, m, True)
            m.module = lambda *_: (_ for _ in ()).throw(RuntimeError('pixel stage unexpectedly reached'))
            with self.assertRaises(AssertionError):
                m.build(ref, False)
            self.assertEqual(list(v.glob('output-*.json')), [])

    def test_legacy_fixture_demonstrates_late_write_problem(self):
        m = module(1)
        with self.temp() as tmp:
            m.ROOT = Path(tmp)
            ref, plan, v, *_ = fixture(m.ROOT, m, True)
            self.fake_pixel_modules(m)
            with self.assertRaises(AssertionError):
                m.build(ref, False)
            self.assertEqual(len(list(v.glob('output-*.json'))), 3)

    def test_same_capture_requires_separate_isolation_workflow(self):
        m = module(2)
        with self.temp() as tmp:
            m.ROOT = Path(tmp)
            ref, plan, v, *_ = fixture(m.ROOT, m)
            plan['manualDecisions'][0]['decision'] = 'same_capture_series_association'
            with self.assertRaises(AssertionError):
                m.validate_manual(m.select(m.read(plan['inputs']['priority']), 1), plan['manualDecisions'])

    def test_output_escape_rejected_before_pixels(self):
        m = module(2)
        with self.temp() as tmp:
            m.ROOT = Path(tmp)
            ref, plan, v, *_ = fixture(m.ROOT, m)
            plan['outputs']['review'] = '../../escaped.json'
            Path(ref['path']).write_bytes((json.dumps(plan) + '\n').encode())
            ref = m.bind(Path(ref['path']))
            m.module = lambda *_: (_ for _ in ()).throw(RuntimeError('pixel stage unexpectedly reached'))
            with self.assertRaises(AssertionError):
                m.build(ref, False)
            self.assertFalse((m.ROOT / 'escaped.json').exists())
            self.assertEqual(list(v.glob('output-*.json')), [])

    def test_stable_owner_split_is_required(self):
        m = module(2)
        with self.temp() as tmp:
            m.ROOT = Path(tmp)
            ref, plan, v, original, p, d, l = fixture(m.ROOT, m)
            l = copy.deepcopy(l)
            l['sourceParentQualificationInventory'][1]['identity']['split'] = 'val'
            with self.assertRaises(AssertionError):
                m.project_pending(original, p, d, set(map(tuple, d['pendingPairIdentities'])), l['sourceParentQualificationInventory'])
if __name__ == '__main__':
    unittest.main(verbosity=2)
