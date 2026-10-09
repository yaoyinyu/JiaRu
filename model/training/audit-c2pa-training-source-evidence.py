"""C2PA来源证据分层：CLI成功、签名/绑定成功、完整父链与训练准入互不代替。

只读冻结的官方验证器JSON；不解析成训练许可，不修改任何素材或证书。
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

REQUIRED = {'claimSignature.validated', 'assertion.dataHash.match', 'signingCredential.trusted'}


def bind(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def read(ref):
    if bind(ref['path']) != ref:
        raise ValueError('reconstruction_mismatch: ' + ref['path'])
    return json.loads(Path(ref['path']).read_bytes())


def summarize(document):
    active = document.get('active_manifest')
    if not active or active not in document.get('manifests', {}):
        raise ValueError('active C2PA manifest missing')
    manifest = document['manifests'][active]
    if manifest.get('label') != active:
        raise ValueError('active manifest identity drift')
    results = document.get('validation_results', {}).get('activeManifest')
    if not isinstance(results, dict) or any(not isinstance(results.get(k), list) for k in ('success', 'failure', 'informational')):
        raise ValueError('validation result scope missing')
    successes = {v['code'] for v in results['success']}
    failures = [v['code'] for v in results['failure']]
    status = [v['code'] for v in document.get('validation_status', [])]
    # 顶层状态和活动manifest各自保留；任一失败都禁止将局部成功晋升整体。
    qualified = document.get('validation_state') == 'Trusted' and not failures and not status and REQUIRED <= successes
    assertions = [a for a in manifest.get('assertions', []) if a.get('label') in ('c2pa.actions', 'c2pa.actions.v2')]
    if len(assertions) != 1 or not isinstance(assertions[0].get('data', {}).get('actions'), list):
        raise ValueError('single explicit actions assertion required')
    data = assertions[0]['data']; actions = data['actions']
    all_included = data.get('allActionsIncluded') is True
    ingredients_present = 'ingredients' in manifest
    ingredients = manifest.get('ingredients', [])
    if not isinstance(ingredients, list):
        raise ValueError('ingredients must be an explicit list')
    signature = manifest.get('signature_info', {})
    return {
        'activeManifest': active, 'validationState': document.get('validation_state'),
        'issuerDeclaration': signature.get('issuer'), 'signerNameDeclaration': signature.get('common_name'),
        'signatureAlgorithm': signature.get('alg'), 'signatureTimeDeclaration': signature.get('time'),
        'timestampTrusted': 'timeStamp.trusted' in successes and not any('timeStamp.untrusted' == v['code'] for v in results['informational']),
        'signatureAndAssetHashIndividuallyValidated': {'claimSignature': 'claimSignature.validated' in successes,
                                                     'assetHash': 'assertion.dataHash.match' in successes},
        'credentialValidationQualified': qualified,
        'failureCodes': failures, 'topLevelStatusCodes': status,
        'informationalCodes': [v['code'] for v in results['informational']],
        'actionsPreserved': actions, 'allActionsIncluded': all_included,
        'ingredientFieldPresent': ingredients_present, 'declaredIngredients': ingredients,
        'declaredWatermarkActions': [a for a in actions if a.get('action', '').startswith('c2pa.watermarked')],
        'zeroDeclaredIngredientsNeverProvesNoReferenceInputs': True,
        'actualGenerationRequestOrParentChainEvidenceRequired': True,
        'completeParentChainProven': False, 'sourceParentIndependenceQualified': False,
        'modelShortcutExclusionProven': False, 'trainingAllowed': False,
    }


def build(plan_ref):
    plan = read(plan_ref)
    for ref in plan['inputs'].values():
        if bind(ref['path']) != ref: raise ValueError('input binding drift')
    rows = []
    keys = set()
    for item in plan['records']:
        key = tuple(item['identity'][k] for k in ('split', 'fileName', 'imageSha256'))
        if key in keys: raise ValueError('duplicate source identity')
        keys.add(key)
        for ref in (item['sourceImage'], item['isolatedCopy']):
            if bind(ref['path']) != ref or ref['sha256'] != item['identity']['imageSha256']:
                raise ValueError('source/copy hash drift')
        execution = read(item['execution'])
        if execution['exitCode'] != 0:
            raise ValueError('CLI failed; not a source qualification result')
        if execution['identity'] != item['identity'] or execution['sourceSha256After'] != item['identity']['imageSha256'] or execution['copySha256After'] != item['identity']['imageSha256']:
            raise ValueError('execution source identity drift')
        rows.append({'identity': item['identity'], 'sourceGroup': item['sourceGroup'],
                     'sourceImage': item['sourceImage'], 'officialVerifierReport': item['c2paReport'],
                     'inspection': summarize(read(item['c2paReport']))})
    qualified = sum(r['inspection']['credentialValidationQualified'] for r in rows)
    return {'schemaVersion': 1, 'plan': plan_ref, 'records': rows,
            'metadataConsistencyOk': True, 'ok': False,
            'decision': 'c2pa_partial_evidence_not_complete_generation_lineage_or_training_permission',
            'counts': {'sources': len(rows), 'credentialQualified': qualified, 'credentialNotQualified': len(rows)-qualified,
                       'incompleteActionHistory': sum(not r['inspection']['allActionsIncluded'] for r in rows),
                       'declaredWatermarkActions': sum(bool(r['inspection']['declaredWatermarkActions']) for r in rows),
                       'completeParentChainApproved': 0},
            'newModelCalls': 0, 'optimizerSteps': 0, 'trainingAllowed': False, 'productHold': True}


def freeze(path, value):
    with Path(path).open('xb') as f:
        f.write((json.dumps(value, ensure_ascii=False, indent=2)+'\n').encode()); f.flush(); os.fsync(f.fileno())


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--plan',type=Path); parser.add_argument('--output',type=Path); parser.add_argument('--verify-report',type=Path);args=parser.parse_args()
    if args.verify_report:
        old=json.loads(args.verify_report.read_bytes())
        if build(old['plan'])!=old:raise ValueError('reconstruction_mismatch: C2PA evidence')
        print(json.dumps({'reconstructionOk':True,'trainingAllowed':False,'counts':old['counts']}));return
    if not args.plan or not args.output:parser.error('--plan and --output required')
    result=build(bind(args.plan));freeze(args.output,result)
    print(json.dumps({'report':bind(args.output),'metadataConsistencyOk':True,'ok':False,'counts':result['counts']}))


if __name__=='__main__':main()
