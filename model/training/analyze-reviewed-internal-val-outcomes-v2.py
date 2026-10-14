"""完整重放既有归因，修正比例端点的不可达统计；不改变旧报告。"""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('outcome_v2_data',HERE/'reviewed-role-development-data.py');d=importlib.util.module_from_spec(s);s.loader.exec_module(d)


def statistics(base_count,new_count,n,helper,wilson):
    if not isinstance(n,int) or n<=0 or not isinstance(base_count,int) or not isinstance(new_count,int) or not 0<=base_count<=n or not 0<=new_count<=n:raise ValueError('actual integer full denominator')
    r=helper(base_count,new_count,n,wilson)
    if base_count+r['sameDenominatorMinimumDistinguishableIncreaseCount']>n:r['sameDenominatorMinimumDistinguishableIncreaseCount']=None
    if base_count-r['sameDenominatorMinimumDistinguishableDecreaseCount']<0:r['sameDenominatorMinimumDistinguishableDecreaseCount']=None
    r['increaseUnreachableWithinCurrentDenominator']=r['sameDenominatorMinimumDistinguishableIncreaseCount'] is None
    r['decreaseUnreachableWithinCurrentDenominator']=r['sameDenominatorMinimumDistinguishableDecreaseCount'] is None
    r['impossibleCountsMayNotBeInterpretedAsRequiredSampleSize']=True
    return r


def analyze(scope_path,prior_report):
    old_ref=d.bind(prior_report);old=d.read(old_ref)
    if old['inputs']['scope']!=d.bind(scope_path) or not old['ok'] or old['schemaVersion']!=1 or old['decision']!='full_internal_val_attribution_reconstructed_diagnostic_only' or old['newModelCalls'] or old['formalReleaseAllowed'] or not old['productHold']:raise ValueError('complete original diagnostic scope')
    original=d.load(d.checked(old['inputs']['auditor']),'outcome_frozen_v1');rebuilt=original.analyze(scope_path)
    if rebuilt!=old:raise ValueError('reconstruction_mismatch: original full per-source/per-truth attribution')
    runner=d.load(HERE/'audit-reviewed-internal-val-native.py','outcome_v2_metric_runner')
    relative={metric:statistics(old['summaries']['coarse'][metric],old['summaries']['actual_refined'][metric],50,original.minimum_distinguishable,runner.wilson) for metric in ('iou075Count','jointBoundaryCount')}
    result=copy.deepcopy(old);result['schemaVersion']=2;result['inputs']=old['inputs']|{'auditor':d.bind(__file__),'originalAuditor':old['inputs']['auditor'],'priorReport':old_ref}
    result['priorDiagnosticStatistics']=old['relativeDiagnostic'];result['relativeDiagnostic']=relative
    result['statisticalEndpointRepair']={'oldReportAndSourcePreserved':True,'originalCoreAttributionRebuiltExactly':True,'onlyImpossibleEndpointCountsBecomeNull':True,'priorEndpointStatisticsAccepted':False,'noModelOrQualityGateChanged':True}
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--scope',type=Path,required=True);p.add_argument('--prior-report',type=Path,required=True);p.add_argument('--output',type=Path);p.add_argument('--verify-report',type=Path);args=p.parse_args();result=analyze(args.scope.resolve(),args.prior_report.resolve())
    if args.verify_report:
        if result!=d.read(d.bind(args.verify_report)):raise ValueError('reconstruction_mismatch: full corrected attribution')
    elif args.output:d.new(args.output.resolve(),result)
    print(json.dumps({'ok':result['ok'],'schemaVersion':2,'relativeDiagnostic':result['relativeDiagnostic'],'newModelCalls':0,'productHold':True}))
