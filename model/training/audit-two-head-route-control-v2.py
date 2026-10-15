"""只修冻结读取器的Windows来源键；原计划/脚本及零输入失败保持。"""
import argparse
import ast
import importlib.util
import inspect
import json
from pathlib import Path

SOURCE = Path(__file__).with_name('audit-two-head-route-control.py')
spec = importlib.util.spec_from_file_location('two_head_frozen_original', SOURCE)
old = importlib.util.module_from_spec(spec); spec.loader.exec_module(old)


def portable_reader(source):
    tree = ast.parse(source); sites = []
    class Keys(ast.NodeTransformer):
        def visit_Subscript(self, node):
            node = self.generic_visit(node)
            if isinstance(node.slice, ast.Constant) and node.slice.value == 'model/training/audit-two-head-route-control.py':
                sites.append(node.lineno)
                node.slice = ast.copy_location(ast.Constant(str(Path('model/training/audit-two-head-route-control.py'))), node.slice)
            return node
    tree = Keys().visit(tree); ast.fix_missing_locations(tree)
    if len(sites) != 1: raise ValueError('exact one frozen resource-key site')
    return tree, sites


tree, SITES = portable_reader(inspect.getsource(old.resources))
exec(compile(tree, str(Path(__file__).resolve()), 'exec'), old.__dict__)
fixed = old.resources


def validate(root):
    proof = old.read(root / 'adapter-v2.json')
    if proof['adapter'] != old.p.bind(__file__) or proof['execution'] != old.p.bind(root / 'execution.json') or proof['repairSites'] != SITES:
        raise ValueError('frozen reader adapter bytes')
    return fixed(root)


old.resources = validate


def reconstruct(root):
    result = old.reconstruct(root)
    result['resourceKeyAdapter'] = old.p.bind(__file__)
    result['adapterExecution'] = old.p.bind(root / 'adapter-v2.json')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('mode', choices=['freeze-adapter', 'cpu', 'serve', 'audit', 'verify'])
    parser.add_argument('--root', type=Path, required=True); parser.add_argument('--port', type=int, default=8868)
    args = parser.parse_args(); root = args.root.resolve()
    if args.mode == 'freeze-adapter':
        fixed(root)
        if (root / 'cpu-attempt.json').exists() or list((root / 'cpu').iterdir()) or list((root / 'events').iterdir()): raise ValueError('only untouched original neural budget can be carried')
        old.p.new(root / 'initial-resource-key-failure.json', {'ok': False, 'exitCode': 1,
            'error': "KeyError: 'model/training/audit-two-head-route-control.py'", 'cpuAttemptCreated': False,
            'originalModelStarts': 0, 'frozenSource': old.p.bind(SOURCE), 'originalExecution': old.p.bind(root / 'execution.json')})
        old.p.new(root / 'adapter-v2.json', {'adapter': old.p.bind(__file__), 'execution': old.p.bind(root / 'execution.json'),
            'repairSites': SITES, 'originalModelStarts': 0, 'newNeuralBudgetBeyondOriginal': 0,
            'originalFailure': old.p.bind(root / 'initial-resource-key-failure.json'),
            'onlyNativePathKeyLookupChanged': True, 'productHold': True})
        print(json.dumps({'ok': True, 'newModelInputs': 0, 'carriedOriginalBudget': 296}))
    elif args.mode == 'cpu': old.cpu(root)
    elif args.mode == 'serve': old.serve(root, args.port)
    else:
        result = reconstruct(root)
        if args.mode == 'verify':
            if result != old.read(root / 'report.json'): raise ValueError('complete route control replay mismatch')
        else: old.p.new(root / 'report.json', result)
        print(json.dumps({'ok': True, 'fullNonzeroRouteControlPassed': result['fullNonzeroRouteControlPassed'], 'summary': result['summary']}), flush=True)
