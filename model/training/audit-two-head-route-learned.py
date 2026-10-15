"""学得双头验收：复用已通过控制的数值执行和捕获协议，单列学得身份与预算。"""
import argparse
import ast
import importlib.util
import inspect
import json
from pathlib import Path
import platform

import numpy as np
import onnxruntime as ort

SOURCE = Path(__file__).with_name('audit-two-head-route-control.py')
spec = importlib.util.spec_from_file_location('learned_original_capture', SOURCE)
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
p, ROOT = old.p, old.ROOT
BUDGET = {'onnxInputsPerBackend': 74, 'backends': ['cpu', 'wasm', 'webgpu'], 'totalOnnxInputs': 222,
          'extraF64WasmMaskInputs': 74, 'browserCoordinateCalls': 296, 'internalValInputsAllowed': 0,
          'protectedInputsAllowed': 0, 'restartAllowed': False}
QUALITY = {'maxAbs': 1e-4, 'decodedPixelDifferences': 0, 'presenceDecisionDifferences': 0}


def adapt(name):
    tree = ast.parse(inspect.getsource(getattr(old, name))); sites = []
    class Labels(ast.NodeTransformer):
        def visit_Subscript(self, node):
            node = self.generic_visit(node)
            if name == 'parity' and isinstance(node.slice, ast.Constant) and node.slice.value == 'control':
                node.slice.value = 'learned'; sites.append('reference_slot')
            return node

        def visit_Dict(self, node):
            node = self.generic_visit(node)
            for i, key in enumerate(node.keys):
                if name == 'cpu' and isinstance(key, ast.Constant) and key.value == 'learnedInputs':
                    if not isinstance(node.values[i], ast.Constant) or node.values[i].value != 0:
                        raise ValueError('exact original CPU accounting site')
                    node.values[i].value = 74; sites.append('cpu_learned_inputs')
            return node

        def visit_Constant(self, node):
            if name == 'cpu' and node.value in ['actual_cpu_control', 'cpuControlGatePassed']:
                sites.append(node.value)
                node.value = {'actual_cpu_control': 'actual_cpu_learned', 'cpuControlGatePassed': 'cpuLearnedGatePassed'}[node.value]
            if name == 'serve' and isinstance(node.value, str) and '<title>全74新双头路由控制</title>' in node.value:
                sites.append('html_label')
                node.value = node.value.replace('全74新双头路由控制', '全74学得双头路由验收').replace('执行全74新双头控制', '执行全74学得双头验收')
            return node
    tree = Labels().visit(tree); ast.fix_missing_locations(tree)
    expected = {'parity': ['reference_slot'], 'cpu': ['actual_cpu_control', 'cpu_learned_inputs', 'cpuControlGatePassed'], 'serve': ['html_label']}
    if sorted(sites) != sorted(expected[name]):
        raise ValueError('exact reference/accounting/display adaptation: ' + name)
    exec(compile(tree, str(Path(__file__).resolve()), 'exec'), old.__dict__)
    return sites


ADAPTATIONS = {name: adapt(name) for name in ['parity', 'cpu', 'serve']}


def resources(root):
    e = old.read(root / 'execution.json')
    if e['root'] != str(root) or e['sources']['model/training/audit-two-head-route-learned.py'] != p.bind(__file__):
        raise ValueError('frozen learned executor')
    if e['runtimeVersions'] != {'python': platform.python_version(), 'numpy': np.__version__, 'ort': ort.__version__}:
        raise ValueError('same runtime versions')
    if e['learnedBudget'] != BUDGET or e['quality'] != QUALITY or e['captureAdaptations'] != ADAPTATIONS:
        raise ValueError('full original learned scope and gates')
    for ref in [*e['sources'].values(), *e['pythonRuntimeFiles'].values(), e['browserBinary']]:
        p.checked(ref)
    pre = p.read(e['preflight']); control = p.read(e['controlGate'])
    if pre['referenceKind'] != 'learned' or len(pre['cases']) != 74 or not control['fullNonzeroRouteControlPassed']:
        raise ValueError('current full control before learned acceptance')
    for ref in [*pre['sources'].values(), *pre['nativeRuntimeSources'].values(), pre['model'],
                pre['wasm'], pre['parameterPack'], pre['parameterConfig'], pre['weights']]:
        p.checked(ref)
    return e, pre


old.resources = resources


def freeze(root, preflight):
    if not root.is_relative_to(ROOT / 'model/reviews'):
        raise ValueError('isolated new learned scope')
    pre = p.read(p.bind(preflight)); control = p.read(pre['controlGate'])
    ce = p.read(control['execution']); cp = p.read(ce['preflight'])
    if not control['fullNonzeroRouteControlPassed'] or control['learnedInputs'] != 0 or pre['learnedBudgetAllocatedNow']:
        raise ValueError('unconsumed learned budget and complete new control')
    for name in old.MODULES:
        ref = ce['sources'][str(Path('model/runtime') / name)]
        if ref != p.bind(ROOT / 'model/runtime' / name):
            raise ValueError('identical tested runtime bytes')
    nr = p.read(ce['nodeCoordinateReplay'])
    old.coordinates(Path(ce['nodeCoordinateReplay']['path']).parent, pre, nr)
    for a, b in zip(pre['cases'], cp['cases'], strict=True):
        for key in ['ordinal', 'candidateIdentity', 'h', 'w', 'input', 'resizeRatios', 'coordinateAxes']:
            if a[key] != b[key]:
                raise ValueError('full tested input/coordinate identity')
    sources = {path.relative_to(ROOT).as_posix(): p.bind(path) for path in [Path(__file__), SOURCE,
        Path(__file__).with_name('prepare-two-head-route-learned.py'),
        Path(__file__).with_name('verify-native-multiscale-browser-v2.py'),
        *[ROOT / 'model/runtime' / name for name in old.MODULES]]}
    root.mkdir(exist_ok=False)
    for name in ['cpu', 'events', 'browser', 'coordinates']:
        (root / name).mkdir()
    e = {'purpose': 'complete74_learned_three_backend_actual_two_head_route_acceptance',
        'preflight': p.bind(preflight), 'controlGate': pre['controlGate'], 'controlExecution': control['execution'],
        'sources': sources, 'pythonRuntimeFiles': ce['pythonRuntimeFiles'], 'browserBinary': ce['browserBinary'],
        'runtimeVersions': ce['runtimeVersions'], 'learnedBudget': BUDGET, 'quality': QUALITY,
        'captureAdaptations': ADAPTATIONS, 'root': str(root), 'formalReleaseAllowed': False, 'productHold': True}
    p.new(root / 'execution.json', e)
    resources(root)
    print(json.dumps({'ok': True, 'learnedOnnxBudget': 222, 'extraF64MaskBudget': 74}), flush=True)


def reconstruct(root):
    result = old.reconstruct(root)
    result['fullLearnedRouteGatePassed'] = result.pop('fullNonzeroRouteControlPassed')
    result['decision'] = 'complete74_learned_route_reconstructed'
    result['learnedInputs'] = 296
    result['learnedOnnxInputs'] = 222
    result['learnedExtraF64MaskInputs'] = 74
    result['uniqueCandidates'] = 74
    result['captureAdapter'] = p.bind(__file__)
    if old.read(root / 'cpu-report.json')['learnedInputs'] != 74:
        raise ValueError('actual CPU learned accounting')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('mode', choices=['freeze', 'cpu', 'serve', 'audit', 'verify'])
    parser.add_argument('--root', type=Path, required=True); parser.add_argument('--preflight', type=Path)
    parser.add_argument('--port', type=int, default=8869); args = parser.parse_args(); root = args.root.resolve()
    if args.mode == 'freeze': freeze(root, args.preflight.resolve())
    elif args.mode == 'cpu': old.cpu(root)
    elif args.mode == 'serve': old.serve(root, args.port)
    else:
        result = reconstruct(root)
        if args.mode == 'verify':
            if result != old.read(root / 'report.json'):
                raise ValueError('complete learned route reconstruction mismatch')
        else: p.new(root / 'report.json', result)
        print(json.dumps({'ok': True, 'fullLearnedRouteGatePassed': result['fullLearnedRouteGatePassed'],
                          'summary': result['summary']}), flush=True)
