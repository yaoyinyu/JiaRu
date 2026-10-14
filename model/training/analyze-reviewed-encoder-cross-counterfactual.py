"""完整enc2/enc3四格条件数学诊断；旧纯域继承，新交叉逐阶段重算。"""
import argparse
import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('encoder_cross_deep', HERE / 'analyze-reviewed-deep-decoder-counterfactual.py')
deep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deep)
u, m, t, d = deep.u, deep.m, deep.t, deep.d
STAGES, SAVED, POLICY = deep.STAGES, deep.SAVED, deep.POLICY
StageJournal, resize_propagated64 = deep.StageJournal, deep.resize_propagated64
BRANCH_SPECS = [
    {'name': 'enc2_wasm_enc3_cuda_fixed_wasm_skip', 'enc2Origin': 'wasm', 'enc3Origin': 'cuda'},
    {'name': 'enc2_cuda_enc3_wasm_fixed_wasm_skip', 'enc2Origin': 'cuda', 'enc3Origin': 'wasm'},
]
BRANCHES = [row['name'] for row in BRANCH_SPECS]


def sources():
    return deep.sources() | {Path(__file__).name: d.bind(__file__)}


def source_selection(case, branch):
    choices = [row for row in BRANCH_SPECS if row['name'] == branch]
    if len(choices) != 1:
        raise ValueError('explicit enc2/enc3 origin selection')
    choice = choices[0]
    refs = {key: case['features'][key][choice[origin]] for key, origin in
            [('enc2.5', 'enc2Origin'), ('enc3.5', 'enc3Origin')]}
    return choice, refs


def interaction(cc, ww, wc, cw, original_cuda, original_wasm):
    """格顺序为enc2、enc3；在同一原实际失败坐标分解，不加独立最大值。"""
    arrays = [np.asarray(a) for a in (cc, ww, wc, cw, original_cuda, original_wasm)]
    if any(a.dtype != np.float32 or a.shape != arrays[0].shape or not a.size or not np.isfinite(a).all() for a in arrays):
        raise ValueError('same native finite original F32 cells and head domains')
    c, w, enc2, enc3, original_c, original_w = [a.astype(np.float64) for a in arrays]
    total, effect2, effect3 = w - c, enc2 - c, enc3 - c
    coupling = w - enc2 - enc3 + c
    residual = float(np.abs(total - (effect2 + effect3 + coupling)).max())
    if residual > 1e-12:
        raise ValueError('same-coordinate four-cell identity')
    at = tuple(int(i) for i in np.unravel_index(np.abs(original_w - original_c).argmax(), c.shape))
    return {'cellAxisOrder': ['enc2Origin', 'enc3Origin'], 'equationResidualMaxAbs': residual,
            'coordinateOfOriginalActualMax': list(at),
            'signedAtSameCoordinate': {'originalActualDifference': float((original_w - original_c)[at]),
                                      'mathematicalTotal': float(total[at]), 'enc2OnlyEffect': float(effect2[at]),
                                      'enc3OnlyEffect': float(effect3[at]), 'interaction': float(coupling[at])},
            'mathematicalTotalMaxAbs': float(np.abs(total).max()), 'enc2OnlyMaxAbs': float(np.abs(effect2).max()),
            'enc3OnlyMaxAbs': float(np.abs(effect3).max()), 'interactionMaxAbs': float(np.abs(coupling).max()),
            'conditionalActivationOracleNotOperatorCausalityOrActualRepair': True}


def validate_contract(p):
    count = len(p['cases'])
    if count <= 0 or p['fullCandidateCount'] != count or p['branches'] != BRANCHES or p['branchSpecs'] != BRANCH_SPECS:
        raise ValueError('complete explicit branch and candidate denominator')
    if [c['ordinal'] for c in p['cases']] != list(range(1, count + 1)) or any(c['candidateIdentity']['identity']['split'] != 'train' for c in p['cases']):
        raise ValueError('complete ordered train identities')
    if (p['newBranchCandidateCount'], p['inheritedBranchCandidateCount'], p['fourCellCandidateCount']) != (2 * count, 2 * count, 4 * count):
        raise ValueError('separate inherited/new/four-cell denominators')
    expected = {stage: 2 * count for stage in STAGES[:-1]} | {'total': 2 * count * (len(STAGES) - 1)}
    size = sum(2 * (32 * (c['candidateInput']['shape'][2] // 2) * (c['candidateInput']['shape'][3] // 2) * 8 +
                    c['candidateInput']['shape'][2] * c['candidateInput']['shape'][3] * 4) for c in p['cases'])
    if p['analyticalEvaluationsAllowed'] != expected or p['singleFinalFloat32Conversions'] != 2 * count or p['expectedRawCount'] != 4 * count or p['expectedRawBytes'] != size:
        raise ValueError('new stage/rounding/storage budgets')
    if p['storagePolicy'] != POLICY or p['savedStages'] != list(SAVED) or p['orderedStages'] != list(STAGES):
        raise ValueError('all-stage hashes and boundary-only storage contract')
    if p['requiredMaxAbs'] != 1e-4 or p['requiredDecodedPixelDifferences'] != 0 or p['requiredPresenceDecisionDifferences'] != 0:
        raise ValueError('unchanged final head gates')
    if any(p[key] for key in ('newProjectModelInputsAllowed', 'newSyntheticModelInputsAllowed', 'optimizerStepsAllowed', 'valInputsAllowed', 'protectedInputsAllowed', 'newChatImageInputsAllowed', 'actualFp32RepairOrWholeModelUnreachableProven', 'fullModelLearnedGatePassed', 'formalReleaseAllowed')) or not p['productHold']:
        raise ValueError('zero model budget and conditional diagnosis only')


def inherited_integrity(pure_ref, prior, old):
    """继承已独立重算的纯域；原事件、保存RAW及完整分母均重新验真。"""
    execution = d.read(prior['inputs']['execution'])
    root = Path(pure_ref['path']).parent
    if execution['sources'] != deep.sources() or execution['runtime'] != t.runtime_binding() or d.read(execution['scope']) != old or execution['outputRoot'] != str(root):
        raise ValueError('inherited frozen sources/runtime/scope/root')
    events = []
    for case, row in zip(old['cases'], prior['records'], strict=True):
        if row['ordinal'] != case['ordinal'] or row['candidateIdentity'] != case['candidateIdentity'] or [b['branch'] for b in row['branches']] != deep.BRANCHES:
            raise ValueError('inherited complete stable identities')
        if d.read(d.bind(root / 'results' / f'{case["ordinal"]:03d}-record.json')) != row:
            raise ValueError('inherited entire candidate record')
        for branch in row['branches']:
            if [s['stage'] for s in branch['stages']] != list(STAGES):
                raise ValueError('inherited stage denominator')
            for stage in branch['stages']:
                stem = f'{case["ordinal"]:03d}-{branch["branch"]}-{stage["stage"]}'
                start_path = root / 'events' / (stem + '-start.json')
                done_path = root / 'events' / (stem + '-done.json')
                start = {'execution': prior['inputs']['execution'], 'ordinal': case['ordinal'], 'candidateIdentity': case['candidateIdentity'],
                         'branch': branch['branch'], 'stage': stage['stage'], 'inputs': stage['inputs']}
                if d.read(d.bind(start_path)) != start or d.read(d.bind(done_path)) != stage:
                    raise ValueError('inherited start/done input binding')
                events.extend((start_path, done_path))
                if ('savedRaw' in stage) != (stage['stage'] in SAVED):
                    raise ValueError('inherited saved-stage contract')
                if 'savedRaw' in stage and deep.descriptor(t.read_tensor(stage['savedRaw'])) != stage['output']:
                    raise ValueError('inherited complete saved RAW bytes')
    if sorted(events) != sorted((root / 'events').iterdir()) or hashlib.sha256(d.raw([d.bind(path) for path in sorted(events)])).hexdigest() != prior['eventManifestSha256']:
        raise ValueError('inherited complete event manifest')
    if t.summarize(old, prior['records']) != prior['summary']:
        raise ValueError('inherited full final-gate summary')


def derive(design_ref):
    design = d.read(design_ref)
    if design['purpose'] != 'complete74_enc2_enc3_four_cell_math_design_only' or any(design[k] for k in ('analyticalBudgetAllocatedNow', 'newProjectModelInputsAllowedNow', 'newSyntheticModelInputsAllowedNow')):
        raise ValueError('original pre-budget encoder-cross design')
    for ref in design['inputs'].values():
        d.checked(ref)
    prior = d.read(design['inputs']['pureMath'])
    replay = d.read(design['inputs']['independentReplay'])
    old, parameters, graph = deep.derive(design['inputs']['originalDeepDesign'])
    if not prior['ok'] or not replay['ok'] or replay['exitCode'] != 0 or replay['mathReport'] != design['inputs']['pureMath'] or d.read(design['inputs']['pureScope']) != old:
        raise ValueError('complete inherited pure math and independent replay')
    inherited_integrity(design['inputs']['pureMath'], prior, old)
    if design['cases'] != old['cases'] or design['fullCandidateCount'] != old['fullCandidateCount'] or design['inputs']['graph'] != old['model'] or design['newBranches'] != BRANCH_SPECS or design['inheritedBranches'] != deep.BRANCHES:
        raise ValueError('reconstruction_mismatch: exact original full74 cells')
    for key in ('deepTopology', 'lastTopology', 'storagePolicy', 'savedStages', 'requiredMaxAbs', 'requiredDecodedPixelDifferences', 'requiredPresenceDecisionDifferences', 'formalReleaseAllowed', 'fullModelLearnedGatePassed', 'productHold'):
        if design[key] != old[key]:
            raise ValueError('original graph/gates/storage/hold: ' + key)
    if not all(design[k] for k in ('originalReferenceAndFullDenominatorPreserved', 'sameOriginalWasmSkipAndPresenceForAllFourCells', 'inheritedAndNewMathBudgetsMustBeSeparate')):
        raise ValueError('original diagnostic boundaries')
    trace = d.read(d.read(design['inputs']['originalDeepDesign'])['inputs']['trace'])
    cases = []
    for case, row, observed in zip(old['cases'], prior['records'], trace['captures']['wasm'], strict=True):
        if case['ordinal'] != observed['ordinal'] or case['candidateIdentity'] != observed['candidateIdentity'] or case['fixedWasmPresence'] != observed['outputs']['presence']:
            raise ValueError('same original WASM final heads and identity')
        t.read_tensor(observed['outputs']['mask'])
        cases.append(case | {'inheritedPureBranches': row['branches'], 'originalWasmMask': observed['outputs']['mask']})
    p = old | {'purpose': 'complete_enc2_enc3_four_cell_fixed_wasm_skip_math_only', 'design': design_ref,
               'cases': cases, 'branches': BRANCHES, 'branchSpecs': BRANCH_SPECS, 'inheritedPureMath': design['inputs']['pureMath'],
               'newBranchCandidateCount': len(cases) * 2, 'inheritedBranchCandidateCount': len(cases) * 2, 'fourCellCandidateCount': len(cases) * 4}
    validate_contract(p)
    return p, parameters, graph


def mask_ref(branch):
    stages = branch['stages']
    if [s['stage'] for s in stages] != list(STAGES):
        raise ValueError('complete stages before final cell')
    return stages[-1]['savedRaw']


def four_cell_records(p, records):
    if len(records) != p['fullCandidateCount']:
        raise ValueError('full four-cell denominator before conclusions')
    rows = []
    for case, row in zip(p['cases'], records, strict=True):
        if row['ordinal'] != case['ordinal'] or row['candidateIdentity'] != case['candidateIdentity'] or [b['branch'] for b in row['branches']] != BRANCHES:
            raise ValueError('stable ordered four-cell identity')
        refs = [mask_ref(b) for b in case['inheritedPureBranches']] + [mask_ref(b) for b in row['branches']]
        refs += [case['originalStrictCudaHeads']['mask'], case['originalWasmMask']]
        rows.append({'ordinal': case['ordinal'], 'candidateIdentity': case['candidateIdentity'],
                     'decomposition': interaction(*(t.read_tensor(ref) for ref in refs))})
    return rows


def evaluate(case, p, parameters, graph, journal):
    h, w = case['candidateInput']['shape'][2:]
    half_shape, full_shape = (1, 32, h // 2, w // 2), (1, 16, h, w)
    choice, refs = source_selection(case, journal.branch)
    e2, e3 = (t.read_tensor(refs[key]) for key in ('enc2.5', 'enc3.5'))
    ratios = t.read_tensor(case['resizeRatios'])
    fixed = t.read_tensor(case['fixedWasmSkip'])
    run = journal.run
    a, desc = run('deepResize64', refs | {'ratios': case['resizeRatios']}, lambda: resize_propagated64(e3, e2, ratios, graph, p['deepTopology']), (1, 64, h // 2, w // 2), 'float64')
    a, desc = run('deepConcat64', {'resized': desc, 'originalSkip': refs['enc2.5']}, lambda: u.concat64(a, e2), (1, 96, h // 2, w // 2), 'float64')
    a, desc = run('deepConv1_64', {'input': desc}, lambda: m.decoder.conv64(a, parameters['deepConv0'], p['maximumOutputPixelsPerChunk']), half_shape, 'float64')
    for i, suffix in enumerate(('1', '4')):
        config = p['deepGroupNorms'][i]
        a, desc = run(f'deepGn{i+1}_64', {'input': desc}, lambda: t.gn64(a, parameters['deepGamma' + suffix], parameters['deepBeta' + suffix], config['groups'], config['epsilon']), half_shape, 'float64')
        a, desc = run(f'deepGelu{i+1}_64', {'input': desc}, lambda: t.gelu64(a, p['deepGelu']), half_shape, 'float64')
        if i == 0:
            a, desc = run('deepConv2_64', {'input': desc}, lambda: m.decoder.conv64(a, parameters['deepConv3'], p['maximumOutputPixelsPerChunk']), half_shape, 'float64')
    boundary_error = float(np.abs(a - t.read_tensor(case['features']['dec2.5']['wasm']).astype(np.float64)).max())
    a, desc = run('resize64', {'input': desc, 'fixedSkip': case['fixedWasmSkip'], 'ratios': case['resizeRatios']}, lambda: resize_propagated64(a, fixed, ratios, graph, p['lastTopology']), (1, 32, h, w), 'float64')
    a, desc = run('concat64', {'input': desc, 'fixedSkip': case['fixedWasmSkip']}, lambda: u.concat64(a, fixed), (1, 48, h, w), 'float64')
    a, desc = run('firstConv64', {'input': desc}, lambda: m.decoder.conv64(a, parameters['upstreamConvWeight'], p['maximumOutputPixelsPerChunk']), full_shape, 'float64')
    config = p['firstGroupNorm']
    a, desc = run('firstGn64', {'input': desc}, lambda: t.gn64(a, parameters['firstGamma'], parameters['firstBeta'], config['groups'], config['epsilon']), full_shape, 'float64')
    a, desc = run('firstGelu64', {'input': desc}, lambda: t.gelu64(a, p['gelu']), full_shape, 'float64')
    a, desc = run('conv64', {'input': desc}, lambda: m.decoder.conv64(a, parameters['convWeight'], p['maximumOutputPixelsPerChunk']), full_shape, 'float64')
    config = p['lastGroupNorm']
    a, desc = run('lastGn64', {'input': desc}, lambda: t.gn64(a, parameters['gamma'], parameters['beta'], config['groups'], config['epsilon']), full_shape, 'float64')
    a, desc = run('lastGelu64', {'input': desc}, lambda: t.gelu64(a, p['gelu']), full_shape, 'float64')
    a, desc = run('delta64', {'input': desc}, lambda: t.delta64(a, parameters['deltaWeight'], parameters['deltaBias'], p['maximumOutputPixelsPerChunk']), (1, 1, h, w), 'float64')
    delta_error = float(np.abs(a - t.read_tensor(case['originalCudaDelta']).astype(np.float64)).max())
    seed = t.seed32(t.read_tensor(case['candidateInput']))
    a, desc = run('finalMaskAdd64', {'input': desc, 'originalCandidate': case['candidateInput']}, lambda: t.final_mask64(seed, a), (1, 1, h, w), 'float64')
    a, _ = run('mask32', {'input': desc}, lambda: (a.astype(np.float32), {'singleFinalFloat32Rounding': True}), (1, 1, h, w), 'float32')
    references = {key: t.read_tensor(ref) for key, ref in case['originalStrictCudaHeads'].items()}
    parity = t.comparator.compare_outputs(references['mask'].reshape(-1), references['presence'].reshape(-1), a.reshape(-1), t.read_tensor(case['fixedWasmPresence']).reshape(-1), h, w)
    return {'branch': journal.branch, 'stages': journal.records, 'deepBoundaryAgainstOriginalWasmMaxAbsDiagnosticOnly': boundary_error, 'encoderOrigins': choice,
            'originalFeatureInputs': refs, 'fixedSkip': case['fixedWasmSkip'], 'fixedPresence': case['fixedWasmPresence'],
            'originalCudaParity': parity, 'counterfactualNumericPixelAndPresenceGatesPassed': all(parity[k] for k in ('numericGatePassed', 'decodedPixelGatePassed', 'presenceDecisionMatched', 'allReferenceAndCapturedHeadsFinite')),
            'delta64AgainstOriginalCudaMaxAbs': delta_error, 'actualFp32RepairProven': False}


def compute(execution, root, replay=False):
    e = d.read(d.bind(execution))
    if e['sources'] != sources() or e['runtime'] != t.runtime_binding() or e['outputRoot'] != str(root):
        raise ValueError('frozen source/runtime/exclusive output root')
    p = d.read(e['scope'])
    actual, parameters, graph = derive(p['design'])
    if p != actual:
        raise ValueError('reconstruction_mismatch: complete derived scope')
    if not replay:
        if shutil.disk_usage(root.parent).free < p['expectedRawBytes'] + 1024**3:
            raise ValueError('pre-registered raw bytes plus one GiB reserve')
        root.mkdir(exist_ok=False)
        (root / 'events').mkdir()
        (root / 'results').mkdir()
    records, journals = [], []
    try:
        for case in p['cases']:
            row = {'ordinal': case['ordinal'], 'candidateIdentity': case['candidateIdentity'], 'branches': []}
            for branch in BRANCHES:
                journal = StageJournal(root, d.bind(execution), case, branch, replay)
                journals.append(journal)
                row['branches'].append(evaluate(case, p, parameters, graph, journal))
            path = root / 'results' / f'{case["ordinal"]:03d}-record.json'
            if replay:
                if d.read(d.bind(path)) != row:
                    raise ValueError('reconstruction_mismatch: complete candidate record')
            else:
                d.new(path, row)
            records.append(row)
            print(json.dumps({'ordinal': case['ordinal'], 'completedStages': len(records) * 2 * len(STAGES), 'replay': replay}), flush=True)
        expected_names = sorted(f'{c["ordinal"]:03d}-{b}-{s}-{phase}.json' for c in p['cases'] for b in BRANCHES for s in STAGES for phase in ('start', 'done'))
        actual_events = sorted(path.name for path in (root / 'events').iterdir())
        files = sorted((root / 'results').glob('*.bin'))
        if expected_names != actual_events or len(files) != p['expectedRawCount'] or sum(path.stat().st_size for path in files) != p['expectedRawBytes']:
            raise ValueError('complete independent stage events and saved boundary denominator')
        report = {'ok': True, 'decision': 'complete_enc2_enc3_four_cell_math_diagnostic_only', 'inputs': {'execution': d.bind(execution)},
                  'records': records, 'summary': t.summarize(p, records), 'candidateCount': len(records),
                  'inheritedPureSummary': d.read(p['inheritedPureMath'])['summary'], 'fourCellInteraction': four_cell_records(p, records),
                  'newBranchCandidateCount': len(records) * 2, 'inheritedBranchCandidateCount': len(records) * 2, 'fourCellCandidateCount': len(records) * 4,
                  'analyticalEvaluationsConsumed': p['analyticalEvaluationsAllowed'], 'singleFinalFloat32Conversions': p['singleFinalFloat32Conversions'],
                  'stageByteHashes': len(records) * 2 * len(STAGES), 'startEventCount': len(expected_names) // 2, 'doneEventCount': len(expected_names) // 2,
                  'eventManifestSha256': hashlib.sha256(d.raw([d.bind(root / 'events' / name) for name in expected_names])).hexdigest(),
                  'actualRawCount': len(files), 'actualRawBytes': sum(path.stat().st_size for path in files), 'storagePolicy': POLICY,
                  'allOriginalFinalHeadByteFidelityPreserved': True, 'fixedWasmSkipAndPresenceNotWholeNetworkRepair': True,
                  'actualFp32RepairOrWholeModelUnreachableProven': False, 'newModelCalls': 0, 'optimizerSteps': 0, 'valInputs': 0, 'protectedInputs': 0, 'newChatImageInputs': 0,
                  'oldFailuresAndConsumedBudgetsPreserved': True, 'fullModelLearnedGatePassed': False, 'formalReleaseAllowed': False, 'productHold': True}
        if replay:
            if report != d.read(d.bind(root / 'report.json')):
                raise ValueError('reconstruction_mismatch: entire report')
        else:
            d.new(root / 'report.json', report)
        print(json.dumps({'ok': True, 'summary': report['summary'], 'actualRawBytes': report['actualRawBytes'], 'replay': replay}), flush=True)
    except BaseException as err:
        if not replay:
            d.new(root / 'execution-failure.json', {'ok': False, 'decision': 'reconstruction_mismatch', 'execution': d.bind(execution), 'error': str(err), 'completeCandidateRecords': len(records), 'completedStages': sum(len(j.records) for j in journals), 'startedEvents': len(list((root / 'events').glob('*-start.json'))), 'newModelCalls': 0, 'productHold': True})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--execution', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--verify-report', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    execution_path = d.checked(d.read(d.bind(output / 'report.json'))['inputs']['execution']) if args.verify_report else args.execution.resolve()
    compute(execution_path, output, args.verify_report)
