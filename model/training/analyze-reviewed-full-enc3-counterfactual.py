"""从原enc2特征经真实池化/首卷积的完整enc3数学充分性诊断。"""
import argparse
import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

import numpy as np
import onnx
from onnx import numpy_helper

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('full_enc3_chain', HERE / 'analyze-reviewed-enc3-chain-counterfactual.py')
chain = importlib.util.module_from_spec(spec); spec.loader.exec_module(chain)
deep, u, m, t, d = chain.deep, chain.u, chain.m, chain.t, chain.d
NEW_STAGES = ('enc3AveragePool64', 'enc3FirstConv64')
STAGES = (*NEW_STAGES, *chain.STAGES)
SAVED, POLICY = chain.SAVED, chain.POLICY
BRANCHES = ['cuda_enc2_full_enc3_fixed_wasm_skips', 'wasm_enc2_full_enc3_fixed_wasm_skips']
descriptor, resize_propagated64 = chain.descriptor, chain.resize_propagated64


def sources():
    return chain.sources() | {Path(__file__).name: d.bind(__file__)}


def average_pool64(x):
    if x.dtype != np.float32 or x.ndim != 4 or x.shape[0] != 1 or x.shape[1] < 1 or min(x.shape[2:]) < 2 or not np.isfinite(x).all():
        raise ValueError('original finite native F32 pool input')
    height, width = x.shape[2] // 2, x.shape[3] // 2
    a = x[:, :, :height * 2, :width * 2].astype(np.float64)
    result = ((a[:, :, 0::2, 0::2] + a[:, :, 0::2, 1::2]) + a[:, :, 1::2, 0::2]) + a[:, :, 1::2, 1::2]
    result *= .25
    descriptor(result)
    return result, {'originalPoolSemantics': {'kernel': [2, 2], 'strides': [2, 2], 'pads': [0, 0, 0, 0], 'ceilMode': 0, 'countIncludePad': 1},
                    'inputStorageDomain': 'float32', 'featureArithmeticDomain': 'float64',
                    'sumOrder': 'top_left_plus_top_right_then_bottom_left_then_bottom_right_divide_four',
                    'actualPoolCaptureClaimed': False}


def pool_and_first_conv(graph, mapping):
    outputs = {o: n for n in graph.graph.node for o in n.output}
    initializers = {i.name: i for i in graph.graph.initializer}
    conv = outputs[mapping['enc3.0']['tensor']]; pool = outputs[conv.input[0]]
    attrs = {v.name: onnx.helper.get_attribute_value(v) for v in pool.attribute}
    cattrs = {v.name: onnx.helper.get_attribute_value(v) for v in conv.attribute}
    if pool.op_type != 'AveragePool' or list(pool.input) != [mapping['enc2.5']['tensor']] or attrs != {'ceil_mode': 0, 'count_include_pad': 1, 'kernel_shape': [2, 2], 'pads': [0, 0, 0, 0], 'strides': [2, 2]}:
        raise ValueError('original full enc3 2x2 stride2 no-pad floor pooling')
    if conv.op_type != 'Conv' or len(conv.input) != 2 or cattrs != {'dilations': [1, 1], 'group': 1, 'kernel_shape': [3, 3], 'pads': [1, 1, 1, 1], 'strides': [1, 1]}:
        raise ValueError('original first enc3 32-to-64 convolution without bias')
    proto = initializers[conv.input[1]]; weight = numpy_helper.to_array(proto)
    if weight.dtype != np.float32 or weight.shape != (64, 32, 3, 3) or not np.isfinite(weight).all():
        raise ValueError('original enc3 first weight bits/domain')
    topology = {'originalPoolNode': {'name': pool.name, 'opType': pool.op_type, 'inputs': list(pool.input), 'outputs': list(pool.output), 'attributes': attrs, 'nodeProtoSha256': hashlib.sha256(pool.SerializeToString()).hexdigest()},
                'originalFirstConvNode': {'name': conv.name, 'inputs': list(conv.input), 'outputs': list(conv.output), 'attributes': cattrs, 'nodeProtoSha256': hashlib.sha256(conv.SerializeToString()).hexdigest()},
                'firstEncoderConvBinding': {'initializerName': conv.input[1], **descriptor(weight), 'tensorProtoSha256': hashlib.sha256(proto.SerializeToString()).hexdigest()}}
    return weight, topology


def derive(design_ref):
    design = d.read(design_ref)
    if design['purpose'] != 'complete74_full_enc3_from_enc2_pool_and_first_conv_math_sufficiency_design_only' or any(design[k] for k in ('analyticalBudgetAllocatedNow', 'newProjectModelInputsAllowedNow', 'newSyntheticModelInputsAllowedNow')):
        raise ValueError('original unallocated full enc3 design')
    for ref in design['inputs'].values(): d.checked(ref)
    prior = d.read(design['inputs']['enc3ChainMath']); replay = d.read(design['inputs']['independentReplay'])
    saved = d.read(design['inputs']['currentScope']); old, parameters, graph = chain.derive(saved['design'])
    if old != saved or not prior['ok'] or not replay['ok'] or replay['exitCode'] != 0 or replay['mathReport'] != design['inputs']['enc3ChainMath']:
        raise ValueError('complete inherited enc3 chain and independent replay')
    verify_prior(design['inputs']['enc3ChainMath'], prior, old)
    if prior['summary'][chain.BRANCHES[0]]['failedOrdinals'] or prior['summary'][chain.BRANCHES[1]]['failedOrdinals'] != [40, 41, 74]:
        raise ValueError('preserved full original insufficiency')
    original = d.read(old['design'])
    if any(design['inputs'][k] != original['inputs'][k] for k in ('parentScope', 'trace', 'graph')):
        raise ValueError('original graph/observation/reference')
    parent = d.read(design['inputs']['parentScope']); mapping = {row['module']: row for row in parent['mapping']}
    weight, topology = pool_and_first_conv(graph, mapping); parameters['firstEncoderConv'] = weight
    for key in ('originalPoolNode', 'originalFirstConvNode'):
        if design[key] != topology[key]: raise ValueError('frozen semantic node: ' + key)
    cases = []
    for c, oc in zip(design['cases'], old['cases'], strict=True):
        if c != oc | {'enc3PoolInput': oc['features']['enc2.5']}:
            raise ValueError('reconstruction_mismatch: complete original pool input and fixed skip identities')
        height, width = c['candidateInput']['shape'][2:]
        for ref in c['enc3PoolInput'].values():
            a = t.read_tensor(ref)
            if a.dtype != np.float32 or a.shape != (1, 32, height // 2, width // 2):
                raise ValueError('complete original F32 enc2 feature domain')
        cases.append(c)
    for key in ('originalFirstConvParameterBitsMustBeDerivedBeforeBudget', 'poolFloat64ReferenceNotActualCapturedFloat32Output', 'featuresFloat64PropagatedNoIntermediateFloat32Rounding', 'fixedWasmSkipsAndPresenceAreConditionalNotWholeNetworkRepair', 'originalFloat32HostCoordinatesAndConstantsPreserved', 'stageByteHashesAndExclusiveStartDoneRecomputeAllRequired'):
        if design[key] is not True: raise ValueError('full enc3 mathematical invariant: ' + key)
    if design['fullCandidateCount'] != len(cases) or design['branches'] != BRANCHES or design['orderedNewStages'] != list(NEW_STAGES) or design['orderedDownstreamStages'] != list(chain.STAGES) or design['savedStages'] != list(SAVED):
        raise ValueError('original full scope stage design')
    for key in ('requiredMaxAbs', 'requiredDecodedPixelDifferences', 'requiredPresenceDecisionDifferences', 'actualFp32RepairOrWholeModelUnreachableProven', 'fullModelLearnedGatePassed', 'formalReleaseAllowed', 'productHold'):
        if design[key] != old[key]: raise ValueError('original gates and hold: ' + key)
    p = old | topology | {'design': design_ref, 'purpose': 'complete_full_enc3_from_enc2_math_sufficiency_only', 'cases': cases,
                         'branches': BRANCHES, 'orderedStages': list(STAGES),
                         'analyticalEvaluationsAllowed': {stage: len(cases) * 2 for stage in STAGES[:-1]} | {'total': len(cases) * 2 * (len(STAGES) - 1)}}
    validate_contract(p)
    if (p['analyticalEvaluationsAllowed']['total'], p['singleFinalFloat32Conversions'], p['expectedRawCount'], p['expectedRawBytes']) != tuple(design[key] for key in ('plannedNewMathStagesNotAllocated', 'plannedFinalFloat32ConversionsNotAllocated', 'plannedSavedRawCountNotAllocated', 'plannedSavedRawBytesNotAllocated')):
        raise ValueError('derived full enc3 budget equals original design')
    return p, parameters, graph


def validate_contract(p):
    count = len(p['cases'])
    if count <= 0 or p['fullCandidateCount'] != count or p['branches'] != BRANCHES or p['orderedStages'] != list(STAGES):
        raise ValueError('complete native two-origin enc3 chain denominator')
    if [c['ordinal'] for c in p['cases']] != list(range(1, count + 1)) or any(c['candidateIdentity']['identity']['split'] != 'train' for c in p['cases']):
        raise ValueError('complete ordered train identities')
    expected = {stage: 2 * count for stage in STAGES[:-1]} | {'total': 2 * count * (len(STAGES) - 1)}
    size = sum(2 * (64 * (c['candidateInput']['shape'][2] // 4) * (c['candidateInput']['shape'][3] // 4) * 8 +
                    c['candidateInput']['shape'][2] * c['candidateInput']['shape'][3] * 4) for c in p['cases'])
    if p['analyticalEvaluationsAllowed'] != expected or p['singleFinalFloat32Conversions'] != 2 * count or p['expectedRawCount'] != 4 * count or p['expectedRawBytes'] != size:
        raise ValueError('new enc3 math/rounding/saved RAW budgets')
    if p['storagePolicy'] != POLICY or p['savedStages'] != list(SAVED):
        raise ValueError('only enc3 boundary and final RAW, all stages recomputed')
    if p['requiredMaxAbs'] != 1e-4 or p['requiredDecodedPixelDifferences'] != 0 or p['requiredPresenceDecisionDifferences'] != 0:
        raise ValueError('original final head gates unchanged')
    if any(p[k] for k in ('newProjectModelInputsAllowed', 'newSyntheticModelInputsAllowed', 'optimizerStepsAllowed', 'valInputsAllowed', 'protectedInputsAllowed', 'newChatImageInputsAllowed', 'actualFp32RepairOrWholeModelUnreachableProven', 'fullModelLearnedGatePassed', 'formalReleaseAllowed')) or not p['productHold']:
        raise ValueError('zero neural budget and conditional math diagnosis only')


def verify_prior(ref, prior, p):
    e = d.read(prior['inputs']['execution']); root = Path(ref['path']).parent
    if e['sources'] != chain.sources() or e['runtime'] != t.runtime_binding() or d.read(e['scope']) != p or e['outputRoot'] != str(root):
        raise ValueError('frozen prior cross sources/runtime/scope')
    events = []
    for case, row in zip(p['cases'], prior['records'], strict=True):
        if case['ordinal'] != row['ordinal'] or case['candidateIdentity'] != row['candidateIdentity'] or [b['branch'] for b in row['branches']] != chain.BRANCHES:
            raise ValueError('all inherited cross identities and branches')
        if d.read(d.bind(root / 'results' / f'{case["ordinal"]:03d}-record.json')) != row:
            raise ValueError('inherited entire cross record')
        for branch in row['branches']:
            if [s['stage'] for s in branch['stages']] != list(chain.STAGES):
                raise ValueError('inherited cross stage denominator')
            for stage in branch['stages']:
                stem = f'{case["ordinal"]:03d}-{branch["branch"]}-{stage["stage"]}'
                start, done = root / 'events' / (stem + '-start.json'), root / 'events' / (stem + '-done.json')
                expected = {'execution': prior['inputs']['execution'], 'ordinal': case['ordinal'], 'candidateIdentity': case['candidateIdentity'],
                            'branch': branch['branch'], 'stage': stage['stage'], 'inputs': stage['inputs']}
                if d.read(d.bind(start)) != expected or d.read(d.bind(done)) != stage:
                    raise ValueError('inherited exact stage input chain')
                if ('savedRaw' in stage) != (stage['stage'] in chain.SAVED):
                    raise ValueError('inherited saved-stage policy')
                if 'savedRaw' in stage and descriptor(t.read_tensor(stage['savedRaw'])) != stage['output']:
                    raise ValueError('inherited complete saved array bytes')
                events.extend((start, done))
    if sorted(events) != sorted((root / 'events').iterdir()) or hashlib.sha256(d.raw([d.bind(path) for path in sorted(events)])).hexdigest() != prior['eventManifestSha256']:
        raise ValueError('inherited complete cross event manifest')
    if t.summarize(p, prior['records']) != prior['summary']:
        raise ValueError('inherited cross full final-gate summary')


class StageJournal:
    """不可覆盖开始/完成事件；每次重放重新计算全数组，不凭汇总继承。"""
    def __init__(self, root, execution_ref, case, branch, replay=False):
        self.root, self.execution_ref, self.case, self.branch, self.replay = root, execution_ref, case, branch, replay
        self.records = []

    def run(self, stage, inputs, function, shape, dtype):
        if len(self.records) >= len(STAGES) or stage != STAGES[len(self.records)]:
            raise ValueError('ordered complete analytical chain')
        stem = f'{self.case["ordinal"]:03d}-{self.branch}-{stage}'
        start = {'execution': self.execution_ref, 'ordinal': self.case['ordinal'], 'candidateIdentity': self.case['candidateIdentity'], 'branch': self.branch, 'stage': stage, 'inputs': inputs}
        event = self.root / 'events' / (stem + '-start.json')
        if self.replay:
            if d.read(d.bind(event)) != start:
                raise ValueError('reconstruction_mismatch: original analytical start event')
        else:
            d.new(event, start)
        array, stats = function()
        desc = descriptor(array)
        if desc['shape'] != list(shape) or desc['dtype'] != dtype:
            raise ValueError('reconstruction_mismatch: stage native shape/domain')
        result = {'stage': stage, 'inputs': inputs, 'output': desc, 'statistics': stats}
        if stage in SAVED:
            path = self.root / 'results' / (stem + '.bin')
            if self.replay:
                ref = d.bind(path) | {'shape': list(array.shape), 'dtype': str(array.dtype)}
                m.same_bytes(t.read_tensor(ref), array)
            else:
                ref = t.save(path, array)
            result['savedRaw'] = ref
        done = self.root / 'events' / (stem + '-done.json')
        if self.replay:
            if d.read(d.bind(done)) != result:
                raise ValueError('reconstruction_mismatch: full stage bytes/statistics/input chain')
        else:
            d.new(done, result)
        self.records.append(result)
        return array, desc


def evaluate(case, p, parameters, graph, journal):
    h, w = case['candidateInput']['shape'][2:]
    half_shape, full_shape = (1, 32, h // 2, w // 2), (1, 16, h, w)
    if journal.branch not in BRANCHES:
        raise ValueError('explicit original enc2 pool input origin')
    origin = 'cuda' if journal.branch == BRANCHES[0] else 'wasm'
    refs = {'enc3PoolInput': case['enc3PoolInput'][origin], 'enc2.5': case['fixedWasmEnc2']}
    e2 = t.read_tensor(refs['enc2.5'])
    pool_input = t.read_tensor(refs['enc3PoolInput'])
    ratios = t.read_tensor(case['resizeRatios'])
    fixed = t.read_tensor(case['fixedWasmSkip'])
    run = journal.run
    pool_shape = (1, 32, h // 4, w // 4)
    encoder_shape = (1, 64, h // 4, w // 4)
    a, desc = run('enc3AveragePool64', {'originalPoolInput': refs['enc3PoolInput']}, lambda: average_pool64(pool_input), pool_shape, 'float64')
    a, desc = run('enc3FirstConv64', {'input': desc}, lambda: m.decoder.conv64(a, parameters['firstEncoderConv'], p['maximumOutputPixelsPerChunk']), encoder_shape, 'float64')
    first_conv_error = float(np.abs(a - t.read_tensor(case['originalEnc3FirstConv'][origin]).astype(np.float64)).max())
    e3 = a
    small_shape = (1, 64, h // 4, w // 4)
    config = p['encoderGroupNorms'][0]
    a, desc = run('enc3FirstGn64', {'computedFirstConv64': desc}, lambda: t.gn64(e3, parameters['encoderGamma1'], parameters['encoderBeta1'], config['groups'], config['epsilon']), small_shape, 'float64')
    a, desc = run('enc3FirstGelu64', {'input': desc}, lambda: t.gelu64(a, p['encoderGelu']), small_shape, 'float64')
    a, desc = run('enc3SecondConv64', {'input': desc}, lambda: m.decoder.conv64(a, parameters['encoderConv3'], p['maximumOutputPixelsPerChunk']), small_shape, 'float64')
    config = p['encoderGroupNorms'][1]
    a, desc = run('enc3LastGn64', {'input': desc}, lambda: t.gn64(a, parameters['encoderGamma4'], parameters['encoderBeta4'], config['groups'], config['epsilon']), small_shape, 'float64')
    a, desc = run('enc3LastGelu64', {'input': desc}, lambda: t.gelu64(a, p['encoderGelu']), small_shape, 'float64')
    encoder_error = float(np.abs(a - t.read_tensor(case['features']['enc3.5'][origin]).astype(np.float64)).max())
    e3 = a
    a, desc = run('deepResize64', {'enc3Feature64': desc, 'fixedEnc2': case['fixedWasmEnc2'], 'ratios': case['resizeRatios']}, lambda: resize_propagated64(e3, e2, ratios, graph, p['deepTopology']), (1, 64, h // 2, w // 2), 'float64')
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
    return {'branch': journal.branch, 'stages': journal.records, 'deepBoundaryAgainstOriginalWasmMaxAbsDiagnosticOnly': boundary_error,
            'encoderBoundaryAgainstSameOriginMaxAbs': encoder_error, 'originalEnc3FirstConv': case['originalEnc3FirstConv'][origin],
            'originalPoolInput': refs['enc3PoolInput'], 'firstConv64AgainstSameOriginMaxAbs': first_conv_error,
            'fixedWasmEnc2': case['fixedWasmEnc2'], 'fixedWasmEnc1': case['fixedWasmSkip'], 'fixedWasmPresence': case['fixedWasmPresence'],
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
        report = {'ok': True, 'decision': 'complete_full_enc3_from_enc2_math_diagnostic_only', 'inputs': {'execution': d.bind(execution)},
                  'records': records, 'summary': t.summarize(p, records), 'candidateCount': len(records),
                  'analyticalEvaluationsConsumed': p['analyticalEvaluationsAllowed'], 'singleFinalFloat32Conversions': p['singleFinalFloat32Conversions'],
                  'stageByteHashes': len(records) * 2 * len(STAGES), 'startEventCount': len(expected_names) // 2, 'doneEventCount': len(expected_names) // 2,
                  'eventManifestSha256': hashlib.sha256(d.raw([d.bind(root / 'events' / name) for name in expected_names])).hexdigest(),
                  'actualRawCount': len(files), 'actualRawBytes': sum(path.stat().st_size for path in files), 'storagePolicy': POLICY,
                  'allOriginalFinalHeadByteFidelityPreserved': True, 'fixedWasmEnc2Enc1AndPresenceNotWholeNetworkRepair': True,
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
