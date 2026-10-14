"""同候选全分母内部val失败归因；只读取冻结RAW及原像素真值。"""
import argparse
import importlib.util
import json
import math
from pathlib import Path
import numpy as np
from PIL import Image
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('val_outcome_data',HERE/'reviewed-role-development-data.py');d=importlib.util.module_from_spec(s);s.loader.exec_module(d)


def decode_native(logits,presence,h,w,q):
    if logits.dtype!=np.float32 or presence.dtype!=np.float32 or logits.shape!=(1,1,h,w) or presence.shape!=(1,1) or not np.isfinite(logits).all() or not np.isfinite(presence).all():raise ValueError('native finite float32 two-head domain')
    raw=logits[0,0]>=q['maskAcceptanceLogit'];accepted=bool(presence.item()>=q['presenceAcceptanceLogit'])
    return raw,accepted,raw if accepted else np.zeros((h,w),bool)


def metrics(truth,prediction,q,boundary):
    if truth.shape!=prediction.shape or truth.dtype!=bool or prediction.dtype!=bool or not truth.any():raise ValueError('same native complete positive truth')
    union=int((truth|prediction).sum());iou=int((truth&prediction).sum())/union
    stats=boundary.boundary_stats(truth,prediction,q['boundaryToleranceOriginalPixels']);ip=iou>=q['maskIou']
    return {'maskIou':iou,'boundary':stats,'iou075Passed':ip,'jointBoundaryPassed':ip and stats['boundaryIoU']>=q['boundaryIou'] and stats['boundaryF1']>=q['boundaryF1']}


def minimum_distinguishable(base_count,new_count,n,wilson):
    raw_low,raw_high=wilson(base_count,n)
    # 二项分布0次/全部成功的解析端点为0/1；另保留冻结函数的浮点值。
    low=0. if base_count==0 else raw_low;high=1. if base_count==n else raw_high;rate=base_count/n;delta=(new_count-base_count)/n
    up=max(0,math.floor(high*n)+1-base_count);down=max(0,base_count-(math.ceil(low*n)-1))
    # 仅作同分母二项诊断；不把多枚同源甲当作独立发布证据。
    minimum=None
    if delta:
        for count in range(1,1_000_001):
            # 保留观察到的基线比例；理论规划分母，不伪造新增样本。
            a,b=wilson(rate*count,count)
            if (delta>0 and new_count/n>b) or (delta<0 and new_count/n<a):minimum=count;break
    return {'baselineWilson95':[low,high],'baselineWilson95RawFrozenCalculation':[raw_low,raw_high],'analyticZeroOrOneEndpointUsed':base_count in (0,n),'observedSignedDifference':delta,'sameDenominatorMinimumDistinguishableIncreaseCount':up,'sameDenominatorMinimumDistinguishableDecreaseCount':down,'minimumSampleSizeAtObservedRatesBinomialPlanningOnly':minimum,'noFiniteSampleWhenObservedDifferenceZero':delta==0,'withinBaselineWilson95':low<=new_count/n<=high,'relativeGateDecision':'not_registered_no_branch_pass_or_fail','withinSourceCorrelationAndUpstreamHistoryPreventFormalInference':True}


def validate_scope(a,p,r):
    fixed={'purpose':'full50_same_candidate_coarse_vs_refined_and_presence_boundary_attribution_zero_inference','referenceBackend':'strict_cuda','newModelInputsAllowed':0,'optimizerStepsAllowed':0,'protectedInputsAllowed':0,'newChatImageInputsAllowed':0,'thresholdCalibrationAllowed':False,'trainingUse':'prohibited','formalSourceIndependent':False,'formalReleaseAllowed':False,'releaseIdentityRegistered':False,'productHold':True}
    if any(a.get(k)!=v for k,v in fixed.items()) or not a['decodedEqualityMustBeRebuiltFromAll4Backends'] or not a['preserveOldFailuresAndConsumed448Budget']:raise ValueError('zero-inference diagnostic/role policy')
    for key in ('candidateIdentities','counts','sourceTruthDenominator','missingTruthsPreserved','unpairedFullTruthAssets'):
        if a[key]!=p[key]:raise ValueError('full original denominator/identity '+key)
    if a['qualityContract']!=p['qualityDiagnostics'] or len(p['cases'])!=56 or p['counts']!={'candidateInputs':56,'positiveInputs':49,'rejectInputs':7}:raise ValueError('all56 exact original metric contract')
    if not r['ok'] or r['kind']!='learned' or r['internalValNumericGatePassed'] or r['summary']['wasm']['failedOrdinals']!=a['actualDiagnostic']['wasmNumericFailedOrdinals']:raise ValueError('old numeric failure remains failed')
    if any(r['summary'][b]['decodedPixelDifferences'] or r['summary'][b]['presenceFailed'] for b in ('strict_cuda','cpu','wasm','webgpu')):raise ValueError('original decoded equality')
    summary=r['qualityDiagnostics']['perBackend']['strict_cuda']['summary']
    if summary['iou075Count']!=a['actualDiagnostic']['iou075Count'] or summary['jointBoundaryCount']!=a['actualDiagnostic']['jointBoundaryCount'] or summary['nonzeroOutputRejectCount']!=a['actualDiagnostic']['nonzeroOutputRejectCount']:raise ValueError('frozen actual quality denominator')


def analyze(scope_path):
    a=d.read(d.bind(scope_path))
    for ref in list(a['inputs'].values())+list(a['sources'].values()):d.checked(ref)
    p=d.read(a['inputs']['valScope']);r=d.read(a['inputs']['valReport']);validate_scope(a,p,r)
    if a['inputs']['controlReport']!=r['controlGate'] or a['qualityContract']!=p['qualityDiagnostics'] or any(a['sources'][name]!=p['sources'][name] for name in ('dataHelper','readOnlyGuard','boundaryMetric')):raise ValueError('same original authority / metric sources')
    runner=d.load(d.checked(a['sources']['runtimeReader']),'val_outcome_runner')
    if runner.reconstruct(Path(a['inputs']['valReport']['path']).parent)!=r:raise ValueError('reconstruction_mismatch: full original val stage')
    control=d.read(a['inputs']['controlReport']);runner.require_control_gate(control)
    training_contract=d.read(p['inputs']['trainingContract']);selected=d.validate(training_contract);train=[s for s in selected if s['identity']['split']=='train']
    mat=d.read(p['inputs']['materialization']);train_cases=[s for s in mat['records'] if s['split']=='train']
    quality=d.read(training_contract['inputs']['quality']);blocked=d.unresolved_groups(d.read(training_contract['inputs']['pairDisposition']));inventory=quality['currentQualityEligibleInventory']
    supply={'trainingContract':p['inputs']['trainingContract'],'qualityInventory':training_contract['inputs']['quality'],'pairDisposition':training_contract['inputs']['pairDisposition'],'roleAuthority':training_contract['inputs']['roles'],'auditedTrainSources':len(train),'auditedTrainSourceGroups':len({s['sourceGroup'] for s in train}),'auditedTrainTruthNails':sum(s['maskCount'] for s in train),'auditedTrainCandidates':len(train_cases),'auditedTrainPositiveCandidates':sum(s['presenceTarget'] for s in train_cases),'auditedTrainRejectCandidates':sum(not s['presenceTarget'] for s in train_cases),'currentQualityEligibleSources':len(inventory),'eligibleButUnresolvedSources':sum(s['sourceGroup'] in blocked for s in inventory),'eligibleButUnresolvedTrainSources':sum(s['sourceGroup'] in blocked and s['identity']['split']=='train' for s in inventory),'currentTrainIdentities':[s['identity'] for s in train],'currentInternalValTruthNails':sum(s['maskCount'] for s in selected if s['identity']['split']=='val'),'internalValMayNotReturnToTrain':True,'formalTrainingQualificationProven':False}
    guard=d.load(d.checked(a['sources']['readOnlyGuard']),'val_outcome_guard');guard.install_read_only_ultralytics_image_check();boundary=d.load(d.checked(a['sources']['boundaryMetric']),'val_outcome_boundary');q=a['qualityContract'];records=[];views={name:[] for name in ('coarse','actual_refined','raw_refined_without_presence')};cached=r['qualityDiagnostics']['perBackend']['strict_cuda']['records']
    try:
        for c,expected in zip(p['cases'],cached,strict=True):
            arrays={}
            for name in ('nativeCoarse','nativeTarget'):
                with Image.open(d.checked(c['originalNativeAssets'][name])) as im:
                    if im.mode!='L' or im.size!=(c['w'],c['h']):raise ValueError('uint8 native L domain')
                    im.load();raw=np.asarray(im).copy()
                if raw.dtype!=np.uint8 or not set(np.unique(raw)).issubset({0,255}):raise ValueError('binary original L pixels')
                arrays[name]=raw>=128
            truth=arrays['nativeTarget'];coarse=arrays['nativeCoarse']
            if int(truth.sum())!=c['nativeTargetPixels'] or bool(truth.any())!=c['presenceTarget']:raise ValueError('full target/reject semantics')
            caps={b:r['captures'][b][c['ordinal']-1] for b in ('strict_cuda','cpu','wasm','webgpu')};decoded={};raw_masks={};accepted={}
            for backend,cap in caps.items():
                if cap['candidateIdentity']!=c['candidateIdentity'] or cap['ordinal']!=c['ordinal']:raise ValueError('same candidate allocation')
                logits=runner.tensor(cap['outputs']['mask']);presence=runner.tensor(cap['outputs']['presence'])
                raw_masks[backend],accepted[backend],decoded[backend]=decode_native(logits,presence,c['h'],c['w'],q)
            if any(not np.array_equal(mask,decoded['strict_cuda']) or accepted[b]!=accepted['strict_cuda'] for b,mask in decoded.items()):raise ValueError('full four-domain decoded reconstruction')
            masks={'coarse':coarse,'actual_refined':decoded['strict_cuda'],'raw_refined_without_presence':raw_masks['strict_cuda']};row={'ordinal':c['ordinal'],'candidateIdentity':c['candidateIdentity'],'identity':c['candidateIdentity']['identity'],'truthIndex':c['target']['truthIndex'],'sourceGroup':c['sourceGroup'],'target':c['target'],'presenceTarget':c['presenceTarget'],'cropBox':c['cropBox'],'nativeShape':[c['h'],c['w']],'truthPixels':int(truth.sum()),'presenceAccepted':accepted['strict_cuda'],'actualChangedFromCoarsePixels':int((coarse!=decoded['strict_cuda']).sum()),'rawChangedFromCoarsePixels':int((coarse!=raw_masks['strict_cuda']).sum()),'all4DecodedExactlyEqual':True,'views':{}}
            for name,prediction in masks.items():
                val={k:row[k] for k in ('ordinal','candidateIdentity','identity','truthIndex','presenceTarget','target')};val.update(presenceAccepted=accepted['strict_cuda'] if name=='actual_refined' else True,predictionPixels=int(prediction.sum()))
                if c['presenceTarget']:val.update(metrics(truth,prediction,q,boundary))
                else:
                    if not c['target']['emptyTargetIsNotNoNailsInRgbRoi'] or truth.any():raise ValueError('same candidate empty target only')
                    val.update(rejectZeroOutputPassed=not prediction.any(),emptyTargetDoesNotMeanNoNailsInRgbRoi=True)
                row['views'][name]=val;views[name].append(val)
            actual=row['views']['actual_refined']
            for key in ('identity','truthIndex','presenceTarget','presenceAccepted','predictionPixels'):
                if actual[key]!=expected[key]:raise ValueError('reconstruction_mismatch: existing actual view '+key)
            if c['presenceTarget'] and any(actual[k]!=expected[k] for k in ('maskIou','boundary','iou075Passed','jointBoundaryPassed')):raise ValueError('reconstruction_mismatch: original actual metrics')
            records.append(row)
        missing=r['qualityDiagnostics']['perBackend']['strict_cuda']['missingTruths'];summaries={name:runner.quality_summary(rows,missing,q['fullTruthDenominator'],q['sourceDenominator']) for name,rows in views.items()}
        if summaries['actual_refined']!=r['qualityDiagnostics']['perBackend']['strict_cuda']['summary']:raise ValueError('full aggregate reconstruction')
        positives=[row for row in records if row['presenceTarget']];rejects=[row for row in records if not row['presenceTarget']]
        truth_migrations=[]
        for row in positives:
            cs=row['views']['coarse'];rs=row['views']['actual_refined'];oracle=row['views']['raw_refined_without_presence']
            truth_migrations.append({'identity':row['identity'],'truthIndex':row['truthIndex'],'candidateIdentity':row['candidateIdentity'],'presenceRejected':not row['presenceAccepted'],'coarseIouPassed':cs['iou075Passed'],'refinedIouPassed':rs['iou075Passed'],'rawRefinedIouPassed':oracle['iou075Passed'],'coarseBoundaryPassed':cs['jointBoundaryPassed'],'refinedBoundaryPassed':rs['jointBoundaryPassed'],'rawRefinedBoundaryPassed':oracle['jointBoundaryPassed'],'iouDelta':rs['maskIou']-cs['maskIou'],'boundaryIouDelta':rs['boundary']['boundaryIoU']-cs['boundary']['boundaryIoU'],'boundaryF1Delta':rs['boundary']['boundaryF1']-cs['boundary']['boundaryF1']})
        for m in missing:truth_migrations.append({'identity':m['identity'],'truthIndex':m['truthIndex'],'candidateIdentity':None,'decision':m['decision'],'modelInputCreated':False,'coarseIouPassed':False,'refinedIouPassed':False,'rawRefinedIouPassed':False,'coarseBoundaryPassed':False,'refinedBoundaryPassed':False,'rawRefinedBoundaryPassed':False,'iouDelta':0.,'boundaryIouDelta':0.,'boundaryF1Delta':0.})
        if len(truth_migrations)!=50 or len({(d.key(t['identity']),t['truthIndex']) for t in truth_migrations})!=50:raise ValueError('full50 stable per-truth migration')
        attribution={'missingCandidateTruths':len(missing),'positivePresenceRejected':sum(not row['presenceAccepted'] for row in positives),'acceptedPositiveIouFailures':sum(row['presenceAccepted'] and not row['views']['actual_refined']['iou075Passed'] for row in positives),'iouPassedButBoundaryFailed':sum(row['views']['actual_refined']['iou075Passed'] and not row['views']['actual_refined']['jointBoundaryPassed'] for row in positives),'rejectNonzeroOutput':sum(row['views']['actual_refined']['predictionPixels']>0 for row in rejects),'rejectNotAutomaticallyBackgroundFalsePositive':True,'boundaryIouGatePassed':sum(row['views']['actual_refined']['boundary']['boundaryIoU']>=q['boundaryIou'] for row in positives),'boundaryF1GatePassed':sum(row['views']['actual_refined']['boundary']['boundaryF1']>=q['boundaryF1'] for row in positives),'coarseToRefinedIouRestoredTruths':[t for t in truth_migrations if not t['coarseIouPassed'] and t['refinedIouPassed']],'coarseToRefinedIouNewFailures':[t for t in truth_migrations if t['coarseIouPassed'] and not t['refinedIouPassed']],'positiveRawMaskExactlyCoarseCount':sum(row['rawChangedFromCoarsePixels']==0 for row in positives)}
        relative={metric:minimum_distinguishable(summaries['coarse'][metric],summaries['actual_refined'][metric],50,runner.wilson) for metric in ('iou075Count','jointBoundaryCount')}
        ceiling={'parityOnlyRepairPreservingStrictCudaCanImproveDecodedQuality':False,'parityOnlyJointBoundaryUpperBound':summaries['actual_refined']['jointBoundaryCount'],'parityOnlyRejectZeroUpperBound':summaries['actual_refined']['zeroOutputRejectCount'],'presenceBypassJointBoundaryCount':summaries['raw_refined_without_presence']['jointBoundaryCount'],'presenceBypassIsCounterfactualNotProductPolicy':True,'perfectPerCandidateSegmentationUpperBound':49,'fullTruthDenominator':50,'sourceIndependentFormalQualificationProven':False}
        route={'decision':'normal_stage_b_requires_train_only_supply_and_generalization_design_before_new_budget','auditedTrainSupply':supply,'priority':'conditional high resolution boundary generalization and same-candidate rejection; numerical parity cannot solve fixed CUDA quality','preserveTrainingTruthAndAll50ValDenominator':True,'modelSelectionUseOfCurrentValAllowed':False,'thresholdCalibrationAllowed':False,'newOptimizationBudgetAllocated':False,'optimizerStepsAllowedNow':0,'mustAuditWholeTrainCohortNotPickByValOrProtectedOutputs':True,'candidateInitializationAndTrainingRecipeNotChosenByThisVal':True,'nextWork':'metadata-only whole train supply/role/lineage and unresolved whole-group disposition audit; then train-only feasibility and preregister independent normal training contract','doesNotGrantFormalTrainingOrReleaseQualification':True}
        return {'schemaVersion':1,'ok':True,'decision':'full_internal_val_attribution_reconstructed_diagnostic_only','inputs':{'scope':d.bind(scope_path),'auditor':d.bind(__file__)},'records':records,'truthMigrations':truth_migrations,'missingTruthsPreserved':missing,'summaries':summaries,'attribution':attribution,'relativeDiagnostic':relative,'zeroInferenceCeilings':ceiling,'normalStageBRoute':route,'originalValNumericGatePassed':False,'wasmFailedOrdinals':r['summary']['wasm']['failedOrdinals'],'all4BackendDecodedMasksRebuilt':True,'newModelCalls':0,'optimizerSteps':0,'protectedModelInputs':0,'newChatImageInputs':0,'trainingUse':'prohibited','formalCalibrationEligible':False,'formalSourceIndependent':False,'formalReleaseAllowed':False,'productHold':True}
    finally:
        for path in training_contract['cacheCleanupRoots']:guard.remove_ultralytics_label_caches(Path(path))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--scope',type=Path,required=True);p.add_argument('--output',type=Path);p.add_argument('--verify-report',type=Path);args=p.parse_args();result=analyze(args.scope.resolve())
    if args.verify_report:
        if result!=d.read(d.bind(args.verify_report)):raise ValueError('reconstruction_mismatch: attribution report')
    elif args.output:d.new(args.output.resolve(),result)
    print(json.dumps({'ok':result['ok'],'attribution':result['attribution']|{'coarseToRefinedIouRestoredTruths':len(result['attribution']['coarseToRefinedIouRestoredTruths']),'coarseToRefinedIouNewFailures':len(result['attribution']['coarseToRefinedIouNewFailures'])},'summaries':{k:{m:v[m] for m in ('iou075Count','jointBoundaryCount','zeroOutputRejectCount','meanMaskIouFullTruth','meanBoundaryIouFullTruth','meanBoundaryF1FullTruth')} for k,v in result['summaries'].items()},'newModelCalls':0}))
