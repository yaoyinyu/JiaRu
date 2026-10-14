"""enc3首GN至最终mask的完整高精度条件诊断，不替代实际部署。"""
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
spec = importlib.util.spec_from_file_location('enc3_encoder_cross', HERE / 'analyze-reviewed-encoder-cross-counterfactual.py')
cross = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cross)
deep, u, m, t, d = cross.deep, cross.u, cross.m, cross.t, cross.d
PREFIX = ('enc3FirstGn64', 'enc3FirstGelu64', 'enc3SecondConv64', 'enc3LastGn64', 'enc3LastGelu64')
STAGES = (*PREFIX, *deep.STAGES)
SAVED = ('enc3LastGelu64', 'mask32')
POLICY = 'all_stage_full_bytes_sha256_exclusive_start_done_recompute_all_save_only_enc3_boundary_f64_and_final_mask_f32'
BRANCHES = ['cuda_enc3_first_conv_fixed_wasm_skips', 'wasm_enc3_first_conv_fixed_wasm_skips']
descriptor, resize_propagated64 = deep.descriptor, deep.resize_propagated64


def sources():
    return cross.sources() | {Path(__file__).name: d.bind(__file__)}


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
    if e['sources'] != cross.sources() or e['runtime'] != t.runtime_binding() or d.read(e['scope']) != p or e['outputRoot'] != str(root):
        raise ValueError('frozen prior cross sources/runtime/scope')
    events = []
    for case, row in zip(p['cases'], prior['records'], strict=True):
        if case['ordinal'] != row['ordinal'] or case['candidateIdentity'] != row['candidateIdentity'] or [b['branch'] for b in row['branches']] != cross.BRANCHES:
            raise ValueError('all inherited cross identities and branches')
        if d.read(d.bind(root / 'results' / f'{case["ordinal"]:03d}-record.json')) != row:
            raise ValueError('inherited entire cross record')
        for branch in row['branches']:
            if [s['stage'] for s in branch['stages']] != list(deep.STAGES):
                raise ValueError('inherited cross stage denominator')
            for stage in branch['stages']:
                stem = f'{case["ordinal"]:03d}-{branch["branch"]}-{stage["stage"]}'
                start, done = root / 'events' / (stem + '-start.json'), root / 'events' / (stem + '-done.json')
                expected = {'execution': prior['inputs']['execution'], 'ordinal': case['ordinal'], 'candidateIdentity': case['candidateIdentity'],
                            'branch': branch['branch'], 'stage': stage['stage'], 'inputs': stage['inputs']}
                if d.read(d.bind(start)) != expected or d.read(d.bind(done)) != stage:
                    raise ValueError('inherited exact stage input chain')
                if ('savedRaw' in stage) != (stage['stage'] in deep.SAVED):
                    raise ValueError('inherited saved-stage policy')
                if 'savedRaw' in stage and descriptor(t.read_tensor(stage['savedRaw'])) != stage['output']:
                    raise ValueError('inherited complete saved array bytes')
                events.extend((start, done))
    if sorted(events) != sorted((root / 'events').iterdir()) or hashlib.sha256(d.raw([d.bind(path) for path in sorted(events)])).hexdigest() != prior['eventManifestSha256']:
        raise ValueError('inherited complete cross event manifest')
    if t.summarize(p, prior['records']) != prior['summary']:
        raise ValueError('inherited cross full final-gate summary')


def derive(design_ref):
    design = d.read(design_ref)
    if design['purpose'] != 'complete74_enc3_first_gn_to_final_head_math_sufficiency_design_only' or any(design[k] for k in ('analyticalBudgetAllocatedNow', 'newProjectModelInputsAllowedNow', 'newSyntheticModelInputsAllowedNow')):
        raise ValueError('original unallocated enc3 chain design')
    for ref in design['inputs'].values(): d.checked(ref)
    prior = d.read(design['inputs']['encoderCrossMath']); replay = d.read(design['inputs']['independentReplay'])
    saved = d.read(design['inputs']['currentScope'])
    old, parameters, graph = cross.derive(saved['design'])
    if old != saved or not prior['ok'] or not replay['ok'] or replay['exitCode'] != 0 or replay['mathReport'] != design['inputs']['encoderCrossMath']:
        raise ValueError('complete original cross and independent replay')
    verify_prior(design['inputs']['encoderCrossMath'], prior, old)
    if prior['summary'][cross.BRANCHES[0]]['failedOrdinals'] or prior['summary'][cross.BRANCHES[1]]['failedOrdinals'] != [41, 74]:
        raise ValueError('preserve actual localization and old failures')
    original = d.read(d.read(old['design'])['inputs']['originalDeepDesign'])
    if original['inputs']['parentScope'] != design['inputs']['parentScope'] or original['inputs']['trace'] != design['inputs']['trace'] or old['model'] != design['inputs']['graph']:
        raise ValueError('same original graph observation and strict CUDA reference')
    parent, trace = d.read(design['inputs']['parentScope']), d.read(design['inputs']['trace'])
    index = [row['module'] for row in parent['mapping']].index('enc3.0')
    cases = []
    keys = ('ordinal', 'candidateIdentity', 'candidateInput', 'resizeRatios', 'originalStrictCudaHeads', 'fixedWasmSkip', 'fixedWasmPresence', 'features', 'originalCudaDelta')
    for c, oc, pc, wc in zip(design['cases'], old['cases'], parent['cases'], trace['captures']['wasm'], strict=True):
        expected = {k: oc[k] for k in keys} | {'originalEnc3FirstConv': {'cuda': pc['strictCudaLayers']['enc3.0'], 'wasm': wc['outputs'][f'layer{index:02d}']}, 'fixedWasmEnc2': oc['features']['enc2.5']['wasm']}
        if c != expected or c['candidateIdentity'] != pc['candidateIdentity'] or c['candidateIdentity'] != wc['candidateIdentity'] or c['ordinal'] != pc['ordinal'] or c['ordinal'] != wc['ordinal']:
            raise ValueError('reconstruction_mismatch: original complete enc3 cut and fixed skips')
        h, w = c['candidateInput']['shape'][2:]
        for ref in c['originalEnc3FirstConv'].values():
            a = t.read_tensor(ref)
            if a.dtype != np.float32 or a.shape != (1, 64, h // 4, w // 4):
                raise ValueError('original enc3 first convolution F32 native domain')
        cases.append(c)
    extra, configs = encoder_parameters(graph); parameters.update(extra)
    for key in ('originalGraphEncoderParameterAndConstantBitsMustBeDerivedBeforeBudget', 'fixedWasmEnc2Enc1AndPresenceNotWholeModelRepair', 'sameOriginalStrictCudaReferenceAndFullDenominator', 'featuresFloat64PropagatedNoIntermediateFloat32Rounding', 'originalFloat32HostCoordinateArithmeticPreserved', 'stageByteHashesAndExclusiveStartDoneRecomputeAllRequired'):
        if design[key] is not True: raise ValueError('enc3 diagnostic invariant: ' + key)
    if design['fullCandidateCount'] != len(cases) or design['branches'] != BRANCHES or design['orderedNewEncoderStages'] != list(PREFIX) or design['orderedDownstreamStages'] != list(deep.STAGES) or design['savedStages'] != list(SAVED):
        raise ValueError('original complete scope and stage design')
    for key in ('requiredMaxAbs', 'requiredDecodedPixelDifferences', 'requiredPresenceDecisionDifferences', 'formalReleaseAllowed', 'fullModelLearnedGatePassed', 'productHold'):
        if design[key] != old[key]: raise ValueError('unchanged original gates: ' + key)
    count = len(cases)
    p = old | configs | {'design': design_ref, 'purpose': 'complete_enc3_first_gn_to_final_head_math_sufficiency_only', 'cases': cases,
                         'branches': BRANCHES, 'orderedStages': list(STAGES), 'savedStages': list(SAVED), 'storagePolicy': POLICY,
                         'fullCandidateCount': count, 'analyticalEvaluationsAllowed': {stage: count * 2 for stage in STAGES[:-1]} | {'total': count * 2 * (len(STAGES) - 1)},
                         'expectedRawBytes': sum(2 * (64 * (c['candidateInput']['shape'][2] // 4) * (c['candidateInput']['shape'][3] // 4) * 8 + c['candidateInput']['shape'][2] * c['candidateInput']['shape'][3] * 4) for c in cases)}
    for key in ('branchSpecs', 'newBranchCandidateCount', 'inheritedBranchCandidateCount', 'fourCellCandidateCount', 'inheritedPureMath'):
        del p[key]
    validate_contract(p)
    if (p['analyticalEvaluationsAllowed']['total'], p['singleFinalFloat32Conversions'], p['expectedRawCount'], p['expectedRawBytes']) != tuple(design[key] for key in ('plannedNewMathStagesNotAllocated', 'plannedFinalFloat32ConversionsNotAllocated', 'plannedSavedRawCountNotAllocated', 'plannedSavedRawBytesNotAllocated')):
        raise ValueError('derived budget equals pre-registered design')
    return p, parameters, graph


def encoder_parameters(graph):
    nodes = {n.name: n for n in graph.graph.node}
    outputs = {o: n for n in graph.graph.node for o in n.output}
    initializers = {i.name: i for i in graph.graph.initializer}
    parameters, bindings, configs, gelus = {}, {}, [], []

    def parameter(key, name, shape):
        proto = initializers[name]
        value = numpy_helper.to_array(proto)
        if value.dtype != np.float32 or value.shape != shape or not np.isfinite(value).all():
            raise ValueError('original deep parameter shape/domain')
        parameters[key] = value
        bindings[key] = {'initializerName': name, **descriptor(value), 'tensorProtoSha256': hashlib.sha256(proto.SerializeToString()).hexdigest()}
        return value

    for suffix, channels in [('3', 64)]:
        conv = nodes[f'/enc3/enc3.{suffix}/Conv']
        attrs = {a.name: onnx.helper.get_attribute_value(a) for a in conv.attribute}
        if conv.op_type != 'Conv' or len(conv.input) != 2 or attrs != {'dilations': [1, 1], 'group': 1, 'kernel_shape': [3, 3], 'pads': [1, 1, 1, 1], 'strides': [1, 1]}:
            raise ValueError('actual original deep convolution without bias')
        parameter('encoderConv' + suffix, conv.input[1], (64, channels, 3, 3))
    for suffix in ('1', '4'):
        prefix = f'/enc3/enc3.{suffix}/'
        add = outputs[prefix + 'Add_output_0']
        mul = outputs[add.input[0]]
        div = outputs[prefix + 'InstanceNormalization_output_0']
        sqrt = outputs[div.input[1]]
        eps_add = outputs[sqrt.input[0]]
        reshape = nodes[prefix + 'Reshape']
        groups = numpy_helper.to_array(outputs[reshape.input[1]].attribute[0].t).tolist()
        if [add.op_type, mul.op_type, div.op_type, sqrt.op_type, eps_add.op_type] != ['Add', 'Mul', 'Div', 'Sqrt', 'Add'] or groups != [0, 4, -1]:
            raise ValueError('actual original deep four-group centered normalization')
        parameter('encoderGamma' + suffix, mul.input[1], (64, 1, 1))
        parameter('encoderBeta' + suffix, add.input[1], (64, 1, 1))
        eps = numpy_helper.to_array(initializers[eps_add.input[1]])
        parameter('encoderEpsilon' + suffix, eps_add.input[1], eps.shape)
        if eps.size != 1 or not float(eps.reshape(-1)[0]) > 0:
            raise ValueError('original positive scalar epsilon')
        configs.append({'groups': 4, 'channels': 64, 'epsilon': float(eps.reshape(-1)[0])})
    for suffix in ('2', '5'):
        values = []
        for constant in ('Constant', 'Constant_1', 'Constant_2'):
            a = numpy_helper.to_array(nodes[f'/enc3/enc3.{suffix}/{constant}'].attribute[0].t)
            if a.dtype != np.float32 or a.size != 1:
                raise ValueError('original deep GELU constant bits')
            values.append(float(a.reshape(-1)[0]))
        gelus.append(dict(zip(('sqrt2FromOriginalFloat32', 'oneFromOriginalFloat32', 'halfFromOriginalFloat32'), values, strict=True)))
    if gelus[0] != gelus[1]:
        raise ValueError('different original deep GELU constant bits')
    return parameters, {'encoderParameterBindings': bindings, 'encoderGroupNorms': configs, 'encoderGelu': gelus[0]}


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
        raise ValueError('explicit original first-convolution origin')
    origin = 'cuda' if journal.branch == BRANCHES[0] else 'wasm'
    refs = {'enc3.0': case['originalEnc3FirstConv'][origin], 'enc2.5': case['fixedWasmEnc2']}
    e2 = t.read_tensor(refs['enc2.5'])
    e3 = t.read_tensor(refs['enc3.0']).astype(np.float64)
    ratios = t.read_tensor(case['resizeRatios'])
    fixed = t.read_tensor(case['fixedWasmSkip'])
    run = journal.run
    small_shape = (1, 64, h // 4, w // 4)
    config = p['encoderGroupNorms'][0]
    a, desc = run('enc3FirstGn64', {'originalFirstConv': refs['enc3.0']}, lambda: t.gn64(e3, parameters['encoderGamma1'], parameters['encoderBeta1'], config['groups'], config['epsilon']), small_shape, 'float64')
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
            'encoderBoundaryAgainstSameOriginMaxAbs': encoder_error, 'originalEnc3FirstConv': refs['enc3.0'],
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
        report = {'ok': True, 'decision': 'complete_enc3_first_gn_to_final_math_diagnostic_only', 'inputs': {'execution': d.bind(execution)},
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
