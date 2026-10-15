"""原输入完整mask支路F64数学充分性；固定presence，不替代实际部署。"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

import numpy as np
import onnx
from onnx import numpy_helper

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('full_mask_enc3', HERE / 'analyze-reviewed-full-enc3-counterfactual.py')
f = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)
deep, u, m, t, d = f.deep, f.u, f.m, f.t, f.d
PREFIX = ('enc1FirstConv64', 'enc1FirstGn64', 'enc1FirstGelu64', 'enc1SecondConv64', 'enc1LastGn64', 'enc1LastGelu64',
          'enc2AveragePool64', 'enc2FirstConv64', 'enc2FirstGn64', 'enc2FirstGelu64', 'enc2SecondConv64', 'enc2LastGn64', 'enc2LastGelu64')
STAGES = (*PREFIX, *f.STAGES)
BRANCHES = ['original_input_full_mask_float64_fixed_wasm_presence']
SAVED = ('mask32',)
POLICY = 'all_full_arrays_sha256_exclusive_start_done_recompute_all_save_only_final_mask_f32'
descriptor = f.descriptor


def sources():
    return f.sources() | {Path(__file__).name: d.bind(__file__)}


def average_pool64(x):
    if x.dtype != np.float64 or x.ndim != 4 or x.shape[0] != 1 or min(x.shape[1:]) < 1 or min(x.shape[2:]) < 2 or not np.isfinite(x).all():
        raise ValueError('complete finite propagated F64 pool input')
    h, w = x.shape[2] // 2, x.shape[3] // 2
    a = x[:, :, :h * 2, :w * 2]
    out = ((a[:, :, 0::2, 0::2] + a[:, :, 0::2, 1::2]) + a[:, :, 1::2, 0::2]) + a[:, :, 1::2, 1::2]
    out *= .25
    descriptor(out)
    return out, {'kernel': [2, 2], 'strides': [2, 2], 'pads': [0, 0, 0, 0], 'ceilMode': 0,
                 'sumOrder': 'top_left_plus_top_right_then_bottom_left_then_bottom_right_divide_four',
                 'inputStorageDomain': 'float64', 'actualPoolCaptureClaimed': False}


def concat64(resized, skip):
    if any(a.dtype != np.float64 or a.ndim != 4 or a.shape[0] != 1 or not np.isfinite(a).all() for a in (resized, skip)) or resized.shape[2:] != skip.shape[2:]:
        raise ValueError('both computed native skip and resized feature must stay F64')
    return np.concatenate((resized, skip), axis=1), {'orderedInputs': ['computed_resized_f64', 'computed_skip_f64'], 'intermediateFloat32Rounding': False}


def resize64(x, skip, ratios, graph, topology):
    if x.dtype != np.float64 or skip.dtype != np.float64 or ratios.dtype != np.float32 or ratios.shape != (4,):
        raise ValueError('F64 features/skips and original F32 coordinate ratios')
    if x.ndim != 4 or skip.ndim != 4 or x.shape[0] != 1 or skip.shape[0] != 1 or any(not np.isfinite(a).all() for a in (x, skip, ratios)):
        raise ValueError('complete finite native resize inputs')
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
    top, bottom = np.take(x, y['lower'], axis=2), np.take(x, y['upper'], axis=2)
    top_value = z['weight0'].astype(np.float64) * np.take(top, z['lower'], axis=3) + z['weight1'].astype(np.float64) * np.take(top, z['upper'], axis=3)
    bottom_value = z['weight0'].astype(np.float64) * np.take(bottom, z['lower'], axis=3) + z['weight1'].astype(np.float64) * np.take(bottom, z['upper'], axis=3)
    result = y['weight0'].astype(np.float64) * top_value + y['weight1'].astype(np.float64) * bottom_value
    descriptor(result)
    return result, {'coordinatePolicy': u.POLICY, 'inputFeatureDomain': 'float64', 'skipFeatureDomain': 'float64',
                    'coordinateBindings': {axis: {key: {'dtype': str(a.dtype), 'shape': list(a.shape), 'bytesSha256': hashlib.sha256(a.tobytes()).hexdigest()} for key, a in row.items()} for axis, row in coords.items()},
                    'featureArithmeticDomain': 'float64', 'intermediateFloat32Rounding': False, 'actualResizeCaptureClaimed': False}


def encoder_parameters(graph):
    nodes = {n.name: n for n in graph.graph.node}
    outputs = {o: n for n in graph.graph.node for o in n.output}
    initializers = {i.name: i for i in graph.graph.initializer}
    parameters, configs, bindings = {}, {}, {}
    attrs = lambda n: {a.name: onnx.helper.get_attribute_value(a) for a in n.attribute}

    def parameter(key, name, shape):
        proto = initializers[name]
        array = numpy_helper.to_array(proto)
        if array.dtype != np.float32 or array.shape != shape or not np.isfinite(array).all():
            raise ValueError('original front encoder F32 parameter domain')
        parameters[key] = array
        bindings[key] = {'initializerName': name, **descriptor(array), 'tensorProtoSha256': hashlib.sha256(proto.SerializeToString()).hexdigest()}
        return array

    for block, incoming, channels in [('enc1', 4, 16), ('enc2', 16, 32)]:
        norms, gelus = [], []
        for suffix, count in [('0', incoming), ('3', channels)]:
            node = nodes[f'/{block}/{block}.{suffix}/Conv']
            if node.op_type != 'Conv' or len(node.input) != 2 or attrs(node) != {'dilations': [1, 1], 'group': 1, 'kernel_shape': [3, 3], 'pads': [1, 1, 1, 1], 'strides': [1, 1]}:
                raise ValueError('original front encoder no-bias padded 3x3 convolution')
            parameter(block + 'Conv' + suffix, node.input[1], (channels, count, 3, 3))
        for suffix in ('1', '4'):
            prefix = f'/{block}/{block}.{suffix}/'
            add = outputs[prefix + 'Add_output_0']
            mul = outputs[add.input[0]]
            div = outputs[prefix + 'InstanceNormalization_output_0']
            sqrt = outputs[div.input[1]]
            eps_add = outputs[sqrt.input[0]]
            reshape = nodes[prefix + 'Reshape']
            shape_node = outputs[reshape.input[1]]
            groups = numpy_helper.to_array(shape_node.attribute[0].t)
            if [add.op_type, mul.op_type, div.op_type, sqrt.op_type, eps_add.op_type] != ['Add', 'Mul', 'Div', 'Sqrt', 'Add'] or groups.dtype != np.int64 or groups.tolist() != [0, 4, -1]:
                raise ValueError('original front encoder four-group centered normalization')
            parameter(block + 'Gamma' + suffix, mul.input[1], (channels, 1, 1))
            parameter(block + 'Beta' + suffix, add.input[1], (channels, 1, 1))
            proto = initializers[eps_add.input[1]]
            epsilon = parameter(block + 'Epsilon' + suffix, proto.name, numpy_helper.to_array(proto).shape)
            if epsilon.size != 1 or float(epsilon.reshape(-1)[0]) <= 0:
                raise ValueError('original positive scalar GN epsilon')
            norms.append({'groups': 4, 'channels': channels, 'epsilon': float(epsilon.reshape(-1)[0])})
        for suffix in ('2', '5'):
            values = []
            for constant in ('Constant', 'Constant_1', 'Constant_2'):
                value = numpy_helper.to_array(nodes[f'/{block}/{block}.{suffix}/{constant}'].attribute[0].t)
                if value.dtype != np.float32 or value.size != 1:
                    raise ValueError('original front encoder GELU F32 constants')
                values.append(float(value.reshape(-1)[0]))
            gelus.append(dict(zip(('sqrt2FromOriginalFloat32', 'oneFromOriginalFloat32', 'halfFromOriginalFloat32'), values, strict=True)))
        if gelus[0] != gelus[1] or gelus[0] != {'sqrt2FromOriginalFloat32': float(np.float32(np.sqrt(2))), 'oneFromOriginalFloat32': 1., 'halfFromOriginalFloat32': .5}:
            raise ValueError('same exact original front encoder GELU bits')
        configs[block] = {'groupNorms': norms, 'gelu': gelus[0]}
    first = nodes['/enc1/enc1.0/Conv']
    pool = outputs[nodes['/enc2/enc2.0/Conv'].input[0]]
    if first.input[0] != 'candidate' or pool.op_type != 'AveragePool' or list(pool.input) != ['/enc1/enc1.5/Mul_1_output_0'] or attrs(pool) != {'ceil_mode': 0, 'count_include_pad': 1, 'kernel_shape': [2, 2], 'pads': [0, 0, 0, 0], 'strides': [2, 2]}:
        raise ValueError('original candidate input and first 2x2 no-pad pool topology')
    return parameters, {'frontEncoders': configs, 'frontParameterBindings': bindings,
                        'firstPoolNode': {'name': pool.name, 'inputs': list(pool.input), 'attributes': attrs(pool), 'nodeProtoSha256': hashlib.sha256(pool.SerializeToString()).hexdigest()}}


def validate_contract(p):
    n = len(p['cases'])
    if n <= 0 or p['fullCandidateCount'] != n or p['branches'] != BRANCHES or p['orderedStages'] != list(STAGES):
        raise ValueError('complete ordered original-input mask denominator')
    if [c['ordinal'] for c in p['cases']] != list(range(1, n + 1)) or any(c['candidateIdentity']['identity']['split'] != 'train' for c in p['cases']):
        raise ValueError('full train identities, no val/protected input')
    budget = {stage: n for stage in STAGES[:-1]} | {'total': n * (len(STAGES) - 1)}
    size = sum(c['candidateInput']['shape'][2] * c['candidateInput']['shape'][3] * 4 for c in p['cases'])
    if p['analyticalEvaluationsAllowed'] != budget or p['singleFinalFloat32Conversions'] != n or p['expectedRawCount'] != n or p['expectedRawBytes'] != size:
        raise ValueError('all stages and final-only saved RAW budget')
    if p['storagePolicy'] != POLICY or p['savedStages'] != list(SAVED):
        raise ValueError('full recomputation policy without old RAW deletion')
    if p['requiredMaxAbs'] != 1e-4 or p['requiredDecodedPixelDifferences'] != 0 or p['requiredPresenceDecisionDifferences'] != 0:
        raise ValueError('original fixed final gates')
    if any(p[k] for k in ('newProjectModelInputsAllowed', 'newSyntheticModelInputsAllowed', 'optimizerStepsAllowed', 'valInputsAllowed', 'protectedInputsAllowed', 'newChatImageInputsAllowed', 'actualFp32RepairOrWholeModelUnreachableProven', 'fullModelLearnedGatePassed', 'formalReleaseAllowed')) or not p['productHold']:
        raise ValueError('conditional mask math only; zero neural budget and HOLD')


def verify_prior(ref, report, p):
    execution = d.read(report['inputs']['execution'])
    root = Path(ref['path']).parent
    if execution['sources'] != f.sources() or execution['runtime'] != t.runtime_binding() or d.read(execution['scope']) != p or execution['outputRoot'] != str(root):
        raise ValueError('frozen complete full-enc3 source/runtime/scope')
    events = []
    for case, row in zip(p['cases'], report['records'], strict=True):
        if case['ordinal'] != row['ordinal'] or case['candidateIdentity'] != row['candidateIdentity'] or [b['branch'] for b in row['branches']] != f.BRANCHES:
            raise ValueError('complete prior identities and both origins')
        if d.read(d.bind(root / 'results' / f'{case["ordinal"]:03d}-record.json')) != row:
            raise ValueError('complete prior candidate record')
        for branch in row['branches']:
            if [s['stage'] for s in branch['stages']] != list(f.STAGES):
                raise ValueError('complete prior stage denominator')
            for stage in branch['stages']:
                stem = f'{case["ordinal"]:03d}-{branch["branch"]}-{stage["stage"]}'
                start, done = root / 'events' / (stem + '-start.json'), root / 'events' / (stem + '-done.json')
                expected = {'execution': report['inputs']['execution'], 'ordinal': case['ordinal'], 'candidateIdentity': case['candidateIdentity'], 'branch': branch['branch'], 'stage': stage['stage'], 'inputs': stage['inputs']}
                if d.read(d.bind(start)) != expected or d.read(d.bind(done)) != stage or ('savedRaw' in stage) != (stage['stage'] in f.SAVED):
                    raise ValueError('original complete stage input/event/storage chain')
                if 'savedRaw' in stage and descriptor(t.read_tensor(stage['savedRaw'])) != stage['output']:
                    raise ValueError('original saved full array bytes')
                events.extend((start, done))
    if sorted(events) != sorted((root / 'events').iterdir()) or hashlib.sha256(d.raw([d.bind(x) for x in sorted(events)])).hexdigest() != report['eventManifestSha256'] or t.summarize(p, report['records']) != report['summary']:
        raise ValueError('complete prior manifest and final gates')


def derive(design_ref):
    design = d.read(design_ref)
    if design['purpose'] != 'complete74_original_input_end_to_end_mask_math_sufficiency_design_only' or any(design[k] for k in ('analyticalBudgetAllocatedNow', 'newProjectModelInputsAllowedNow', 'newSyntheticModelInputsAllowedNow')):
        raise ValueError('unallocated complete original-input mask design')
    for ref in design['inputs'].values():
        d.checked(ref)
    old = d.read(design['inputs']['currentScope'])
    actual, parameters, graph = f.derive(old['design'])
    prior, replay = d.read(design['inputs']['fullEnc3Math']), d.read(design['inputs']['independentReplay'])
    if actual != old or not prior['ok'] or not replay['ok'] or replay['exitCode'] != 0 or replay['mathReport'] != design['inputs']['fullEnc3Math']:
        raise ValueError('complete inherited full enc3 computation and independent replay')
    for key in ('stdout', 'stderr'):
        d.checked(replay[key])
    verify_prior(design['inputs']['fullEnc3Math'], prior, old)
    old_design = d.read(old['design'])
    if any(design['inputs'][key] != old_design['inputs'][key] for key in ('parentScope', 'trace', 'graph')):
        raise ValueError('same original model and full observation lineage')
    parent, trace = d.read(design['inputs']['parentScope']), d.read(design['inputs']['trace'])
    cases = []
    for c, oc, pc, wc in zip(design['cases'], old['cases'], parent['cases'], trace['captures']['wasm'], strict=True):
        keys = ('ordinal', 'candidateIdentity', 'candidateInput', 'resizeRatios', 'originalStrictCudaHeads', 'fixedWasmPresence', 'originalCudaDelta')
        expected = {key: oc[key] for key in keys} | {'originalObservedLayersAuditOnly': {'cuda': pc['strictCudaLayers'], 'wasm': {row['module']: wc['outputs'][f'layer{i:02d}'] for i, row in enumerate(parent['mapping'])}}}
        if c != expected or c['candidateInput'] != pc['input'] or c['resizeRatios'] != pc['resizeRatios']:
            raise ValueError('complete original candidate identity/input/reference audit-only layers')
        x = t.read_tensor(c['candidateInput'])
        if x.dtype != np.float32 or x.shape != (1, 4, pc['h'], pc['w']):
            raise ValueError('original four-channel native F32 input')
        for backend in ('cpu', 'wasm', 'webgpu'):
            row = trace['captures'][backend][c['ordinal'] - 1]
            if row['ordinal'] != c['ordinal'] or row['candidateIdentity'] != c['candidateIdentity'] or row['inputSha256'] != c['candidateInput']['sha256'] or row['resizeRatiosSha256'] != c['resizeRatios']['sha256']:
                raise ValueError('identical original full input and ratio bytes across backends')
        cases.append(c)
    invariants = ('allOriginalBackendInputAndHostRatioBytesIdenticalVerified', 'singleMathematicalMaskStreamBecauseOriginalInputBytesIdentical',
                  'allPriorTwoOriginBranchesFailuresAndDenominatorsPreserved', 'originalObservedActivationsAuditOnlyNotMathematicalMaskInputs',
                  'computedEnc1AndEnc2SkipValuesFloat64NotStoredBackendActivations', 'allEncoderParameterPoolAndSemanticNodeBitsMustBeDerivedBeforeBudget',
                  'originalFloat32CoordinatesAndCoarseSeedArithmeticUnchanged', 'featuresFloat64PropagatedNoIntermediateFloat32Rounding',
                  'fixedWasmPresenceIsConditionalNotFullTwoHeadModelRepair', 'stageByteHashesAndExclusiveStartDoneRecomputeAllRequired')
    if any(design[key] is not True for key in invariants) or design['orderedStages'] != list(STAGES) or design['savedStages'] != list(SAVED) or design['branches'] != BRANCHES or design['fullCandidateCount'] != len(cases):
        raise ValueError('original complete mask mathematical scope and invariants')
    extra, configs = encoder_parameters(graph)
    parameters.update(extra)
    count = len(cases)
    p = old | configs | {'design': design_ref, 'purpose': 'complete_original_input_mask_math_sufficiency_only', 'cases': cases, 'branches': BRANCHES,
                        'orderedStages': list(STAGES), 'savedStages': list(SAVED), 'storagePolicy': POLICY,
                        'fullCandidateCount': count, 'analyticalEvaluationsAllowed': {stage: count for stage in STAGES[:-1]} | {'total': count * (len(STAGES) - 1)},
                        'singleFinalFloat32Conversions': count, 'expectedRawCount': count,
                        'expectedRawBytes': sum(c['candidateInput']['shape'][2] * c['candidateInput']['shape'][3] * 4 for c in cases)}
    for key in ('requiredMaxAbs', 'requiredDecodedPixelDifferences', 'requiredPresenceDecisionDifferences', 'actualFp32RepairOrWholeModelUnreachableProven', 'fullModelLearnedGatePassed', 'formalReleaseAllowed', 'productHold'):
        if design[key] != p[key]:
            raise ValueError('original gates and hold')
    validate_contract(p)
    if (p['analyticalEvaluationsAllowed']['total'], p['singleFinalFloat32Conversions'], p['expectedRawCount'], p['expectedRawBytes']) != tuple(design[k] for k in ('plannedNewMathStagesNotAllocated', 'plannedFinalFloat32ConversionsNotAllocated', 'plannedSavedRawCountNotAllocated', 'plannedSavedRawBytesNotAllocated')):
        raise ValueError('pre-registered full mathematical budget')
    return p, parameters, graph


class StageJournal:
    """每次重放重新计算全部数组；只有最终mask落盘。"""
    def __init__(self, root, execution_ref, case, branch, replay=False):
        self.root, self.execution_ref, self.case, self.branch, self.replay = root, execution_ref, case, branch, replay
        self.records = []

    def run(self, stage, inputs, function, shape, dtype):
        if len(self.records) >= len(STAGES) or stage != STAGES[len(self.records)]:
            raise ValueError('complete ordered original-input mask chain')
        stem = f'{self.case["ordinal"]:03d}-{self.branch}-{stage}'
        start = {'execution': self.execution_ref, 'ordinal': self.case['ordinal'], 'candidateIdentity': self.case['candidateIdentity'], 'branch': self.branch, 'stage': stage, 'inputs': inputs}
        path = self.root / 'events' / (stem + '-start.json')
        if self.replay:
            if d.read(d.bind(path)) != start:
                raise ValueError('reconstruction_mismatch: full mask start event')
        else:
            d.new(path, start)
        array, stats = function()
        desc = descriptor(array)
        if desc['shape'] != list(shape) or desc['dtype'] != dtype:
            raise ValueError('reconstruction_mismatch: full native stage shape/domain')
        result = {'stage': stage, 'inputs': inputs, 'output': desc, 'statistics': stats}
        if stage in SAVED:
            path = self.root / 'results' / (stem + '.bin')
            if self.replay:
                ref = d.bind(path) | {'shape': list(array.shape), 'dtype': str(array.dtype)}
                m.same_bytes(t.read_tensor(ref), array)
            else:
                ref = t.save(path, array)
            result['savedRaw'] = ref
        path = self.root / 'events' / (stem + '-done.json')
        if self.replay:
            if d.read(d.bind(path)) != result:
                raise ValueError('reconstruction_mismatch: full mask bytes/statistics/input chain')
        else:
            d.new(path, result)
        self.records.append(result)
        return array, desc


def evaluate(case, p, parameters, graph, journal):
    if journal.branch != BRANCHES[0]:
        raise ValueError('single original input stream, fixed original presence only')
    candidate = t.read_tensor(case['candidateInput'])
    if candidate.dtype != np.float32 or candidate.ndim != 4 or candidate.shape[:2] != (1, 4):
        raise ValueError('original native F32 candidate')
    h, w = candidate.shape[2:]
    ratios = t.read_tensor(case['resizeRatios'])
    run = journal.run
    a, desc = candidate.astype(np.float64), {'originalCandidate': case['candidateInput'], 'exactFloat32ValuesPromoted': True}
    computed_skips, skip_desc = {}, {}
    boundary_errors = {}
    for block, channels, height, width in [('enc1', 16, h, w), ('enc2', 32, h // 2, w // 2), ('enc3', 64, h // 4, w // 4)]:
        shape = (1, channels, height, width)
        if block != 'enc1':
            a, desc = run(block + 'AveragePool64', {'input': desc}, lambda: average_pool64(a), (1, 16 if block == 'enc2' else 32, height, width), 'float64')
        key = 'firstEncoderConv' if block == 'enc3' else block + 'Conv0'
        a, desc = run(block + 'FirstConv64', {'input': desc}, lambda: m.decoder.conv64(a, parameters[key], p['maximumOutputPixelsPerChunk']), shape, 'float64')
        configs = {'groupNorms': p['encoderGroupNorms'], 'gelu': p['encoderGelu']} if block == 'enc3' else p['frontEncoders'][block]
        for i, suffix, tag in [(0, '1', 'First'), (1, '4', 'Last')]:
            norm = configs['groupNorms'][i]
            prefix = 'encoder' if block == 'enc3' else block
            a, desc = run(block + tag + 'Gn64', {'input': desc}, lambda: t.gn64(a, parameters[prefix + 'Gamma' + suffix], parameters[prefix + 'Beta' + suffix], norm['groups'], norm['epsilon']), shape, 'float64')
            a, desc = run(block + tag + 'Gelu64', {'input': desc}, lambda: t.gelu64(a, configs['gelu']), shape, 'float64')
            if i == 0:
                a, desc = run(block + 'SecondConv64', {'input': desc}, lambda: m.decoder.conv64(a, parameters[prefix + 'Conv3'], p['maximumOutputPixelsPerChunk']), shape, 'float64')
        computed_skips[block], skip_desc[block] = a, desc
        boundary_errors[block] = {origin: float(np.abs(a - t.read_tensor(refs[block + '.5']).astype(np.float64)).max()) for origin, refs in case['originalObservedLayersAuditOnly'].items()}
    e1, e2 = computed_skips['enc1'], computed_skips['enc2']
    half_shape, full_shape = (1, 32, h // 2, w // 2), (1, 16, h, w)
    a, desc = run('deepResize64', {'input': desc, 'computedSkip': skip_desc['enc2'], 'ratios': case['resizeRatios']}, lambda: resize64(a, e2, ratios, graph, p['deepTopology']), (1, 64, h // 2, w // 2), 'float64')
    a, desc = run('deepConcat64', {'resized': desc, 'computedSkip': skip_desc['enc2']}, lambda: concat64(a, e2), (1, 96, h // 2, w // 2), 'float64')
    a, desc = run('deepConv1_64', {'input': desc}, lambda: m.decoder.conv64(a, parameters['deepConv0'], p['maximumOutputPixelsPerChunk']), half_shape, 'float64')
    for i, suffix in enumerate(('1', '4')):
        norm = p['deepGroupNorms'][i]
        a, desc = run(f'deepGn{i+1}_64', {'input': desc}, lambda: t.gn64(a, parameters['deepGamma' + suffix], parameters['deepBeta' + suffix], norm['groups'], norm['epsilon']), half_shape, 'float64')
        a, desc = run(f'deepGelu{i+1}_64', {'input': desc}, lambda: t.gelu64(a, p['deepGelu']), half_shape, 'float64')
        if i == 0:
            a, desc = run('deepConv2_64', {'input': desc}, lambda: m.decoder.conv64(a, parameters['deepConv3'], p['maximumOutputPixelsPerChunk']), half_shape, 'float64')
    a, desc = run('resize64', {'input': desc, 'computedSkip': skip_desc['enc1'], 'ratios': case['resizeRatios']}, lambda: resize64(a, e1, ratios, graph, p['lastTopology']), (1, 32, h, w), 'float64')
    a, desc = run('concat64', {'input': desc, 'computedSkip': skip_desc['enc1']}, lambda: concat64(a, e1), (1, 48, h, w), 'float64')
    a, desc = run('firstConv64', {'input': desc}, lambda: m.decoder.conv64(a, parameters['upstreamConvWeight'], p['maximumOutputPixelsPerChunk']), full_shape, 'float64')
    norm = p['firstGroupNorm']
    a, desc = run('firstGn64', {'input': desc}, lambda: t.gn64(a, parameters['firstGamma'], parameters['firstBeta'], norm['groups'], norm['epsilon']), full_shape, 'float64')
    a, desc = run('firstGelu64', {'input': desc}, lambda: t.gelu64(a, p['gelu']), full_shape, 'float64')
    a, desc = run('conv64', {'input': desc}, lambda: m.decoder.conv64(a, parameters['convWeight'], p['maximumOutputPixelsPerChunk']), full_shape, 'float64')
    norm = p['lastGroupNorm']
    a, desc = run('lastGn64', {'input': desc}, lambda: t.gn64(a, parameters['gamma'], parameters['beta'], norm['groups'], norm['epsilon']), full_shape, 'float64')
    a, desc = run('lastGelu64', {'input': desc}, lambda: t.gelu64(a, p['gelu']), full_shape, 'float64')
    a, desc = run('delta64', {'input': desc}, lambda: t.delta64(a, parameters['deltaWeight'], parameters['deltaBias'], p['maximumOutputPixelsPerChunk']), (1, 1, h, w), 'float64')
    delta_error = float(np.abs(a - t.read_tensor(case['originalCudaDelta']).astype(np.float64)).max())
    seed = t.seed32(candidate)
    a, desc = run('finalMaskAdd64', {'input': desc, 'originalCandidate': case['candidateInput']}, lambda: t.final_mask64(seed, a), (1, 1, h, w), 'float64')
    a, _ = run('mask32', {'input': desc}, lambda: (a.astype(np.float32), {'singleFinalFloat32Rounding': True}), (1, 1, h, w), 'float32')
    references = {key: t.read_tensor(ref) for key, ref in case['originalStrictCudaHeads'].items()}
    parity = t.comparator.compare_outputs(references['mask'].reshape(-1), references['presence'].reshape(-1), a.reshape(-1), t.read_tensor(case['fixedWasmPresence']).reshape(-1), h, w)
    return {'branch': journal.branch, 'stages': journal.records, 'encoderBoundaryAgainstOriginalBackendsMaxAbsDiagnosticOnly': boundary_errors,
            'originalCudaParity': parity, 'counterfactualNumericPixelAndPresenceGatesPassed': all(parity[k] for k in ('numericGatePassed', 'decodedPixelGatePassed', 'presenceDecisionMatched', 'allReferenceAndCapturedHeadsFinite')),
            'delta64AgainstOriginalCudaMaxAbs': delta_error, 'fixedWasmPresence': case['fixedWasmPresence'], 'actualFp32RepairProven': False}


def compute(execution, root, replay=False):
    e = d.read(d.bind(execution))
    if e['sources'] != sources() or e['runtime'] != t.runtime_binding() or e['outputRoot'] != str(root):
        raise ValueError('frozen source/runtime/exclusive output root')
    p = d.read(e['scope'])
    actual, parameters, graph = derive(p['design'])
    if p != actual:
        raise ValueError('reconstruction_mismatch: full original-input derived scope')
    if not replay:
        if shutil.disk_usage(root.parent).free < p['expectedRawBytes'] + 1024**3:
            raise ValueError('saved RAW budget and one GiB reserve')
        root.mkdir(exist_ok=False)
        (root / 'events').mkdir()
        (root / 'results').mkdir()
    records, journals = [], []
    try:
        for case in p['cases']:
            journal = StageJournal(root, d.bind(execution), case, BRANCHES[0], replay)
            journals.append(journal)
            row = {'ordinal': case['ordinal'], 'candidateIdentity': case['candidateIdentity'], 'branches': [evaluate(case, p, parameters, graph, journal)]}
            path = root / 'results' / f'{case["ordinal"]:03d}-record.json'
            if replay:
                if d.read(d.bind(path)) != row:
                    raise ValueError('reconstruction_mismatch: full mask candidate record')
            else:
                d.new(path, row)
            records.append(row)
            print(json.dumps({'ordinal': case['ordinal'], 'completedStages': len(records) * len(STAGES), 'replay': replay}), flush=True)
        names = sorted(f'{c["ordinal"]:03d}-{BRANCHES[0]}-{stage}-{phase}.json' for c in p['cases'] for stage in STAGES for phase in ('start', 'done'))
        files = sorted((root / 'results').glob('*.bin'))
        if names != sorted(path.name for path in (root / 'events').iterdir()) or len(files) != p['expectedRawCount'] or sum(path.stat().st_size for path in files) != p['expectedRawBytes']:
            raise ValueError('complete stage event and final-only RAW denominator')
        report = {'ok': True, 'decision': 'complete_original_input_full_mask_math_diagnostic_only', 'inputs': {'execution': d.bind(execution)}, 'records': records,
                  'summary': t.summarize(p, records), 'candidateCount': len(records), 'analyticalEvaluationsConsumed': p['analyticalEvaluationsAllowed'],
                  'singleFinalFloat32Conversions': p['singleFinalFloat32Conversions'], 'stageByteHashes': len(records) * len(STAGES),
                  'startEventCount': len(names) // 2, 'doneEventCount': len(names) // 2,
                  'eventManifestSha256': hashlib.sha256(d.raw([d.bind(root / 'events' / name) for name in names])).hexdigest(),
                  'actualRawCount': len(files), 'actualRawBytes': sum(path.stat().st_size for path in files), 'storagePolicy': POLICY,
                  'allEncoderAndSkipValuesComputedFloat64FromOriginalCandidate': True, 'fixedPresenceIsNotActualFullTwoHeadRepair': True,
                  'actualFp32RepairOrWholeModelUnreachableProven': False, 'newModelCalls': 0, 'optimizerSteps': 0, 'valInputs': 0, 'protectedInputs': 0, 'newChatImageInputs': 0,
                  'oldFailuresAndConsumedBudgetsPreserved': True, 'fullModelLearnedGatePassed': False, 'formalReleaseAllowed': False, 'productHold': True}
        if replay:
            if report != d.read(d.bind(root / 'report.json')):
                raise ValueError('reconstruction_mismatch: entire full mask report')
        else:
            d.new(root / 'report.json', report)
        print(json.dumps({'ok': True, 'summary': report['summary'], 'actualRawBytes': report['actualRawBytes'], 'replay': replay}), flush=True)
    except BaseException as error:
        if not replay:
            d.new(root / 'execution-failure.json', {'ok': False, 'decision': 'reconstruction_mismatch', 'execution': d.bind(execution), 'error': str(error),
                                                  'completeCandidateRecords': len(records), 'completedStages': sum(len(j.records) for j in journals),
                                                  'startedEvents': len(list((root / 'events').glob('*-start.json'))), 'newModelCalls': 0, 'productHold': True})
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
