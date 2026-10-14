"""修复三处旧range上界；继承完整捕获，旧审核失败保留，控制禁止重跑。"""
import argparse
import ast
import importlib.util
import inspect
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('native_deployment_original_frozen', HERE/'audit-reviewed-native-deployment.py')
old = importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
d = old.d


def corrected_reconstructor(source):
    tree = ast.parse(source); sites = []
    class Repair(ast.NodeTransformer):
        def visit_Call(self, node):
            if (isinstance(node.func, ast.Name) and node.func.id == 'range' and len(node.args) == 2 and
                    isinstance(node.args[0], ast.Constant) and node.args[0].value == 1 and
                    isinstance(node.args[1], ast.Constant) and node.args[1].value == 69):
                sites.append(node.lineno)
                node.args[1] = ast.BinOp(left=ast.Name(id='N', ctx=ast.Load()), op=ast.Add(), right=ast.Constant(value=1))
            return self.generic_visit(node)
    tree = Repair().visit(tree); ast.fix_missing_locations(tree)
    if len(sites) != 3: raise ValueError('exact three old range upper bounds required')
    return tree, sites


tree, SITES = corrected_reconstructor(inspect.getsource(old.reconstruct))
exec(compile(tree, str(Path(__file__).resolve()), 'exec'), old.__dict__)
raw_reconstruct = old.reconstruct


def reconstruct(root):
    result = raw_reconstruct(root)
    result['reconstructionReader'] = d.bind(__file__)
    result['oldRangeAuditFailurePreserved'] = None
    # 控制的失败报告在原阶段目录，不读取或改写其错误分母。
    if result['kind'] == 'control':
        failure = d.read(d.bind(root/'audit-failure.json'))
        if failure != {'ok': False, 'decision': 'reconstruction_mismatch', 'error': 'all68 per backend', 'productHold': True}: raise ValueError('original failed audit preserved')
        result['oldRangeAuditFailurePreserved'] = d.bind(root/'audit-failure.json')
    result['rangeRepairSites'] = SITES
    return result


def control_gate(e):
    root = Path(e['controlRoot']); report = reconstruct(root); saved_ref = d.bind(root/'report-v2.json')
    if report != d.read(saved_ref): raise ValueError('full corrected control report reconstruction')
    old.require_control_gate(report)
    if 'inheritedControlGate' in e and e['inheritedControlGate'] != saved_ref: raise ValueError('inherited actual control gate')
    return saved_ref


old.control_gate = control_gate


def validate_execution(path):
    e, p, models, compare = old.resources(path)
    if e['sources'].get('reconstructionAdapter') != d.bind(__file__): raise ValueError('new frozen reader binding')
    prior = d.read(e['priorExecution'])
    for key in ('scope', 'runtimeFiles', 'pythonRuntimeFiles', 'runtimeVersions', 'expectedEnvironment', 'stageRoots', 'controlRoot'):
        if e[key] != prior[key]: raise ValueError('same original model/assets/stage identities and unused budget')
    if e['budgetCarry'] != {'originalBackendBudget': 444, 'inheritedControlBackendInputs': 222,
                          'newControlInputsAllowed': 0, 'remainingLearnedBackendInputs': 222,
                          'restartAllowed': False}: raise ValueError('no restart or budget inflation')
    control_gate(e)
    return e


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--execution', type=Path); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--stage', choices=['learned']); parser.add_argument('--serve', action='store_true'); parser.add_argument('--audit', action='store_true')
    parser.add_argument('--verify-report', action='store_true'); parser.add_argument('--port', type=int, default=8852)
    args = parser.parse_args(); root = args.output.resolve()
    if args.audit or args.verify_report:
        result = reconstruct(root); target = root/'report-v2.json'
        if args.verify_report:
            if result != d.read(d.bind(target)): raise ValueError('complete corrected report bytes')
        else: d.new(target, result)
        print(json.dumps({k: result[k] for k in ('ok', 'kind', 'allThreeBackendStageGatesPassed', 'summary')}))
    elif args.serve:
        preparation = d.read(d.bind(root/'preparation.json')); validate_execution(d.checked(preparation['execution'])); old.serve(root, args.port)
    else:
        validate_execution(args.execution.resolve()); old.prepare(args.execution.resolve(), root, 'learned')
