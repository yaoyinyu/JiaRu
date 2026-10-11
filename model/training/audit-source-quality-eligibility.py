"""源质量资格投影：先验证完整旧候选，再排除实看失败源，绝不签发训练许可。"""
import argparse, hashlib, json, os
from pathlib import Path

def bind(p):
 p=Path(p).resolve()
 if not p.is_file(): raise ValueError('missing binding')
 return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def read(ref):
 if bind(ref['path'])!=ref: raise ValueError('reconstruction_mismatch: binding')
 return json.loads(Path(ref['path']).read_bytes())
def key(row): return tuple(row['identity'][k] for k in ('split','fileName','imageSha256'))
def counts(rows):
 tr=[x for x in rows if x['identity']['split']=='train']; va=[x for x in rows if x['identity']['split']=='val']
 return {'trainSources':len(tr),'trainNails':sum(x['maskCount'] for x in tr),'internalValSources':len(va),'internalValNails':sum(x['maskCount'] for x in va),'combinedSources':len(rows),'combinedNails':sum(x['maskCount'] for x in rows),'groups':len({x['sourceGroup'] for x in rows}),'formalTrainingApprovedSources':0}
def project_coverage(old, original, retained):
 by={key(x):x for x in original}; missing={tuple(x[k] for k in ('split','fileName','imageSha256')) for x in old['missingIdentities']}
 if len(missing)!=len(old['missingIdentities']) or not missing<=set(by):raise ValueError('coverage missing identity mismatch')
 covered=[x for x in original if key(x) not in missing]
 expected={'requiredSources':len(original),'requiredNails':sum(x['maskCount'] for x in original),'coveredSources':len(covered),'coveredNails':sum(x['maskCount'] for x in covered),'missingSources':len(missing),'missingNails':sum(by[k]['maskCount'] for k in missing),'complete':not missing}
 if any(old[k]!=v for k,v in expected.items()): raise ValueError('coverage counter mismatch')
 cov=[x for x in retained if key(x) not in missing]; miss=[x for x in retained if key(x) in missing]
 return {'requiredSources':len(retained),'requiredNails':sum(x['maskCount'] for x in retained),'coveredSources':len(cov),'coveredNails':sum(x['maskCount'] for x in cov),'missingSources':len(miss),'missingNails':sum(x['maskCount'] for x in miss),'missingIdentities':[x['identity'] for x in miss],'complete':not miss,'oldCompleteDenominatorVerifiedBeforeProjection':True,'noNewProofAdded':True}
def analyze(plan_ref):
 plan=read(plan_ref); refs=plan['inputs']; ledger=read(refs['priorLedger']); readiness=read(refs['readiness']); roles=read(refs['roles'])
 original=ledger['sourceParentQualificationInventory']; by={key(x):x for x in original}; rb={key(x):x for x in readiness['records']}; roleby={key(x):x for x in roles['records']}
 if len(by)!=len(original) or set(by)!=set(rb) or counts(original)!=ledger['currentCandidateCounts']: raise ValueError('original full cohort mismatch')
 for k,x in by.items():
  r=rb[k]; role=roleby[k]
  if x['sourceImage']!=r['source'] or x['annotation']!=r['annotation'] or x['maskCount']!=r['maskCount'] or x['sourceGroup']!=r['sourceGroup']:raise ValueError('original truth drift')
  if bind(x['sourceImage']['path'])!=x['sourceImage'] or bind(x['annotation']['path'])!=x['annotation']:raise ValueError('original bytes drift')
  if x['sourceGroup']!=role['sourceGroup'] or x['identity']['split'] not in ('train','val') or role['trainingUse']!='prohibited' or role['formalTrainingApproved']:raise ValueError('role or authorization drift')
 reviews=[read(ref) for ref in plan['qualityReviews']]; reviewby={key(x):x for x in reviews}
 if len(reviewby)!=len(reviews) or not set(reviewby)<=set(by):raise ValueError('quality identity mismatch')
 for k,x in reviewby.items():
  originalrow=by[k]; role=roleby[k]
  if not x['actuallyViewed'] or x['toolScalingNotice'] or not x['nativePixelCoverageComplete'] or not x['noResamplingOrReencoding']:raise ValueError('missing native visual evidence')
  if x['annotation']!=originalrow['annotation'] or x['sourceGroup']!=originalrow['sourceGroup'] or x['maskCountPreserved']!=originalrow['maskCount'] or x['wholeSourcePage']['page']!=originalrow['sourceImage']:raise ValueError('quality source binding mismatch')
  digest=hashlib.sha256(json.dumps(role,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
  if x['currentRoleRecordSha256Preserved']!=digest or x['trainingAllowed'] or x['trainingUse']!='prohibited':raise ValueError('quality role drift')
  if x['decision'] not in ('source_quality_excluded','source_quality_candidate'):raise ValueError('unknown source quality decision')
 excluded=[x for x in original if key(x) in reviewby and reviewby[key(x)]['decision']=='source_quality_excluded']; retained=[x for x in original if key(x) not in {key(z) for z in excluded}]
 ordered=sorted([x for x in readiness['records'] if key(x) in {key(z) for z in retained} and key(x) not in reviewby],key=lambda x:(x['minimumNativeNailShortSidePixels'],x['minimumNativeNailAreaPixels'],x['identity']['split'],x['identity']['fileName'],x['identity']['imageSha256']))
 coverage={k:project_coverage(ledger[k],original,retained) for k in ['nativeInputControls','conditionalInputs']}
 return {'schemaVersion':1,'ok':True,'decision':'source_quality_projection_only_training_still_prohibited','plan':plan_ref,'inputs':refs,'qualityReviewBindings':plan['qualityReviews'],'originalCandidateCountsPreserved':counts(original),'originalCandidateInventoryPreserved':original,'excludedFromFutureTraining':excluded,'currentQualityEligibleCounts':counts(retained),'currentQualityEligibleInventory':retained,'sourceQualityReviewedSources':len(reviews),'sourceQualityRetainedSources':sum(x['decision']=='source_quality_candidate' for x in reviews),'sourceQualityRemainingSources':len(ordered),'currentCoverageProjection':coverage,'coverageNamesNotReversed':True,'sourceParentIndependenceQualified':False,'wholeGroupMarkerQualification':False,'fullCohortConditionalInputQualified':False,'currentContractMustBindNewEligibilityBeforeTraining':True,'oldContractAndFailedQualityDenominatorsNotRewritten':True,'rolesTruthsAndSourceGroupMembershipUnmodified':True,'nextQualityBatch':[{'identity':x['identity'],'source':x['source'],'sourceGroup':x['sourceGroup'],'maskCount':x['maskCount'],'priorActualView':x['exactPriorNativeView']} for x in ordered[:3]],'actualModelImageInputs':sum(x['actualModelImageInputs'] for x in reviews),'actualEncodedImageBytes':sum(x['actualToolEncodedImageBytes'] for x in reviews),'newUniqueStockImages':0,'newUniqueStockPages':0,'trainingAllowed':False,'formalTrainingApprovedImages':0,'full30Allowed':False,'productHold':True}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--plan',type=Path);ap.add_argument('--output',type=Path);ap.add_argument('--verify-report',type=Path);args=ap.parse_args()
 if args.verify_report:
  old=json.loads(args.verify_report.read_bytes());current=analyze(old['plan'])
  if current!=old:raise ValueError('reconstruction_mismatch: source quality eligibility')
 else:
  if not args.plan or not args.output:ap.error('--plan and --output required')
  current=analyze(bind(args.plan))
  with args.output.open('xb') as f:f.write((json.dumps(current,ensure_ascii=False,indent=2)+'\n').encode());f.flush();os.fsync(f.fileno())
 print(json.dumps({'ok':True,'counts':current['currentQualityEligibleCounts'],'coverage':{k:{z:y for z,y in x.items() if z!='missingIdentities'} for k,x in current['currentCoverageProjection'].items()},'remainingSourceQuality':current['sourceQualityRemainingSources'],'trainingAllowed':False},ensure_ascii=False))
if __name__=='__main__':main()
