"""只读重建完整内部val原像素输入、角色与全真值分母；不运行模型。"""
import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
import numpy as np
from PIL import Image
HERE=Path(__file__).resolve().parent
if str(HERE) not in sys.path:sys.path.insert(0,str(HERE))
s=importlib.util.spec_from_file_location('val_inputs_data',HERE/'reviewed-role-development-data.py');d=importlib.util.module_from_spec(s);s.loader.exec_module(d)


def verify(scope_path):
    p=d.read(d.bind(scope_path))
    fixed={'purpose':'complete_internal_val_native_diagnostic_only_all56_candidates_full50_truths','newStrictCudaInputsAllowed':112,'newOnnxFullModelInputsAllowed':336,'newFullModelInputsAllowed':448,'optimizerStepsAllowed':0,'newStageAInputsAllowed':0,'protectedInputsAllowed':0,'newChatImageInputsAllowed':0,'formalCalibrationEligible':False,'formalSourceIndependent':False,'thresholdCalibrationAllowed':False,'trainingUse':'prohibited','formalReleaseAllowed':False,'productHold':True}
    if any(p.get(k)!=v for k,v in fixed.items()):raise ValueError('fixed internal diagnostic / roles / budgets')
    for k in ('all50TruthsMustRemainInQualityDenominator','noCandidateMayNotBecomeModelInput','sameCandidateRejectNotEmptyRgb','internalValHasUpstreamTrainingHistory','all224ControlTorchAndOnnxMustPassBeforeLearnedStage'):
        if p[k] is not True:raise ValueError('required denominator/role guard '+k)
    for ref in list(p['inputs'].values())+list(p['sources'].values())+list(p['weights'].values())+list(p['models'].values()):d.checked(ref)
    material=d.read(p['inputs']['materialization']);contract=d.read(p['inputs']['trainingContract']);sources=d.validate(contract);source_map={d.key(row['identity']):row for row in sources};rows=[r for r in material['records'] if r['split']=='val']
    if material['counts']['val']!=p['counts'] or p['counts']!={'candidateInputs':56,'positiveInputs':49,'rejectInputs':7} or p['sourceTruthDenominator']!=material['sourceTruthDenominator'] or p['missingTruthsPreserved']!=material['missingTruthsPreserved'] or p['unpairedFullTruthAssets']!=material['unpairedFullTruthAssets']:raise ValueError('complete authoritative val denominator')
    if len(rows)!=56 or len(p['cases'])!=56 or [c['ordinal'] for c in p['cases']]!=list(range(1,57)) or [c['candidateIdentity'] for c in p['cases']]!=p['candidateIdentities']:raise ValueError('full ordered56 contexts')
    if p['newStrictCudaInputsAllowedByStage']!={'control':56,'learned':56} or p['newOnnxInputsAllowedByStageAndBackend']!={k:{b:56 for b in ('cpu','wasm','webgpu')} for k in ('control','learned')}:raise ValueError('full stage/backend budgets')
    if p['requiredNumericDifference']!=1e-4 or p['requiredDecodedPixelDifferences']!=0 or p['requiredPresenceDecisionDifferences']!=0 or p['qualityDiagnostics']!={'maskIou':.75,'boundaryIou':.75,'boundaryF1':.9,'boundaryToleranceOriginalPixels':2,'fullTruthDenominator':50,'candidatePositiveDenominator':49,'candidateRejectDenominator':7,'sourceDenominator':10,'presenceAcceptanceLogit':0.,'maskAcceptanceLogit':0.,'notFormalReleaseQualityApproval':True}:raise ValueError('original quality / storage/threshold domain')
    guard=d.load(d.checked(p['sources']['readOnlyGuard']),'val_inputs_guard');guard.install_read_only_ultralytics_image_check();ids=[];positive=0;reject=0;files=[]
    try:
        for c,old in zip(p['cases'],rows,strict=True):
            ci=c['candidateIdentity'];source=source_map[d.key(ci['identity'])]
            if c['materializationOrdinal']!=old['ordinal'] or ci!=old['candidateIdentity'] or ci['identity']['split']!='val' or c['trainingUse']!='prohibited' or c['target']!=old['target'] or c['presenceTarget']!=old['presenceTarget'] or c['nativeTargetPixels']!=old['nativeTargetPixels'] or c['cropBox']!=old['cropBox'] or c['originalNativeAssets']!=old['paths'] or c['sourceImage']!=source['sourceImage'] or c['annotation']!=source['annotation'] or c['sourceGroup']!=source['sourceGroup']:raise ValueError('same candidate/source/target/role')
            arrays={}
            for name,mode in (('nativeRgb','RGB'),('nativeCoarse','L'),('nativeTarget','L')):
                with Image.open(d.checked(c['originalNativeAssets'][name])) as im:
                    if im.mode!=mode:raise ValueError('original image storage')
                    im.load();arrays[name]=np.asarray(im).copy()
            rgb=arrays['nativeRgb'];coarse=arrays['nativeCoarse'];truth=arrays['nativeTarget'];h,w=c['h'],c['w']
            if old['nativeSize']!=[w,h] or rgb.shape!=(h,w,3) or coarse.shape!=truth.shape or coarse.shape!=(h,w) or any(a.dtype!=np.uint8 for a in arrays.values()) or any(not set(np.unique(a)).issubset({0,255}) for a in (coarse,truth)):raise ValueError('native sizes/uint8 domains')
            for a,key in ((rgb,'rgbNativeBytesSha256'),(coarse,'coarseNativeBytesSha256'),(truth,'targetNativeBytesSha256')):
                if hashlib.sha256(a.tobytes()).hexdigest()!=old[key]:raise ValueError('all native pixels')
            normalized=((rgb.astype(np.float64)/255-np.array([.485,.456,.406]))/np.array([.229,.224,.225])).transpose(2,0,1).astype(np.float32);expected=np.concatenate([normalized,(coarse.astype(np.float32)/255)[None]],axis=0)[None]
            path=d.checked({k:c['input'][k] for k in ('path','sha256')});ratio_path=d.checked({k:c['resizeRatios'][k] for k in ('path','sha256')})
            vector=np.array([np.float32(a)/np.float32(b) for a,b in ((h//4,h//2),(w//4,w//2),(h//2,h),(w//2,w))],np.float32)
            if c['input']['dtype']!='float32' or c['input']['shape']!=[1,4,h,w] or path.read_bytes()!=expected.astype('<f4',copy=False).tobytes() or c['resizeRatios']['dtype']!='float32' or c['resizeRatios']['shape']!=[4] or ratio_path.read_bytes()!=vector.astype('<f4',copy=False).tobytes():raise ValueError('raw normalizer and ratio byte reconstruction')
            if bool(truth.any())!=c['presenceTarget'] or int((truth>=128).sum())!=c['nativeTargetPixels'] or old['sourceTruthPixelsLost']!=0:raise ValueError('complete target/reject semantics')
            ids.append(d.key(ci['identity']));positive+=c['presenceTarget'];reject+=not c['presenceTarget'];files.extend([d.bind(path),d.bind(ratio_path)])
        if len(set(ids))!=10 or positive!=49 or reject!=7 or len(p['missingTruthsPreserved'])!=1 or len(p['unpairedFullTruthAssets'])!=1:raise ValueError('all10 source /49 positive /7 reject /1 missing')
        item=p['unpairedFullTruthAssets'][0];missing=p['missingTruthsPreserved'][0]
        if item['identity']!=missing['identity'] or item['truthIndex']!=missing['truthIndex'] or item['inferenceUse']!='prohibited_gt_only_no_candidate' or item['trainingUse']!='prohibited':raise ValueError('unpaired truth not model input')
        with Image.open(d.checked(item['fullNativeTruth'])) as im:im.load();truth=np.asarray(im).copy()
        if int((truth>=128).sum())!=item['truthPixels']:raise ValueError('missing full truth pixels')
        return {'schemaVersion':1,'ok':True,'scope':d.bind(scope_path),'verifier':d.bind(__file__),'candidateCount':56,'positiveCount':positive,'rejectCount':reject,'sourceCount':len(set(ids)),'fullTruthCount':50,'missingTruthCount':1,'rawFiles':files,'allInputAndRatioBytesReconstructed':True,'sourceRolesPreserved':True,'newModelCalls':0,'optimizerSteps':0,'formalCalibrationEligible':False,'formalReleaseAllowed':False,'productHold':True}
    finally:
        for path in contract['cacheCleanupRoots']:guard.remove_ultralytics_label_caches(Path(path))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--scope',type=Path,required=True);p.add_argument('--output',type=Path);p.add_argument('--verify-report',type=Path);a=p.parse_args();result=verify(a.scope.resolve())
    if a.verify_report:
        if result!=d.read(d.bind(a.verify_report)):raise ValueError('val input report reconstruction_mismatch')
    elif a.output:d.new(a.output.resolve(),result)
    print(json.dumps({k:result[k] for k in ('ok','candidateCount','sourceCount','fullTruthCount','missingTruthCount','newModelCalls')}))
