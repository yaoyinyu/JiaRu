"""编码四格来源、原坐标交互、完整重算及证据篡改拒绝。"""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

import importlib.util
R = Path(__file__).resolve().parents[1]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


m = load(R / 'model/training/analyze-reviewed-encoder-cross-counterfactual.py', 'encoder_cross_test')
fixture = load(R / 'tests/reviewed-deep-decoder-counterfactual_test.py', 'encoder_cross_fixture')


class EncoderCrossTests(unittest.TestCase):
    def test_explicit_mixed_inputs_and_missing_or_unknown_origin_rejected(self):
        case = {'features': {name: {origin: name + origin for origin in ('cuda', 'wasm')} for name in ('enc2.5', 'enc3.5')}}
        for branch, expected in zip(m.BRANCHES, [('wasm', 'cuda'), ('cuda', 'wasm')], strict=True):
            _, refs = m.source_selection(case, branch)
            self.assertEqual(refs, {'enc2.5': 'enc2.5' + expected[0], 'enc3.5': 'enc3.5' + expected[1]})
        with self.assertRaises(ValueError): m.source_selection(case, 'unknown')
        del case['features']['enc2.5']['wasm']
        with self.assertRaises(KeyError): m.source_selection(case, m.BRANCHES[0])

    def test_both_mixed_full_chains_replay_and_match_explicit_pure_adapter(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / 'events').mkdir(); (root / 'results').mkdir()
            c, p, params, graph = fixture.test_case(root)
            for branch in m.BRANCHES:
                j = m.StageJournal(root, {}, c, branch)
                actual = m.evaluate(c, p, params, graph, j)
                self.assertEqual(actual, m.evaluate(c, p, params, graph, m.StageJournal(root, {}, c, branch, True)))
                choice, refs = m.source_selection(c, branch)
                self.assertEqual(actual['originalFeatureInputs'], refs)
                self.assertEqual(actual['encoderOrigins'], choice)
                self.assertEqual(actual['fixedSkip'], c['fixedWasmSkip'])
                self.assertEqual(actual['fixedPresence'], c['fixedWasmPresence'])
                # Independent explicit remapping into the already tested pure evaluator.
                mapped = copy.deepcopy(c)
                for key in ('enc2.5', 'enc3.5'):
                    mapped['features'][key]['cuda'] = refs[key]
                other = root / branch; other.mkdir(); (other / 'events').mkdir(); (other / 'results').mkdir()
                original = m.deep.evaluate(mapped, p, params, graph, m.deep.StageJournal(other, {}, mapped, m.deep.BRANCHES[0]))
                for left, right in zip(actual['stages'], original['stages'], strict=True):
                    self.assertEqual(left['output'], right['output'])
                self.assertEqual(actual['originalCudaParity'], original['originalCudaParity'])
                self.assertEqual(len([s for s in actual['stages'] if 'savedRaw' in s]), 2)
            self.assertEqual(len(list((root / 'events').glob('*.json'))), 76)
            self.assertEqual(len(list((root / 'results').glob('*.bin'))), 4)

    def test_signed_effects_use_original_actual_coordinate_and_axis_order(self):
        cc = np.zeros((1, 1, 1, 3), np.float32)
        enc2 = np.array([[[[8, 2, 1]]]], np.float32)
        enc3 = np.array([[[[1, -3, 9]]]], np.float32)
        ww = np.array([[[[10, 4, 12]]]], np.float32)
        original_w = np.array([[[[0, -20, 0]]]], np.float32)
        result = m.interaction(cc, ww, enc2, enc3, cc, original_w)
        self.assertEqual(result['coordinateOfOriginalActualMax'], [0, 0, 0, 1])
        self.assertEqual(result['signedAtSameCoordinate'], {'originalActualDifference': -20., 'mathematicalTotal': 4., 'enc2OnlyEffect': 2., 'enc3OnlyEffect': -3., 'interaction': 5.})
        self.assertEqual(result['equationResidualMaxAbs'], 0)
        self.assertEqual(result['enc2OnlyMaxAbs'], 8)
        self.assertEqual(result['enc3OnlyMaxAbs'], 9)
        with self.assertRaises(ValueError): m.interaction(cc.astype(np.float64), ww, enc2, enc3, cc, original_w)
        with self.assertRaises(ValueError): m.interaction(cc, ww[..., :2], enc2, enc3, cc, original_w)
        broken = ww.copy(); broken.flat[0] = np.nan
        with self.assertRaises(ValueError): m.interaction(cc, broken, enc2, enc3, cc, original_w)

    def test_original_input_or_unsaved_stage_tamper_rejected_on_recompute(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / 'events').mkdir(); (root / 'results').mkdir()
            c, p, params, graph = fixture.test_case(root)
            branch = m.BRANCHES[0]
            m.evaluate(c, p, params, graph, m.StageJournal(root, {}, c, branch))
            path = next((root / 'events').glob('*deepResize64-start.json'))
            raw = path.read_bytes(); value = json.loads(raw); value['inputs']['enc3.5'] = c['features']['enc3.5']['wasm']
            path.write_bytes(m.d.raw(value))
            with self.assertRaisesRegex(ValueError, 'start event'):
                m.evaluate(c, p, params, graph, m.StageJournal(root, {}, c, branch, True))
            path.write_bytes(raw)
            path = next((root / 'events').glob('*deepConv1_64-done.json'))
            value = json.loads(path.read_bytes()); value['output']['bytesSha256'] = hashlib.sha256(b'bad').hexdigest(); path.write_bytes(m.d.raw(value))
            with self.assertRaisesRegex(ValueError, 'full stage bytes'):
                m.evaluate(c, p, params, graph, m.StageJournal(root, {}, c, branch, True))

    def test_four_cell_denominator_and_identity_mismatch_refuses_conclusions(self):
        p = {'fullCandidateCount': 2, 'cases': [{}, {}]}
        with self.assertRaisesRegex(ValueError, 'denominator'): m.four_cell_records(p, [])
        p = {'fullCandidateCount': 1, 'cases': [{'ordinal': 1, 'candidateIdentity': {'id': 'a'}}]}
        with self.assertRaisesRegex(ValueError, 'identity'):
            m.four_cell_records(p, [{'ordinal': 1, 'candidateIdentity': {'id': 'b'}, 'branches': []}])

    def test_inherited_pure_events_records_and_saved_raw_are_verified(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / 'events').mkdir(); (root / 'results').mkdir()
            c, p, params, graph = fixture.test_case(root)
            p |= {'cases': [c], 'branches': m.deep.BRANCHES, 'fullCandidateCount': 1}
            m.d.new(root / 'scope.json', p)
            m.d.new(root / 'execution.json', {'sources': {}, 'runtime': {}, 'scope': m.d.bind(root / 'scope.json'), 'outputRoot': str(root)})
            execution = m.d.bind(root / 'execution.json')
            branches = [m.deep.evaluate(c, p, params, graph, m.StageJournal(root, execution, c, b)) for b in m.deep.BRANCHES]
            row = {'ordinal': c['ordinal'], 'candidateIdentity': c['candidateIdentity'], 'branches': branches}
            m.d.new(root / 'results/001-record.json', row)
            prior = {'inputs': {'execution': execution}, 'records': [row], 'summary': m.t.summarize(p, [row]),
                     'eventManifestSha256': hashlib.sha256(m.d.raw([m.d.bind(path) for path in sorted((root / 'events').iterdir())])).hexdigest()}
            ref = {'path': str(root / 'report.json'), 'sha256': 'fixture'}
            with patch.object(m.deep, 'sources', return_value={}), patch.object(m.t, 'runtime_binding', return_value={}):
                m.inherited_integrity(ref, prior, p)
                raw_path = Path(m.mask_ref(branches[0])['path'])
                raw_path.write_bytes(b'\0' * raw_path.stat().st_size)
                with self.assertRaises(ValueError): m.inherited_integrity(ref, prior, p)

    def test_contract_rejects_budget_storage_role_and_gate_changes(self):
        c = {'ordinal': 1, 'candidateIdentity': {'identity': {'split': 'train'}}, 'candidateInput': {'shape': [1, 4, 8, 12]}}
        p = {'cases': [c], 'fullCandidateCount': 1, 'branches': m.BRANCHES, 'branchSpecs': m.BRANCH_SPECS,
             'newBranchCandidateCount': 2, 'inheritedBranchCandidateCount': 2, 'fourCellCandidateCount': 4,
             'analyticalEvaluationsAllowed': {s: 2 for s in m.STAGES[:-1]} | {'total': 36},
             'singleFinalFloat32Conversions': 2, 'expectedRawCount': 4, 'expectedRawBytes': 13056,
             'storagePolicy': m.POLICY, 'savedStages': list(m.SAVED), 'orderedStages': list(m.STAGES),
             'requiredMaxAbs': 1e-4, 'requiredDecodedPixelDifferences': 0, 'requiredPresenceDecisionDifferences': 0,
             'productHold': True}
        for key in ('newProjectModelInputsAllowed', 'newSyntheticModelInputsAllowed', 'optimizerStepsAllowed', 'valInputsAllowed', 'protectedInputsAllowed', 'newChatImageInputsAllowed', 'actualFp32RepairOrWholeModelUnreachableProven', 'fullModelLearnedGatePassed', 'formalReleaseAllowed'): p[key] = 0
        m.validate_contract(p)
        for key, val in [('fourCellCandidateCount', 2), ('expectedRawBytes', 0), ('requiredMaxAbs', 2e-4), ('newProjectModelInputsAllowed', 1), ('savedStages', ['mask32'])]:
            broken = copy.deepcopy(p); broken[key] = val
            with self.assertRaises(ValueError): m.validate_contract(broken)
        broken = copy.deepcopy(p); broken['cases'][0]['candidateIdentity']['identity']['split'] = 'val'
        with self.assertRaises(ValueError): m.validate_contract(broken)


if __name__ == '__main__':
    unittest.main()
