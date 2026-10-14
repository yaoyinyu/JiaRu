"""原F32坐标链与双域特征的末级上采样/解码数学诊断，不执行模型。"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import numpy as np
import onnx
from onnx import numpy_helper

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('reviewed_upstream_tail', HERE / 'analyze-reviewed-decoder-counterfactual.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
d = m.d
t = m.t
BRANCHES = ['cuda_features', 'wasm_features']
STAGES = ('resize64', 'concat64', 'firstConv64', *m.STAGES)
POLICY = 'actual_graph_float32_coordinate_and_weight_bits_then_float64_separable_values_and_decoder_once_final_float32'


def metadata_value(graph, boundaries, target):
    """仅解释原图形状/坐标子图；不执行卷积、归一化或神经运行时。"""
    values = {name: numpy_helper.to_array(value) for name, value in ((x.name, x) for x in graph.graph.initializer)}
    values.update(boundaries)
    outputs = {out: node for node in graph.graph.node for out in node.output}
    visiting = set()

    def evaluate(name):
        if name in values:
            return values[name]
        if name in visiting or name not in outputs:
            raise ValueError('unsupported cyclic/missing metadata tensor')
        visiting.add(name)
        node = outputs[name]
        attrs = {a.name: onnx.helper.get_attribute_value(a) for a in node.attribute}
        if node.domain or len(node.output) != 1:
            raise ValueError('original single-output standard metadata node')
        if node.op_type == 'Constant':
            if set(attrs) != {'value'}:
                raise ValueError('original TensorProto metadata constant')
            value = numpy_helper.to_array(attrs['value'])
        elif node.op_type == 'Shape':
            value = np.asarray(evaluate(node.input[0]).shape, np.int64)
            value = value[attrs.get('start', 0):attrs.get('end', len(value))]
        else:
            args = [evaluate(x) for x in node.input if x]
            if node.op_type == 'Gather':
                value = np.take(args[0], args[1], axis=attrs.get('axis', 0))
            elif node.op_type == 'Unsqueeze':
                value = np.expand_dims(args[0], axis=tuple(int(x) for x in args[1].reshape(-1)))
            elif node.op_type == 'Concat':
                value = np.concatenate(args, axis=attrs['axis'])
            elif node.op_type == 'Cast':
                if attrs['to'] not in (onnx.TensorProto.FLOAT, onnx.TensorProto.INT64):
                    raise ValueError('unsupported metadata cast domain')
                value = args[0].astype(np.float32 if attrs['to'] == onnx.TensorProto.FLOAT else np.int64)
            elif node.op_type == 'Slice':
                axes = args[3] if len(args) > 3 else np.arange(args[1].size)
                steps = args[4] if len(args) > 4 else np.ones(args[1].size, np.int64)
                slices = [slice(None)] * args[0].ndim
                for start, end, axis, step in zip(args[1], args[2], axes, steps, strict=True):
                    slices[int(axis)] = slice(int(start), int(end), int(step))
                value = args[0][tuple(slices)]
            elif node.op_type == 'Range':
                value = np.arange(args[0].item(), args[1].item(), args[2].item(), dtype=args[0].dtype)
            elif node.op_type == 'Floor':
                value = np.floor(args[0])
            elif node.op_type in ('Add', 'Sub', 'Mul', 'Max', 'Min'):
                if len(args) != 2 or args[0].dtype != args[1].dtype:
                    raise ValueError('original binary metadata storage domains')
                operation = {'Add': np.add, 'Sub': np.subtract, 'Mul': np.multiply, 'Max': np.maximum, 'Min': np.minimum}[node.op_type]
                value = operation(*args)
            else:
                raise ValueError('unsupported metadata operator ' + node.op_type)
        value = np.asarray(value)
        if value.dtype not in (np.dtype('float32'), np.dtype('int64')) or not np.isfinite(value).all():
            raise ValueError('finite original metadata domain')
        values[name] = value
        visiting.remove(name)
        return value

    return evaluate(target)


def resize64(x, skip, ratios, graph, topology):
    if x.dtype != np.float32 or skip.dtype != np.float32 or ratios.dtype != np.float32:
        raise ValueError('original F32 feature/ratio storage')
    if x.ndim != 4 or skip.ndim != 4 or x.shape[0] != 1 or skip.shape[0] != 1 or ratios.shape != (4,) or not all(np.isfinite(a).all() for a in (x, skip, ratios)):
        raise ValueError('native finite feature and metadata domains')
    h, w = skip.shape[2:]
    env = {topology['deepTensor']: x, topology['skipTensor']: skip, topology['hostRatiosInput']: ratios}
    prefix = topology['resizePrefix']
    coordinates = {axis: {key: metadata_value(graph, env, prefix + axis + '_' + key)
                          for key in ('lower', 'upper', 'weight0', 'weight1')} for axis in ('y', 'x')}
    for axis, incoming, outgoing, shape in [('y', x.shape[2], h, (1, 1, h, 1)), ('x', x.shape[3], w, (1, 1, 1, w))]:
        row = coordinates[axis]
        for key in ('lower', 'upper'):
            if row[key].dtype != np.int64 or row[key].shape != (outgoing,) or np.any(row[key] < 0) or np.any(row[key] >= incoming):
                raise ValueError('whole native metadata indices')
        for key in ('weight0', 'weight1'):
            if row[key].dtype != np.float32 or row[key].shape != shape or np.any(row[key] < 0) or np.any(row[key] > 1):
                raise ValueError('whole original F32 coordinate weights')
    y, z = coordinates['y'], coordinates['x']
    top = np.take(x, y['lower'], axis=2).astype(np.float64)
    bottom = np.take(x, y['upper'], axis=2).astype(np.float64)
    top_value = z['weight0'].astype(np.float64) * np.take(top, z['lower'], axis=3) + z['weight1'].astype(np.float64) * np.take(top, z['upper'], axis=3)
    bottom_value = z['weight0'].astype(np.float64) * np.take(bottom, z['lower'], axis=3) + z['weight1'].astype(np.float64) * np.take(bottom, z['upper'], axis=3)
    result = y['weight0'].astype(np.float64) * top_value + y['weight1'].astype(np.float64) * bottom_value
    if result.shape != (1, x.shape[1], h, w) or not np.isfinite(result).all():
        raise ValueError('complete original native resize domain')
    bindings = {axis: {key: {'dtype': str(value.dtype), 'shape': list(value.shape), 'bytesSha256': hashlib.sha256(value.tobytes()).hexdigest()}
                       for key, value in row.items()} for axis, row in coordinates.items()}
    return result, {'coordinatePolicy': POLICY, 'coordinateBindings': bindings,
                    'featureArithmeticDomain': 'float64', 'actualResizeCaptureClaimed': False,
                    'coveredNativePixelsPerChannel': h * w}


def concat64(resized, skip):
    if resized.dtype != np.float64 or skip.dtype != np.float32 or resized.ndim != 4 or skip.ndim != 4 or resized.shape[0] != skip.shape[0] or resized.shape[2:] != skip.shape[2:] or not all(np.isfinite(a).all() for a in (resized, skip)):
        raise ValueError('native F64 resize plus unchanged F32 skip')
    return np.concatenate([resized, skip.astype(np.float64)], axis=1), {'orderedInputs': ['upsampledDeep', 'originalSkip'], 'axis': 1, 'skipPromotionOnly': True, 'actualConcatCaptureClaimed': False}


def validate_contract(p):
    count = len(p['cases'])
    if count <= 0 or count != p['fullCandidateCount'] or p['branchCandidateCount'] != 2 * count or p['branches'] != BRANCHES:
        raise ValueError('complete dynamic two-origin denominator')
    if [c['ordinal'] for c in p['cases']] != list(range(1, count + 1)) or p['analyticalEvaluationsAllowed'] != ({stage: 2 * count for stage in STAGES} | {'total': 2 * count * len(STAGES)}) or p['singleFinalFloat32Conversions'] != 2 * count:
        raise ValueError('all candidates/stages/final conversions')
    if p['coordinatePolicy'] != POLICY or p['requiredMaxAbs'] != 1e-4 or p['requiredDecodedPixelDifferences'] != 0 or p['requiredPresenceDecisionDifferences'] != 0:
        raise ValueError('original coordinate policy and final head gates')
    if any(p[key] != 0 for key in ('newProjectModelInputsAllowed', 'newSyntheticModelInputsAllowed', 'optimizerStepsAllowed', 'valInputsAllowed', 'protectedInputsAllowed', 'newChatImageInputsAllowed')):
        raise ValueError('zero neural and protected budget')
    if not p['productHold'] or p['formalReleaseAllowed'] or p['fullModelLearnedGatePassed']:
        raise ValueError('mathematical evidence cannot approve deployment')


def sources():
    return m.sources() | {Path(__file__).name: d.bind(__file__)}


def derive(design_ref):
    design = d.read(design_ref)
    if design['purpose'] != 'complete74_two_origin_upstream_resize_skip_first_conv_counterfactual_design_only' or design['analyticalBudgetAllocatedNow'] or design['newProjectModelInputsAllowedNow'] or design['newSyntheticModelInputsAllowedNow']:
        raise ValueError('current pre-budget upstream design')
    for ref in design['inputs'].values():
        d.checked(ref)
    prior = d.read(design['inputs']['previousMath'])
    if not prior['ok'] or prior['summary']['wasm_dec1_0']['failedOrdinals'] != [40, 41, 74] or prior['fullModelLearnedGatePassed']:
        raise ValueError('preserve complete prior failure')
    _, old, parameters = m.resources(d.checked(prior['inputs']['execution']))
    if old != d.read(design['inputs']['previousMathScope']) or len(design['cases']) != len(old['cases']) or design['fullCandidateCount'] != len(old['cases']):
        raise ValueError('authoritative complete prior scope')
    old_design = d.read(old['design'])
    if design['inputs']['trace'] != old_design['inputs']['trace'] or design['inputs']['parentScope'] != old_design['inputs']['scope'] or design['inputs']['graph'] != old['model']:
        raise ValueError('same authoritative source observation and original graph')
    parent = d.read(design['inputs']['parentScope'])
    trace = d.read(design['inputs']['trace'])
    graph = onnx.load(d.checked(design['inputs']['graph']))
    outputs = {out: node for node in graph.graph.node for out in node.output}
    names = {node.name: node for node in graph.graph.node}
    inits = {value.name: value for value in graph.graph.initializer}
    mapping = {row['module']: row for row in parent['mapping']}
    module_index = {row['module']: i for i, row in enumerate(parent['mapping'])}
    conv = outputs[mapping['dec1.0']['tensor']]
    concat = outputs[conv.input[0]]
    last = outputs[concat.input[0]]
    prefix = last.name.removesuffix('output')
    if conv.op_type != 'Conv' or len(conv.input) != 2 or concat.op_type != 'Concat' or list(concat.input) != [last.output[0], mapping['enc1.5']['tensor']] or last.op_type != 'Add' or not prefix.startswith('native_bilinear_'):
        raise ValueError('actual upstream semantic topology')
    attrs = {a.name: onnx.helper.get_attribute_value(a) for a in conv.attribute}
    if attrs != {'dilations': [1, 1], 'group': 1, 'kernel_shape': [3, 3], 'pads': [1, 1, 1, 1], 'strides': [1, 1]} or {a.name: onnx.helper.get_attribute_value(a) for a in concat.attribute} != {'axis': 1}:
        raise ValueError('original no-bias convolution and concatenation')
    if names[prefix + 'input_shape'].input[0] != mapping['dec2.5']['tensor']:
        raise ValueError('original deep feature boundary')
    topology = {'deepTensor': mapping['dec2.5']['tensor'], 'skipTensor': mapping['enc1.5']['tensor'], 'hostRatiosInput': 'resizeRatios', 'resizePrefix': prefix}
    if design['semanticTopology'] != {'firstConv': conv.name, 'concat': concat.name, 'resizeLast': last.name, 'orderedConcatInputs': list(concat.input), 'orderedConvInputs': list(conv.input)}:
        raise ValueError('frozen actual design node identities')
    for axis, expected in [('y', 2), ('x', 3)]:
        gather = names[prefix + axis + '_ratio']
        if gather.op_type != 'Gather' or gather.input[0] != 'resizeRatios' or int(numpy_helper.to_array(inits[gather.input[1]])) != expected:
            raise ValueError('original exact host ratio coordinate axis')
    for suffix, expected in [('half', .5), ('one_f', 1.), ('zero_f', 0.)]:
        value = numpy_helper.to_array(inits[prefix + suffix])
        if value.dtype != np.float32 or value.shape != () or float(value) != expected:
            raise ValueError('original float32 coordinate constant bits')
    kernel_proto = inits[conv.input[1]]
    kernel = numpy_helper.to_array(kernel_proto)
    if kernel.dtype != np.float32 or kernel.shape != (16, 48, 3, 3) or not np.isfinite(kernel).all():
        raise ValueError('original first convolution parameter bytes')
    parameters['upstreamConvWeight'] = kernel
    cases = []
    for old_case, design_case, source_case, capture in zip(old['cases'], design['cases'], parent['cases'], trace['captures']['wasm'], strict=True):
        if old_case['ordinal'] != design_case['ordinal'] or old_case['candidateIdentity'] != design_case['candidateIdentity'] or old_case['candidateInput'] != design_case['input'] or old_case['originalCudaHeads'] != design_case['originalStrictCudaHeads']:
            raise ValueError('stable full train identity and head references')
        if old_case['candidateIdentity']['identity']['split'] != 'train':
            raise ValueError('train only')
        if any(row['ordinal'] != old_case['ordinal'] or row['candidateIdentity'] != old_case['candidateIdentity'] for row in (source_case, capture)) or design_case['resizeRatios'] != source_case['resizeRatios']:
            raise ValueError('stable actual observation and metadata identity')
        ratios = t.read_tensor(design_case['resizeRatios'])
        native = old_case['candidateInput']['shape'][2:]
        expected_ratios = np.asarray([np.float32(native[0] // 2) / np.float32(native[0]), np.float32(native[1] // 2) / np.float32(native[1])], np.float32)
        m.same_bytes(ratios[2:], expected_ratios)
        for module, channels, factor in [('enc1.5', 16, 1), ('dec2.5', 32, 2), ('dec1.0', 16, 1)]:
            if design_case['features'][module] != {'cuda': source_case['strictCudaLayers'][module], 'wasm': capture['outputs'][f'layer{module_index[module]:02d}']}:
                raise ValueError('exact authoritative captured source feature')
            for origin in ('cuda', 'wasm'):
                value = t.read_tensor(design_case['features'][module][origin])
                if value.dtype != np.float32 or value.shape != (1, channels, native[0] // factor, native[1] // factor):
                    raise ValueError('complete finite original native source features')
            if module == 'dec1.0':
                for origin in ('cuda', 'wasm'):
                    if design_case['features'][module][origin] != old_case['observed'][module][origin]:
                        raise ValueError('original observed first convolution output')
        case = old_case | {'features': design_case['features'], 'resizeRatios': design_case['resizeRatios'],
                           'branches': {'cuda_features': old_case['branches']['cuda_dec1_0'], 'wasm_features': old_case['branches']['wasm_dec1_0']}}
        cases.append(case)
    count = len(cases)
    p = {key: old[key] for key in ('model', 'firstGroupNorm', 'lastGroupNorm', 'gelu', 'maximumOutputPixelsPerChunk')}
    p |= {'purpose': 'complete_upstream_two_origin_math_diagnostic_only', 'design': design_ref,
          'priorTailScope': d.bind(d.checked(d.read(prior['inputs']['execution'])['scope'])),
          'originalFirstConv': {'name': conv.name, 'initializerName': kernel_proto.name, 'tensorProtoSha256': hashlib.sha256(kernel_proto.SerializeToString()).hexdigest(), 'bytesSha256': hashlib.sha256(kernel.tobytes()).hexdigest()},
          'coordinatePolicy': POLICY, 'topology': topology,
          'fullCandidateCount': count, 'branchCandidateCount': 2 * count, 'cases': cases, 'branches': BRANCHES,
          'analyticalEvaluationsAllowed': {stage: 2 * count for stage in STAGES} | {'total': 2 * count * len(STAGES)},
          'singleFinalFloat32Conversions': 2 * count,
          'expectedRawCount': count * 2 * (len(STAGES) + 1),
          'expectedRawBytes': sum(c['candidateInput']['shape'][2] * c['candidateInput']['shape'][3] for c in cases) * 2 * (178 * 8 + 4),
          'requiredMaxAbs': 1e-4, 'requiredDecodedPixelDifferences': 0, 'requiredPresenceDecisionDifferences': 0,
          'requiredSignedEquationResidual': 1e-12, 'newProjectModelInputsAllowed': 0, 'newSyntheticModelInputsAllowed': 0,
          'optimizerStepsAllowed': 0, 'valInputsAllowed': 0, 'protectedInputsAllowed': 0, 'newChatImageInputsAllowed': 0,
          'actualRepairOrWholeModelUnreachableNotProvenByMath': True,
          'fullModelLearnedGatePassed': False, 'formalReleaseAllowed': False, 'productHold': True}
    validate_contract(p)
    return p, parameters, graph


def resources(execution):
    e = d.read(d.bind(execution))
    if e['sources'] != sources() or e['runtime'] != m.decoder.runtime_binding():
        raise ValueError('frozen full source chain and math runtime')
    p = d.read(e['scope'])
    actual, parameters, graph = derive(p['design'])
    if actual != p:
        raise ValueError('reconstruction_mismatch: complete upstream contract')
    return e, p, parameters, graph


def evaluate_case(c, p, parameters, graph, run):
    new_branches = {}
    upstream = {}
    for branch, inputs in c['branches'].items():
        origin = 'cuda' if branch == 'cuda_features' else 'wasm'
        features = {key: c['features'][key][origin] for key in ('enc1.5', 'dec2.5')}
        resize, resize_stats = run(branch, 'resize64', features | {'resizeRatios': c['resizeRatios']},
                                   lambda: resize64(t.read_tensor(features['dec2.5']), t.read_tensor(features['enc1.5']), t.read_tensor(c['resizeRatios']), graph, p['topology']))
        concat, concat_stats = run(branch, 'concat64', {'resize64': resize, 'originalSkip': features['enc1.5']},
                                   lambda: concat64(t.read_tensor(resize), t.read_tensor(features['enc1.5'])))
        conv, conv_stats = run(branch, 'firstConv64', {'concat64': concat},
                               lambda: m.decoder.conv64(t.read_tensor(concat), parameters['upstreamConvWeight'], p['maximumOutputPixelsPerChunk']))
        upstream[branch] = {'resize64': resize, 'concat64': concat, 'firstConv64': conv,
                             'upstreamStatistics': {'resize64': resize_stats, 'concat64': concat_stats, 'firstConv64': conv_stats}}
        new_branches[branch] = {'firstGnInput': conv, 'presence': inputs['presence']}
    result = m.decoder.evaluate_case(c | {'branches': new_branches}, p, parameters, run)
    for row in result['branches']:
        row.update(upstream[row['branch']])
    return result


def make_report(execution, root, p, records):
    signed = []
    for case, record in zip(p['cases'], records, strict=True):
        branches = {b['branch']: b for b in record['branches']}
        stages = {}
        for stage, module in [('firstConv64', 'dec1.0'), ('firstGn64', 'dec1.1'), ('firstGelu64', 'dec1.2'), ('conv64', 'dec1.3'), ('lastGn64', 'dec1.4'), ('lastGelu64', 'dec1.5'), ('delta64', 'delta'), ('mask32', 'mask')]:
            actual = case['observed'][module] if module != 'mask' else {'cuda': case['originalCudaHeads']['mask'], 'wasm': case['originalWasmHeads']['mask']}
            value = m.decompose(t.read_tensor(actual['cuda']), t.read_tensor(actual['wasm']), t.read_tensor(branches['cuda_features'][stage]), t.read_tensor(branches['wasm_features'][stage]), p['requiredSignedEquationResidual'])
            value.pop('residualsAreCumulativeFromDec1_0NotIndividualOperatorErrors')
            value['residualsAreCumulativeFromOriginalFeaturePairNotIndividualOperatorErrors'] = True
            stages[stage] = value
        signed.append({'ordinal': case['ordinal'], 'candidateIdentity': case['candidateIdentity'], 'stages': stages})
    files = list((root / 'results').glob('*.bin'))
    size = sum(path.stat().st_size for path in files)
    if len(files) != p['expectedRawCount'] or size != p['expectedRawBytes']:
        raise ValueError('full actual mathematical RAW denominator/bytes')
    events = [d.bind(path) for path in sorted((root / 'events').glob('*.json'))]
    if len(events) != p['analyticalEvaluationsAllowed']['total']:
        raise ValueError('full analytical event denominator')
    return {'schemaVersion': 1, 'ok': True, 'decision': 'complete_upstream_two_origin_math_reconstructed_diagnostic_only',
            'inputs': {'execution': d.bind(execution), 'auditor': d.bind(__file__)}, 'records': records,
            'summary': t.summarize(p, records), 'signedDecomposition': signed, 'startEvents': events,
            'analyticalEvaluationsConsumed': p['analyticalEvaluationsAllowed'], 'singleFinalFloat32Conversions': p['singleFinalFloat32Conversions'],
            'candidateCount': len(records), 'branchCandidateCount': 2 * len(records), 'actualRawCount': len(files), 'actualRawBytes': size,
            'coordinatePolicy': p['coordinatePolicy'], 'unobservedResizeOrConcatClaimedAsActualCapture': False,
            'originalFinalHeadByteFidelityPreserved': True, 'actualFp32RepairOrWholeModelUnreachableProven': False,
            'newModelCalls': 0, 'optimizerSteps': 0, 'valInputs': 0, 'protectedInputs': 0, 'newChatImageInputs': 0,
            'oldFailuresAndConsumedBudgetsPreserved': True, 'fullModelLearnedGatePassed': False, 'formalReleaseAllowed': False, 'productHold': True}


def compute(execution, root, replay=False):
    e, p, parameters, graph = resources(execution)
    if e['outputRoot'] != str(root):
        raise ValueError('frozen exclusive output root')
    if not replay:
        root.mkdir(exist_ok=False)
        (root / 'events').mkdir()
        (root / 'results').mkdir()
    records = []
    expected_events = []
    try:
        for case in p['cases']:
            def run(branch, stage, inputs, fn):
                stem = f'{case["ordinal"]:03d}-{branch}-{stage}'
                if stage != 'mask32':
                    event = root / 'events' / (stem + '-start.json')
                    expected_events.append(event.name)
                    value = t.stage_event(execution, case, branch, stage, inputs)
                    if replay:
                        if d.read(d.bind(event)) != value:
                            raise ValueError('original exact analytical event')
                    else:
                        d.new(event, value)
                array, stats = fn()
                path = root / 'results' / (stem + '.bin')
                if replay:
                    ref = d.bind(path) | {'dtype': str(array.dtype), 'shape': list(array.shape)}
                    m.same_bytes(t.read_tensor(ref), array)
                else:
                    ref = t.save(path, array)
                return ref, stats
            record = evaluate_case(case, p, parameters, graph, run)
            path = root / 'results' / f'{case["ordinal"]:03d}-record.json'
            if replay:
                if d.read(d.bind(path)) != record:
                    raise ValueError('full upstream mathematical record replay')
            else:
                d.new(path, record)
            records.append(record)
            print(json.dumps({'ordinal': case['ordinal'], 'stagesCompleted': len(expected_events), 'replay': replay}), flush=True)
        if sorted(expected_events) != sorted(path.name for path in (root / 'events').glob('*.json')):
            raise ValueError('no extra/missing mathematical events')
        result = make_report(execution, root, p, records)
        if replay:
            if result != d.read(d.bind(root / 'report.json')):
                raise ValueError('reconstruction_mismatch: complete upstream report')
        else:
            d.new(root / 'report.json', result)
        print(json.dumps({'ok': True, 'summary': result['summary'], 'newModelCalls': 0}), flush=True)
    except BaseException as err:
        if not replay:
            d.new(root / 'execution-failure.json', {'ok': False, 'decision': 'reconstruction_mismatch', 'error': str(err),
                                                  'execution': d.bind(execution), 'analyticalStagesStarted': len(expected_events),
                                                  'completeCandidateRecords': len(records), 'newModelCalls': 0, 'productHold': True})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--execution', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--verify-report', action='store_true')
    a = parser.parse_args()
    root = a.output.resolve()
    if a.verify_report:
        execution = d.checked(d.read(d.bind(root / 'report.json'))['inputs']['execution'])
    else:
        execution = a.execution.resolve()
    compute(execution, root, a.verify_report)
