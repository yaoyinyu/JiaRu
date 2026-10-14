"""从权威全清单派生双域末级解码数学合同；不调用模型或改变冻结参考。"""
import argparse
import hashlib
import importlib.util
from pathlib import Path
import numpy as np
import onnx
from onnx import numpy_helper

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('reviewed_decoder_math', HERE / 'analyze-native-decoder-counterfactual.py')
decoder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(decoder)
t = decoder.t
d = t.d
STAGES = ('firstGn64', 'firstGelu64', 'conv64', 'lastGn64', 'lastGelu64', 'delta64', 'finalMaskAdd64')
BRANCHES = ['cuda_dec1_0', 'wasm_dec1_0']


def validate_contract(p):
    count = len(p['cases'])
    if count <= 0 or p['fullCandidateCount'] != count or p['branchCandidateCount'] != 2 * count or p['branches'] != BRANCHES:
        raise ValueError('complete two-origin denominator')
    if [c['ordinal'] for c in p['cases']] != list(range(1, count + 1)):
        raise ValueError('ordered unique candidate ordinals')
    expected = {stage: 2 * count for stage in STAGES} | {'total': len(STAGES) * 2 * count}
    if p['analyticalEvaluationsAllowed'] != expected or p['singleFinalFloat32Conversions'] != 2 * count:
        raise ValueError('exact per-stage and final conversion denominator')
    if p['requiredNumericDifferenceUnchanged'] != 1e-4 or p['requiredDecodedPixelDifferencesUnchanged'] != 0 or p['requiredPresenceDecisionDifferencesUnchanged'] != 0:
        raise ValueError('original full-head gates')
    for name in ('newProjectModelInputsAllowed', 'newSyntheticModelInputsAllowed', 'optimizerStepsAllowed',
                 'valInputsAllowed', 'protectedInputsAllowed', 'newChatImageInputsAllowed'):
        if p[name] != 0:
            raise ValueError('zero neural/optimizer/protected budget')
    if not p['productHold'] or p['formalReleaseAllowed'] or p['fullModelLearnedGatePassed']:
        raise ValueError('diagnosis cannot approve release')


def sources():
    names = ('analyze-reviewed-decoder-counterfactual.py', 'analyze-native-decoder-counterfactual.py',
             'analyze-native-tail-counterfactual.py', 'analyze-native-convolution-decomposition.py',
             'analyze-native-groupnorm-decomposition.py', 'reviewed-role-development-data.py',
             'verify-native-multiscale-browser-v2.py')
    return {name: d.bind(HERE / name) for name in names}


def same_bytes(a, b):
    if a.dtype != b.dtype or a.shape != b.shape or a.tobytes() != b.tobytes():
        raise ValueError('reconstruction_mismatch: original shape/storage/bytes')


def decompose(cuda, wasm, ideal_cuda, ideal_wasm, tolerance=1e-12):
    arrays = [a.astype(np.float64) for a in (cuda, wasm, ideal_cuda, ideal_wasm)]
    if any(a.shape != arrays[0].shape or not np.isfinite(a).all() for a in arrays):
        raise ValueError('reconstruction_mismatch: finite identical native domains')
    c, w, ic, iw = arrays
    actual = w - c
    inherited = iw - ic
    wasm_chain = w - iw
    cuda_chain = c - ic
    residual = actual - (inherited + wasm_chain - cuda_chain)
    maximum = float(np.abs(residual).max())
    if maximum > tolerance:
        raise ValueError('reconstruction_mismatch: signed same-coordinate identity')
    coordinate = tuple(int(i) for i in np.unravel_index(np.abs(actual).argmax(), actual.shape))
    return {'equationResidualMaxAbs': maximum, 'actualMaxAbs': float(np.abs(actual).max()),
            'propagatedInputMaxAbs': float(np.abs(inherited).max()),
            'wasmCumulativeChainResidualMaxAbs': float(np.abs(wasm_chain).max()),
            'cudaCumulativeChainResidualMaxAbs': float(np.abs(cuda_chain).max()),
            'actualMaximumCoordinate': list(coordinate),
            'signedAtSameCoordinate': {'actual': float(actual[coordinate]),
                                      'propagatedInput': float(inherited[coordinate]),
                                      'wasmCumulativeChainResidual': float(wasm_chain[coordinate]),
                                      'cudaCumulativeChainResidual': float(cuda_chain[coordinate])},
            'residualsAreCumulativeFromDec1_0NotIndividualOperatorErrors': True}


def derive(design_ref):
    design = d.read(design_ref)
    if design['purpose'] != 'full74_two_origin_decoder_zero_model_counterfactual_reachability':
        raise ValueError('current design purpose')
    if design['newProjectModelInputsAllowedNow'] or design['newSyntheticModelInputsAllowedNow'] or design['analyticalBudgetAllocatedNow']:
        raise ValueError('design must precede newly frozen mathematical budget')
    for ref in design['inputs'].values():
        d.checked(ref)
    parent = d.read(design['inputs']['scope'])
    trace = d.read(design['inputs']['trace'])
    cuda = d.read(design['inputs']['cudaObservation'])
    control = d.read(design['inputs']['control'])
    old = d.read(design['inputs']['original'])
    count = len(parent['cases'])
    if count != design['fullCandidateCount'] or count != len(design['candidateIdentities']):
        raise ValueError('reconstruction_mismatch: authoritative full denominator')
    if not all((trace['ok'], trace['allOwnHeadsBitwiseIdenticalAllBackends'], trace['layerConclusionsAllowed'],
                control['ok'], control['allOwnHeadsBitwiseIdenticalAllBackends'], cuda['ok'], cuda['allOriginalHeadsBitwiseEqual'])):
        raise ValueError('full observation fidelity required')
    if old['fullModelLearnedGatePassed'] or old['summary']['wasm']['failedOrdinals'] != design['failedOrdinals']:
        raise ValueError('preserved original full-model failures')
    if design['requiredMaxAbs'] != 1e-4 or design['requiredDecodedPixelDifferences'] != 0 or not design['productHold'] or design['formalReleaseAllowed']:
        raise ValueError('unchanged gates and HOLD')
    graph = onnx.load(d.checked(parent['originalGraph']))
    nodes = {n.name: n for n in graph.graph.node}
    outputs = {o: n for n in graph.graph.node for o in n.output}
    initializers = {n.name: n for n in graph.graph.initializer}
    parameters = {}
    bindings = {}

    def parameter(key, name):
        proto = initializers[name]
        value = numpy_helper.to_array(proto)
        if value.dtype != np.float32 or not np.isfinite(value).all():
            raise ValueError('original finite float32 initializer')
        parameters[key] = value
        bindings[key] = {'initializerName': name, 'shape': list(value.shape), 'dtype': 'float32',
                         'bytesSha256': hashlib.sha256(value.tobytes()).hexdigest(),
                         'tensorProtoSha256': hashlib.sha256(proto.SerializeToString()).hexdigest()}
        return value

    gn_configs = []
    for module, keys in [('dec1.1', ('firstGamma', 'firstBeta', 'firstEpsilon')),
                         ('dec1.4', ('gamma', 'beta', 'epsilon'))]:
        prefix = '/dec1/' + module + '/'
        add = outputs[prefix + 'Add_output_0']
        mul = outputs[add.input[0]]
        div = outputs[prefix + 'InstanceNormalization_output_0']
        sqrt = outputs[div.input[1]]
        epsilon_add = outputs[sqrt.input[0]]
        reshape = nodes[prefix + 'Reshape']
        groups = numpy_helper.to_array(outputs[reshape.input[1]].attribute[0].t).tolist()
        if [add.op_type, mul.op_type, div.op_type, sqrt.op_type, epsilon_add.op_type] != ['Add', 'Mul', 'Div', 'Sqrt', 'Add'] or groups != [0, 4, -1]:
            raise ValueError('actual four-group original normalization topology')
        gamma = parameter(keys[0], mul.input[1])
        beta = parameter(keys[1], add.input[1])
        epsilon = parameter(keys[2], epsilon_add.input[1])
        if gamma.shape != (16, 1, 1) or beta.shape != gamma.shape or epsilon.size != 1:
            raise ValueError('original native GN parameter shapes')
        gn_configs.append({'groups': 4, 'channels': 16, 'epsilon': float(epsilon.reshape(-1)[0]),
                           'centeredVariance': True, 'nativeChannelFirstOrder': True})
    middle = nodes['/dec1/dec1.3/Conv']
    delta = nodes['/delta/Conv']
    if len(middle.input) != 2 or len(delta.input) != 3:
        raise ValueError('actual original absent/present convolution bias')
    parameter('convWeight', middle.input[1])
    parameter('deltaWeight', delta.input[1])
    parameter('deltaBias', delta.input[2])
    if parameters['convWeight'].shape != (16, 16, 3, 3) or parameters['deltaWeight'].shape != (1, 16, 1, 1) or parameters['deltaBias'].shape != (1,):
        raise ValueError('original decoder convolution shapes')
    gelus = []
    for module in ('dec1.2', 'dec1.5'):
        values = []
        for suffix in ('Constant', 'Constant_1', 'Constant_2'):
            value = numpy_helper.to_array(nodes[f'/dec1/{module}/{suffix}'].attribute[0].t)
            if value.dtype != np.float32 or value.size != 1:
                raise ValueError('original GELU float32 constant bits')
            values.append(float(value.reshape(-1)[0]))
        gelus.append(dict(zip(('sqrt2FromOriginalFloat32', 'oneFromOriginalFloat32', 'halfFromOriginalFloat32'), values, strict=True)))
    if gelus[0] != gelus[1]:
        raise ValueError('two original GELU constants differ')
    mapping = {r['module']: i for i, r in enumerate(parent['mapping'])}
    if len(mapping) != len(parent['mapping']):
        raise ValueError('duplicate observed semantic endpoint')
    cases = []
    for i, (c, wc, cc, identity) in enumerate(zip(parent['cases'], trace['captures']['wasm'], cuda['records'], design['candidateIdentities'], strict=True), 1):
        if any(r['ordinal'] != i or r['candidateIdentity'] != identity for r in (c, wc, cc)) or identity['identity']['split'] != 'train':
            raise ValueError('reconstruction_mismatch: stable ordered full train identities')
        cuda_heads = c['references']['learned']
        wasm_heads = {k: wc['outputs'][k] for k in ('mask', 'presence')}
        observed = {}
        for module in ('dec1.0', 'dec1.1', 'dec1.2', 'dec1.3', 'dec1.4', 'dec1.5', 'delta'):
            ref = c['strictCudaLayers'][module]
            if ref != cc['outputs'][f'layer{mapping[module]:02d}']:
                raise ValueError('current strict CUDA observation binding')
            observed[module] = {'cuda': ref, 'wasm': wc['outputs'][f'layer{mapping[module]:02d}']}
        seed = t.seed32(t.read_tensor(c['input']))
        for origin, heads in [('cuda', cuda_heads), ('wasm', wasm_heads)]:
            same_bytes(seed + t.read_tensor(observed['delta'][origin]), t.read_tensor(heads['mask']))
            t.read_tensor(heads['presence'])
            for module in observed:
                a = t.read_tensor(observed[module][origin])
                expected_channels = 1 if module == 'delta' else 16
                if a.dtype != np.float32 or a.shape != (1, expected_channels, c['h'], c['w']):
                    raise ValueError('original native endpoint shapes')
        for key in ('mask', 'presence'):
            same_bytes(t.read_tensor(cuda_heads[key]), t.read_tensor(cc['outputs'][key]))
            same_bytes(t.read_tensor(wasm_heads[key]), t.read_tensor(c['ownUninstrumentedHeads']['learned']['wasm'][key]))
        cases.append({'ordinal': i, 'candidateIdentity': identity, 'candidateInput': c['input'],
                      'originalCudaHeads': cuda_heads, 'originalWasmHeads': wasm_heads,
                      'originalCudaDelta': observed['delta']['cuda'], 'originalWasmDelta': observed['delta']['wasm'],
                      'observed': observed,
                      'branches': {branch: {'firstGnInput': observed['dec1.0'][origin], 'presence': heads['presence']}
                                   for branch, origin, heads in [('cuda_dec1_0', 'cuda', cuda_heads), ('wasm_dec1_0', 'wasm', wasm_heads)]}})
    scope = {'purpose': 'reviewed_complete_two_origin_decoder_counterfactual_diagnostic_only',
             'design': design_ref, 'model': parent['originalGraph'], 'parameterBindings': bindings,
             'nodeBindings': [{'name': n.name, 'sha256': hashlib.sha256(n.SerializeToString()).hexdigest()} for n in graph.graph.node],
             'fullCandidateCount': count, 'branches': BRANCHES, 'branchCandidateCount': 2 * count,
             'cases': cases, 'firstGroupNorm': gn_configs[0], 'lastGroupNorm': gn_configs[1], 'gelu': gelus[0],
             'maximumOutputPixelsPerChunk': 4096, 'requiredNumericDifferenceUnchanged': 1e-4,
             'requiredDecodedPixelDifferencesUnchanged': 0, 'requiredPresenceDecisionDifferencesUnchanged': 0,
             'requiredSignedEquationResidual': 1e-12,
             'analyticalEvaluationsAllowed': {stage: 2 * count for stage in STAGES} | {'total': len(STAGES) * 2 * count},
             'singleFinalFloat32Conversions': 2 * count, 'newProjectModelInputsAllowed': 0,
             'newSyntheticModelInputsAllowed': 0, 'optimizerStepsAllowed': 0,
             'valInputsAllowed': 0, 'protectedInputsAllowed': 0, 'newChatImageInputsAllowed': 0,
             'actualRepairAndWholeModelUnreachableNotProvenByMath': True,
             'formalReleaseAllowed': False, 'fullModelLearnedGatePassed': False, 'productHold': True}
    validate_contract(scope)
    return scope, parameters


def resources(execution):
    e = d.read(d.bind(execution))
    if e['sources'] != sources() or e['runtime'] != decoder.runtime_binding():
        raise ValueError('frozen source and single-thread math runtime')
    p = d.read(e['scope'])
    expected, parameters = derive(p['design'])
    if expected != p:
        raise ValueError('reconstruction_mismatch: derived scope and original bytes')
    return e, p, parameters


def make_report(execution, root, p, records):
    summary = t.summarize(p, records)
    decomposition = []
    stage_modules = [('firstGn64', 'dec1.1'), ('firstGelu64', 'dec1.2'), ('conv64', 'dec1.3'),
                     ('lastGn64', 'dec1.4'), ('lastGelu64', 'dec1.5'), ('delta64', 'delta'), ('mask32', 'mask')]
    for case, record in zip(p['cases'], records, strict=True):
        branches = {row['branch']: row for row in record['branches']}
        row = {'ordinal': case['ordinal'], 'candidateIdentity': case['candidateIdentity'], 'stages': {}}
        for stage, module in stage_modules:
            actual = case['observed'][module] if module != 'mask' else {'cuda': case['originalCudaHeads']['mask'], 'wasm': case['originalWasmHeads']['mask']}
            row['stages'][stage] = decompose(t.read_tensor(actual['cuda']), t.read_tensor(actual['wasm']),
                                           t.read_tensor(branches['cuda_dec1_0'][stage]), t.read_tensor(branches['wasm_dec1_0'][stage]), p['requiredSignedEquationResidual'])
        decomposition.append(row)
    return {'schemaVersion': 1, 'ok': True, 'decision': 'complete_two_origin_decoder_math_reconstructed_diagnostic_only',
            'inputs': {'execution': d.bind(execution), 'auditor': d.bind(__file__)}, 'records': records,
            'summary': summary, 'signedDecomposition': decomposition,
            'startEvents': [d.bind(x) for x in sorted((root / 'events').glob('*.json'))],
            'analyticalEvaluationsConsumed': p['analyticalEvaluationsAllowed'], 'singleFinalFloat32Conversions': p['singleFinalFloat32Conversions'],
            'candidateCount': len(records), 'branchCandidateCount': 2 * len(records),
            'originalFinalHeadByteFidelityPreserved': True, 'newModelCalls': 0, 'optimizerSteps': 0,
            'valInputs': 0, 'protectedInputs': 0, 'newChatImageInputs': 0,
            'actualFp32RepairOrWholeModelUnreachableProven': False, 'oldFailuresAndConsumedBudgetsPreserved': True,
            'fullModelLearnedGatePassed': False, 'formalReleaseAllowed': False, 'productHold': True}


if __name__ == '__main__':
    import json
    parser = argparse.ArgumentParser()
    parser.add_argument('--execution', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--verify-report', action='store_true')
    a = parser.parse_args()
    root = a.output.resolve()
    decoder.resources = resources
    decoder.make_report = make_report
    if a.verify_report:
        result = decoder.reconstruct(root)
        if result != d.read(d.bind(root / 'report.json')):
            raise ValueError('reconstruction_mismatch: complete counterfactual replay')
        print(json.dumps({'ok': True, 'summary': result['summary'], 'newModelCalls': 0}))
    else:
        decoder.execute(a.execution.resolve(), root)
