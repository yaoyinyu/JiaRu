"""完整深层解码数学诊断；阶段字节哈希可重算，仅持久化边界与最终RAW。"""
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
spec = importlib.util.spec_from_file_location('deep_decoder_upstream', HERE / 'analyze-reviewed-upstream-counterfactual.py')
u = importlib.util.module_from_spec(spec)
spec.loader.exec_module(u)
m, t, d = u.m, u.t, u.d
BRANCHES = ['cuda_encoder_features_fixed_wasm_skip', 'wasm_encoder_features_fixed_wasm_skip']
DEEP_STAGES = ('deepResize64', 'deepConcat64', 'deepConv1_64', 'deepGn1_64', 'deepGelu1_64',
               'deepConv2_64', 'deepGn2_64', 'deepGelu2_64')
STAGES = (*DEEP_STAGES, *u.STAGES, 'mask32')
SAVED = ('deepGelu2_64', 'mask32')
POLICY = 'all_stage_full_bytes_sha256_and_exclusive_start_done_events_recompute_all_save_only_deep_boundary_f64_and_final_mask_f32'


def descriptor(a):
    if a.dtype not in (np.dtype('float32'), np.dtype('float64')) or not np.isfinite(a).all() or not a.size:
        raise ValueError('finite nonempty explicit F32/F64 storage domain')
    return {'dtype': str(a.dtype), 'shape': list(a.shape), 'byteCount': a.nbytes,
            'bytesSha256': hashlib.sha256(a.tobytes(order='C')).hexdigest()}


def resize_propagated64(x, skip, ratios, graph, topology):
    """坐标保持原图F32；特征允许F64，禁止在两次resize之间舍入。"""
    if x.dtype not in (np.float32, np.float64) or skip.dtype != np.float32 or ratios.dtype != np.float32 or ratios.shape != (4,):
        raise ValueError('original F32 coordinates and propagated feature domain')
    if x.ndim != 4 or skip.ndim != 4 or x.shape[0] != 1 or skip.shape[0] != 1 or any(not np.isfinite(a).all() for a in (x, skip, ratios)):
        raise ValueError('complete finite native feature domains')
    env = {topology['deepTensor']: x, topology['skipTensor']: skip, topology['hostRatiosInput']: ratios}
    coords = {axis: {key: u.metadata_value(graph, env, topology['resizePrefix'] + axis + '_' + key)
                     for key in ('lower', 'upper', 'weight0', 'weight1')} for axis in ('y', 'x')}
    for axis, incoming, outgoing, shape in [('y', x.shape[2], skip.shape[2], (1, 1, skip.shape[2], 1)),
                                           ('x', x.shape[3], skip.shape[3], (1, 1, 1, skip.shape[3]))]:
        for key in ('lower', 'upper'):
            a = coords[axis][key]
            if a.dtype != np.int64 or a.shape != (outgoing,) or np.any(a < 0) or np.any(a >= incoming):
                raise ValueError('original whole coordinate index domain')
        for key in ('weight0', 'weight1'):
            a = coords[axis][key]
            if a.dtype != np.float32 or a.shape != shape or np.any(a < 0) or np.any(a > 1):
                raise ValueError('original whole F32 coordinate weight domain')
    y, z = coords['y'], coords['x']
    top = np.take(x, y['lower'], axis=2).astype(np.float64)
    bottom = np.take(x, y['upper'], axis=2).astype(np.float64)
    top_value = z['weight0'].astype(np.float64) * np.take(top, z['lower'], axis=3) + z['weight1'].astype(np.float64) * np.take(top, z['upper'], axis=3)
    bottom_value = z['weight0'].astype(np.float64) * np.take(bottom, z['lower'], axis=3) + z['weight1'].astype(np.float64) * np.take(bottom, z['upper'], axis=3)
    result = y['weight0'].astype(np.float64) * top_value + y['weight1'].astype(np.float64) * bottom_value
    descriptor(result)
    return result, {'coordinatePolicy': u.POLICY, 'inputFeatureDomain': str(x.dtype),
                    'coordinateBindings': {axis: {key: {'dtype': str(a.dtype), 'shape': list(a.shape), 'bytesSha256': hashlib.sha256(a.tobytes()).hexdigest()} for key, a in row.items()} for axis, row in coords.items()},
                    'featureArithmeticDomain': 'float64', 'intermediateFloat32Rounding': False,
                    'actualResizeCaptureClaimed': False}


def sources():
    return u.sources() | {Path(__file__).name: d.bind(__file__)}


def deep_parameters(graph):
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

    for suffix, channels in [('0', 96), ('3', 32)]:
        conv = nodes[f'/dec2/dec2.{suffix}/Conv']
        attrs = {a.name: onnx.helper.get_attribute_value(a) for a in conv.attribute}
        if conv.op_type != 'Conv' or len(conv.input) != 2 or attrs != {'dilations': [1, 1], 'group': 1, 'kernel_shape': [3, 3], 'pads': [1, 1, 1, 1], 'strides': [1, 1]}:
            raise ValueError('actual original deep convolution without bias')
        parameter('deepConv' + suffix, conv.input[1], (32, channels, 3, 3))
    for suffix in ('1', '4'):
        prefix = f'/dec2/dec2.{suffix}/'
        add = outputs[prefix + 'Add_output_0']
        mul = outputs[add.input[0]]
        div = outputs[prefix + 'InstanceNormalization_output_0']
        sqrt = outputs[div.input[1]]
        eps_add = outputs[sqrt.input[0]]
        reshape = nodes[prefix + 'Reshape']
        groups = numpy_helper.to_array(outputs[reshape.input[1]].attribute[0].t).tolist()
        if [add.op_type, mul.op_type, div.op_type, sqrt.op_type, eps_add.op_type] != ['Add', 'Mul', 'Div', 'Sqrt', 'Add'] or groups != [0, 4, -1]:
            raise ValueError('actual original deep four-group centered normalization')
        parameter('deepGamma' + suffix, mul.input[1], (32, 1, 1))
        parameter('deepBeta' + suffix, add.input[1], (32, 1, 1))
        eps = numpy_helper.to_array(initializers[eps_add.input[1]])
        parameter('deepEpsilon' + suffix, eps_add.input[1], eps.shape)
        if eps.size != 1 or not float(eps.reshape(-1)[0]) > 0:
            raise ValueError('original positive scalar epsilon')
        configs.append({'groups': 4, 'channels': 32, 'epsilon': float(eps.reshape(-1)[0])})
    for suffix in ('2', '5'):
        values = []
        for constant in ('Constant', 'Constant_1', 'Constant_2'):
            a = numpy_helper.to_array(nodes[f'/dec2/dec2.{suffix}/{constant}'].attribute[0].t)
            if a.dtype != np.float32 or a.size != 1:
                raise ValueError('original deep GELU constant bits')
            values.append(float(a.reshape(-1)[0]))
        gelus.append(dict(zip(('sqrt2FromOriginalFloat32', 'oneFromOriginalFloat32', 'halfFromOriginalFloat32'), values, strict=True)))
    if gelus[0] != gelus[1]:
        raise ValueError('different original deep GELU constant bits')
    return parameters, {'parameterBindings': bindings, 'deepGroupNorms': configs, 'deepGelu': gelus[0]}


def derive(design_ref):
    design = d.read(design_ref)
    if design['purpose'] != 'complete74_deep_dec2_two_origin_fixed_wasm_skip_math_design_only' or design['analyticalBudgetAllocatedNow'] or design['newProjectModelInputsAllowedNow'] or design['newSyntheticModelInputsAllowedNow']:
        raise ValueError('original pre-budget deep diagnostic design')
    for ref in design['inputs'].values():
        d.checked(ref)
    prior = d.read(design['inputs']['upstreamMath'])
    cross = d.read(design['inputs']['featureCross'])
    if not prior['ok'] or prior['summary']['wasm_features']['failedOrdinals'] != [40, 41, 74] or not cross['ok'] or cross['summary']['deep_cuda_skip_wasm']['failedOrdinals'] or cross['fullModelLearnedGatePassed']:
        raise ValueError('preserved complete original math failure and conditional oracle')
    _, old, parameters, graph = u.resources(d.checked(prior['inputs']['execution']))
    parent = d.read(design['inputs']['parentScope'])
    trace = d.read(design['inputs']['trace'])
    old_design = d.read(old['design'])
    if design['inputs']['graph'] != old['model'] or design['inputs']['parentScope'] != old_design['inputs']['parentScope'] or design['inputs']['trace'] != old_design['inputs']['trace'] or not trace['layerConclusionsAllowed']:
        raise ValueError('same authoritative observation graph and full parent')
    mapping = {row['module']: row for row in parent['mapping']}
    indices = {row['module']: i for i, row in enumerate(parent['mapping'])}
    outputs = {o: n for n in graph.graph.node for o in n.output}
    names = {n.name: n for n in graph.graph.node}
    inits = {i.name: i for i in graph.graph.initializer}
    conv = outputs[mapping['dec2.0']['tensor']]
    concat = outputs[conv.input[0]]
    last = outputs[concat.input[0]]
    prefix = last.name.removesuffix('output')
    semantic = {'firstConv': conv.name, 'concat': concat.name, 'resizeLast': last.name,
                'orderedConvInputs': list(conv.input), 'orderedConcatInputs': list(concat.input)}
    if semantic != design['semanticTopology'] or concat.op_type != 'Concat' or {a.name: onnx.helper.get_attribute_value(a) for a in concat.attribute} != {'axis': 1} or list(concat.input) != [last.output[0], mapping['enc2.5']['tensor']] or last.op_type != 'Add' or not prefix.startswith('native_bilinear_') or names[prefix + 'input_shape'].input[0] != mapping['enc3.5']['tensor']:
        raise ValueError('actual graph deep resize then ordered skip concatenate')
    for axis, index in [('y', 0), ('x', 1)]:
        node = names[prefix + axis + '_ratio']
        if node.op_type != 'Gather' or node.input[0] != 'resizeRatios' or int(numpy_helper.to_array(inits[node.input[1]])) != index:
            raise ValueError('original first resize ratio axes')
    for suffix, expected in [('half', .5), ('one_f', 1.), ('zero_f', 0.)]:
        a = numpy_helper.to_array(inits[prefix + suffix])
        if a.dtype != np.float32 or a.shape != () or float(a) != expected:
            raise ValueError('original first resize F32 constants')
    extra, configs = deep_parameters(graph)
    parameters.update(extra)
    cases = []
    for c, oc, pc, wc in zip(design['cases'], old['cases'], parent['cases'], trace['captures']['wasm'], strict=True):
        if any(c['ordinal'] != row['ordinal'] or c['candidateIdentity'] != row['candidateIdentity'] for row in (oc, pc, wc)) or c['candidateIdentity']['identity']['split'] != 'train' or c['candidateInput'] != oc['candidateInput'] or c['originalStrictCudaHeads'] != oc['originalCudaHeads'] or c['resizeRatios'] != pc['resizeRatios'] or c['fixedWasmSkip'] != oc['features']['enc1.5']['wasm'] or c['fixedWasmPresence'] != oc['originalWasmHeads']['presence']:
            raise ValueError('reconstruction_mismatch: stable complete native train identity')
        h, w = c['candidateInput']['shape'][2:]
        ratios = t.read_tensor(c['resizeRatios'])
        expected = np.asarray([np.float32(h // 4) / np.float32(h // 2), np.float32(w // 4) / np.float32(w // 2), np.float32(h // 2) / np.float32(h), np.float32(w // 2) / np.float32(w)], np.float32)
        m.same_bytes(ratios, expected)
        for module, channels, factor in [('enc2.5', 32, 2), ('enc3.5', 64, 4), ('dec2.5', 32, 2)]:
            if c['features'][module] != {'cuda': pc['strictCudaLayers'][module], 'wasm': wc['outputs'][f'layer{indices[module]:02d}']}:
                raise ValueError('exact original captured deep features')
            for ref in c['features'][module].values():
                a = t.read_tensor(ref)
                if a.dtype != np.float32 or a.shape != (1, channels, h // factor, w // factor):
                    raise ValueError('original complete deep feature shapes')
        cases.append(c | {'originalCudaDelta': oc['originalCudaDelta']})
    count = len(cases)
    if count != design['fullCandidateCount'] or design['branches'] != BRANCHES or design['requiredMaxAbs'] != 1e-4 or design['requiredDecodedPixelDifferences'] or design['requiredPresenceDecisionDifferences'] or not design['productHold'] or design['formalReleaseAllowed'] or design['fullModelLearnedGatePassed']:
        raise ValueError('original denominator gates and diagnosis only')
    p = {key: old[key] for key in ('model', 'firstGroupNorm', 'lastGroupNorm', 'gelu', 'maximumOutputPixelsPerChunk', 'coordinatePolicy')}
    p |= configs | {'design': design_ref, 'purpose': 'complete_deep_dec2_fixed_wasm_skip_math_only', 'fullCandidateCount': count,
                    'cases': cases, 'branches': BRANCHES, 'deepTopology': {'deepTensor': mapping['enc3.5']['tensor'], 'skipTensor': mapping['enc2.5']['tensor'], 'hostRatiosInput': 'resizeRatios', 'resizePrefix': prefix},
                    'lastTopology': old['topology'], 'allOriginalNodeBindings': [{'name': n.name, 'sha256': hashlib.sha256(n.SerializeToString()).hexdigest()} for n in graph.graph.node],
                    'storagePolicy': POLICY, 'savedStages': list(SAVED), 'orderedStages': list(STAGES),
                    'analyticalEvaluationsAllowed': {k: 2 * count for k in STAGES[:-1]} | {'total': 2 * count * (len(STAGES) - 1)},
                    'singleFinalFloat32Conversions': count * 2, 'expectedRawCount': count * 4,
                    'expectedRawBytes': sum(2 * (32 * (c['candidateInput']['shape'][2] // 2) * (c['candidateInput']['shape'][3] // 2) * 8 + np.prod(c['candidateInput']['shape'][2:]).item() * 4) for c in cases),
                    'requiredMaxAbs': 1e-4, 'requiredDecodedPixelDifferences': 0, 'requiredPresenceDecisionDifferences': 0,
                    'newProjectModelInputsAllowed': 0, 'newSyntheticModelInputsAllowed': 0, 'optimizerStepsAllowed': 0, 'valInputsAllowed': 0, 'protectedInputsAllowed': 0, 'newChatImageInputsAllowed': 0,
                    'actualFp32RepairOrWholeModelUnreachableProven': False, 'fullModelLearnedGatePassed': False, 'formalReleaseAllowed': False, 'productHold': True}
    return p, parameters, graph


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
    origin = 'cuda' if journal.branch == BRANCHES[0] else 'wasm'
    refs = {key: case['features'][key][origin] for key in ('enc2.5', 'enc3.5')}
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
    boundary_error = float(np.abs(a - t.read_tensor(case['features']['dec2.5'][origin]).astype(np.float64)).max())
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
    return {'branch': journal.branch, 'stages': journal.records, 'deepBoundaryAgainstSameOriginMaxAbs': boundary_error,
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
        report = {'ok': True, 'decision': 'complete_deep_dec2_fixed_wasm_skip_math_diagnostic_only', 'inputs': {'execution': d.bind(execution)},
                  'records': records, 'summary': t.summarize(p, records), 'candidateCount': len(records),
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
