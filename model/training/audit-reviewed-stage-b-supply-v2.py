"""兼容历史项目相对审核页；冻结v1及其拒绝记录保持，字节门不变。"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('stage_b_supply_v1', Path(__file__).with_name('audit-reviewed-stage-b-supply.py'))
v1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v1)


class RelativeEvidence(v1.Evidence):
    def __init__(self, root=ROOT):
        super().__init__()
        self.root = Path(root).resolve()

    def checked(self, ref):
        if set(ref) != {'path', 'sha256'}:
            v1.fail('noncanonical binding')
        declared = Path(ref['path'])
        if declared.is_absolute():
            return super().checked(ref)
        path = (self.root / declared).resolve()
        if not path.is_relative_to(self.root):
            v1.fail('relative review binding escapes project root')
        resolved = {'path': str(path), 'sha256': ref['sha256']}
        return super().checked(resolved)


def audit(execution_ref):
    execution = json.loads(Path(execution_ref['path']).read_bytes())
    if v1.bind(execution_ref['path']) != execution_ref:
        v1.fail('execution binding')
    if execution['sources']['compatibilityReader'] != v1.bind(__file__):
        v1.fail('compatibility reader identity')
    if execution['relativeBindingRoot'] != str(ROOT):
        v1.fail('relative root must be frozen project root')
    attempt = json.loads(Path(execution['priorFailedAttempt']['path']).read_bytes())
    if v1.bind(execution['priorFailedAttempt']['path']) != execution['priorFailedAttempt'] or attempt['exitCode'] != 1 or 'noncanonical binding' not in attempt['stderr'] or attempt['output'] is not None:
        v1.fail('preserved v1 failure')
    prior = json.loads(Path(attempt['execution']['path']).read_bytes())
    if v1.bind(attempt['execution']['path']) != attempt['execution'] or prior['sources']['runner'] != execution['sources']['runner'] or prior['scope'] != execution['scope']:
        v1.fail('original frozen scope/source')
    # v1全量算法保持；唯一扩展是历史相对页路径的解析，任何SHA变化仍拒绝。
    v1.Evidence = RelativeEvidence
    result = v1.audit(execution_ref)
    mappings = []

    def collect(value):
        if isinstance(value, dict):
            if set(value) == {'path', 'sha256'} and not Path(value['path']).is_absolute():
                resolved = (ROOT / value['path']).resolve()
                mappings.append({'declaredBindingPreserved': value, 'resolvedBinding': v1.bind(resolved)})
                if not resolved.is_relative_to(ROOT) or mappings[-1]['resolvedBinding']['sha256'] != value['sha256']:
                    v1.fail('relative binding final byte check')
            else:
                for child in value.values():
                    collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    collect(result['roleRecords'])
    result['schemaVersion'] = 2
    result['relativePathCompatibility'] = {'projectRoot': str(ROOT), 'originalPathStringsAndHashesUnmodified': True,
                                         'relativeReviewBindings': mappings,
                                         'priorFailedAttempt': execution['priorFailedAttempt'],
                                         'priorAttemptAccepted': False, 'priorSourceAndScopeUnchanged': True}
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--execution', type=Path)
    p.add_argument('--output', type=Path)
    p.add_argument('--verify-report', type=Path)
    args = p.parse_args()
    if args.verify_report:
        old = json.loads(args.verify_report.read_bytes())
        result = audit(old['execution'])
        if old != result:
            v1.fail('whole v2 report differs')
    else:
        if not args.execution or not args.output:
            p.error('--execution and --output required')
        result = audit(v1.bind(args.execution))
        with args.output.open('xb') as stream:
            stream.write(v1.raw(result)); stream.flush(); os.fsync(stream.fileno())
    print(json.dumps({'ok': True, 'decision': result['decision'], 'counts': result['observedCounts'],
                      'wholeGroups': len(result['wholeGroups']), 'mappedAssets': result['mappedAcquisitionAssets'],
                      'pendingTrainGroups': len(result['pendingTrainGroupPriorities']),
                      'nextGroups': result['pendingTrainGroupPriorities'][:3],
                      'verifiedBindings': len(result['verifiedBindings']), 'trainingAllowed': False, 'productHold': True}, ensure_ascii=False))


if __name__ == '__main__':
    main()
