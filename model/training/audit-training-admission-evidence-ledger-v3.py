"""现行准入证据/稳定分母及依赖账；只诊断缺口，绝不签发训练许可。"""
import argparse,ast,hashlib,json
from pathlib import Path

def bind(p):
 p=Path(p).resolve();return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def checked(ref):
 if bind(ref['path'])!=ref:raise ValueError('reconstruction_mismatch: '+ref['path'])
 return Path(ref['path'])
def read(ref):return json.loads(checked(ref).read_bytes())
def key(i):return tuple(i[k] for k in ('split','fileName','imageSha256'))
def unique(rows):
 ids=[key(r['identity']) for r in rows]
 if len(ids)!=len(set(ids)):raise ValueError('duplicate stable identity')
 return set(ids)
def coverage(required,observed):
 requiredIds=unique(required);observedIds=unique(observed)
 if not observedIds<=requiredIds:raise ValueError('observed cohort outside prospective qualification scope')
 byId={key(r['identity']):r for r in required}
 for r in observed:
  expected=byId[key(r['identity'])]
  if r['sourceGroup']!=expected['sourceGroup'] or r['maskCount']!=expected['maskCount'] or r['annotation']!=expected['annotation']:raise ValueError('truth/source denominator drift')
 missing=[r for r in required if key(r['identity']) not in observedIds]
 return {'requiredSources':len(required),'requiredNails':sum(r['maskCount'] for r in required),'coveredSources':len(observed),'coveredNails':sum(r['maskCount'] for r in observed),'missingSources':len(missing),'missingNails':sum(r['maskCount'] for r in missing),'missingIdentities':[r['identity'] for r in missing],'complete':not missing}
def restrict_observed_to_required(required, allRows, observed):
 # 排除资格也必须先核验原完整证据身份、来源、真值及分母，不能滤掉坏记录。
 original=coverage(allRows,observed)
 coverage(allRows,required)
 requiredIds=unique(required)
 retained=[row for row in observed if key(row['identity']) in requiredIds]
 excluded=[row for row in observed if key(row['identity']) not in requiredIds]
 return retained, {'originalProofSources':original['coveredSources'],'originalProofNails':original['coveredNails'],
  'currentEligibleProofSources':len(retained),'currentEligibleProofNails':sum(row['maskCount'] for row in retained),
  'qualificationExcludedProofSources':len(excluded),'qualificationExcludedProofNails':sum(row['maskCount'] for row in excluded),
  'qualificationExcludedIdentities':[row['identity'] for row in excluded],'originalRowsPreserved':True,'trainingAllowed':False}

def literal_gate_assignments(source):
 result={}
 for node in ast.walk(ast.parse(source)):
  if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='gates' for t in node.targets) and isinstance(node.value,ast.Dict):
   for k,v in zip(node.value.keys,node.value.values):
    if isinstance(k,ast.Constant) and isinstance(k.value,str) and isinstance(v,ast.Constant) and isinstance(v.value,bool):result[k.value]=v.value
 return result
def has_cycle(edges):
 graph={}
 for a,b in edges:graph.setdefault(a,[]).append(b);graph.setdefault(b,[])
 visited=set();active=set()
 def walk(n):
  if n in active:return True
  if n in visited:return False
  active.add(n)
  if any(walk(m) for m in graph[n]):return True
  active.remove(n);visited.add(n);return False
 return any(walk(n) for n in graph)

def validate_legacy_native_controls(group,doc):
 if not doc.get('ok') or not doc.get('nativeControlScopeOnly') or not doc.get('modelAblationInputsReady') or doc.get('trainingAllowed') or doc.get('newModelCalls',0):raise ValueError('legacy native control is not a closed zero-model input proof')
 if doc['sourceGroup']!=group['sourceGroup'] or doc['entireFrozenGroupMembership']!=group['entireFrozenGroupMembership']:raise ValueError('legacy whole group membership drift')
 expected={key(r['identity']):r for r in group['activeQualificationSources']};rows=doc['records']
 if unique(rows)!=set(expected):raise ValueError('legacy active identity coverage drift')
 for row in rows:
  if row['decision']!='pass' or not row['actuallyViewed'] or row['toolScalingNotice'] or not row['coordinateAlignmentVerified']:raise ValueError('legacy native actual review not passed')
  src=row['controlRecordPreserved']['sourcePreserved'];truth=expected[key(row['identity'])]
  for field in ('sourceImage','annotation','maskCount'):
   if src[field]!=truth[field]:raise ValueError('legacy native source truth drift')
 return list(expected.values())

def analyze(executionRef):
 e=read(executionRef);refs=e['inputs'];docs={k:read(v) for k,v in refs.items() if k not in ('runnerSource','historicalAdmissionRunner')};checked(refs['runnerSource']);historicalSource=checked(refs['historicalAdmissionRunner']).read_text(encoding='utf-8');scope=docs['scope'];index=docs['index'];historical=docs['historicalAdmission'];roi=docs['roiClosure'];geometry=docs['translatedRoi']
 if index['records']!=docs['roleIndexSnapshot']['records']:raise ValueError('role snapshot drift')
 roles={key(r['identity']):r for r in index['records']};historicalRoles={key(r['identity']):r for r in historical['roles']};valTruths={key(r['identity']):r for r in index['currentInternalValTruthRecords']};assert len(roles)==len(historicalRoles)==286
 gs=scope['groups'];allRows=[r for g in gs for r in g['activeQualificationSources']];unique(allRows)
 required=[r for g in gs if not g.get('prospectiveTrainingCandidateExcluded') for r in g['activeQualificationSources']];unique(required);tr=[r for r in required if r['identity']['split']=='train'];va=[r for r in required if r['identity']['split']=='val']
 counts={'trainSources':len(tr),'trainNails':sum(r['maskCount'] for r in tr),'internalValSources':len(va),'internalValNails':sum(r['maskCount'] for r in va),'combinedSources':len(required),'combinedNails':sum(r['maskCount'] for r in required),'groups':len({r['sourceGroup'] for r in required}),'formalTrainingApprovedSources':0}
 if counts!=scope['prospectiveCandidateCounts']:raise ValueError('scope candidate summary drift')
 if len(allRows)!=140 or sum(r['maskCount'] for r in allRows)!=819 or len(gs)!=69:raise ValueError('original audit cohort drift')
 parentRows=[]
 for r in required:
  role=roles[key(r['identity'])];old=historicalRoles[key(r['identity'])]
  if role['sourceGroup']!=r['sourceGroup'] or role['sourceImage']!=r['sourceImage'] or role['identity']['split']!=old['identity']['split'] or role['formalTrainingApproved'] or role['trainingUse']!='prohibited':raise ValueError('source role or approval drift')
  if r['identity']['split']=='train' and (role['protectedTrainConflicts'] or old['protectedTrainConflicts']):raise ValueError('protected source/parent conflict')
  if r['identity']['split']=='train':
   truth=role['currentTruth']
   if not truth or truth['annotation']!=r['annotation'] or truth['geometry']['maskCount']!=r['maskCount'] or truth['imageSize']!=r['imageSize']:raise ValueError('train truth binding drift')
  elif r['identity']['split']=='val':
   truth=valTruths.get(key(r['identity']))
   if not truth or truth['annotation']!=r['annotation'] or truth['maskCount']!=r['maskCount'] or truth['sourceGroup']!=r['sourceGroup'] or truth['trainingAllowed'] or truth['formalIndependentValAllowed']:raise ValueError('internal val truth/role drift')
  else:raise ValueError('protected split in prospective cohort')
  checked(r['sourceImage']);checked(r['annotation']);parentRows.append({'identity':r['identity'],'sourceGroup':r['sourceGroup'],'sourceImage':r['sourceImage'],'annotation':r['annotation'],'maskCount':r['maskCount'],'parents':old['parentsForCurrentQualification'],'knownRoleConflicts':old['protectedTrainConflicts'],'independenceProven':False})
 native=[r for g in gs if not g.get('prospectiveTrainingCandidateExcluded') and g.get('wholeGroupInputControlsQualified') for r in g['activeQualificationSources']];legacyResolved=[]
 for group in gs:
  if group.get('prospectiveTrainingCandidateExcluded') or group.get('wholeGroupInputControlsQualified') or not group.get('nativeControlCloseout'):continue
  ref=group['nativeControlCloseout'];doc=read(ref);resolved=validate_legacy_native_controls(group,doc)
  for row in doc['records']:
   rec=row['controlRecordPreserved'];checked(rec['reviewPage'])
   for imageRef in rec['variants'].values():checked(imageRef)
  native.extend(resolved);legacyResolved.append({'sourceGroup':group['sourceGroup'],'evidence':ref,'sources':len(resolved),'nails':sum(r['maskCount'] for r in resolved),'inheritedNativeInputOnlyNotModelApproval':True})
 nativeCoverage=coverage(required,native)
 if nativeCoverage['coveredSources']!=scope['currentCounts']['wholeGroupInputControlClosedSources'] or nativeCoverage['coveredNails']!=scope['currentCounts']['wholeGroupInputControlClosedNails']:raise ValueError('native coverage reconstruction mismatch with bound current scope')
 if not roi['ok'] or not geometry['ok'] or roi['qualifiedConditionalInputs']!=geometry['counts']['truthNails']:raise ValueError('ROI proof failed')
 observed=[]
 for r in geometry['records']:
  s=r['source'];observed.append({'identity':r['identity'],'sourceGroup':r['sourceGroup'],'maskCount':s['completeVisibleNails'],'annotation':s['annotation']})
 observed,observedScope=restrict_observed_to_required(required,allRows,observed)
 roiCoverage=coverage(required,observed);trainRoi=coverage(tr,[r for r in observed if r['identity']['split']=='train']);valRoi=coverage(va,[r for r in observed if r['identity']['split']=='val'])
 markedApproved=[r for g in gs if not g.get('prospectiveTrainingCandidateExcluded') and g.get('markerQualificationApproved') for r in g['activeQualificationSources']];markerCoverage=coverage(required,markedApproved)
 literals=literal_gate_assignments(historicalSource);names=('wholeGroupMarkerQualification','fullCohortConditionalInputQualified','sourceParentIndependenceQualified');historicalConstants={k:literals.get(k) for k in names}
 if historicalConstants!={k:False for k in names}:raise ValueError('historical runner assumptions drift')
 modelSpec=historical['contract']['markerQualification'];resolvedModelContract=docs.get('modelMarkerAcceptanceContract');contractDefined=bool(resolvedModelContract and all(k in resolvedModelContract for k in ('modelIdentity','modelComponent','acceptanceRules','wholeGroupCoverage','replayVerifier')))
 gates={names[0]:{'state':'unresolved_model_contract' if not contractDefined else 'evidence_missing' if not markerCoverage['complete'] else 'coverage_ready_approval_not_evaluated','coverage':markerCoverage,'acceptanceContractDefined':contractDefined,'historicalContractText':modelSpec,'legacyDiagnosticDoesNotGrantApproval':True},names[1]:{'state':'full_cohort_evidence_missing' if not roiCoverage['complete'] else 'coverage_ready_approval_not_evaluated','coverage':roiCoverage},names[2]:{'state':'full_source_parent_near_duplicate_visual_evidence_missing','requiredSources':len(required),'sourceRecordsWithVerifiedExplicitParents':sum(bool(r['parents']) for r in parentRows),'sourceParentIndependenceApprovalEvidenceAvailable':False,'knownRoleConflictsZeroIsNotIndependenceProof':True}}
 edges=[['role_truth_verification','native_controls_full_cohort'],['native_controls_full_cohort','frozen_stage_a_diagnostics'],['frozen_stage_a_diagnostics','full_cohort_conditional_inputs'],['source_parent_inventory','near_duplicate_recall'],['near_duplicate_recall','native_pair_adjudication'],['native_pair_adjudication','source_parent_independence'],['model_marker_acceptance_contract','whole_group_marker_approval'],['native_controls_full_cohort','whole_group_marker_approval'],['whole_group_marker_approval','training_admission'],['full_cohort_conditional_inputs','training_admission'],['source_parent_independence','training_admission'],['training_admission','train_only_reachability_capacity'],['train_only_reachability_capacity','full30_training'],['full30_training','trained_candidate_release_quality']]
 return {'schemaVersion':1,'execution':executionRef,'inputs':refs,'metadataConsistencyOk':True,'ok':False,'decision':'current_admission_hold_three_gates_evidence_or_contract_missing','approvalAuthority':'none_dependency_evidence_ledger_not_training_permission_evaluator','currentCandidateCounts':counts,'historicalUnmodifiedCounts':historical['counts'],'originalCohortPreserved':{'sources':140,'nails':819,'groups':69},'nativeInputControls':nativeCoverage,'legacyNativeCoverageResolved':legacyResolved,'conditionalInputs':roiCoverage,'conditionalProofQualificationScope':observedScope,'trainConditionalInputs':trainRoi,'internalValConditionalInputs':valRoi,'gates':gates,'historicalLiteralFalseGateAssignments':historicalConstants,'dependencyEdges':edges,'cycleAssessment':{'provenCycleInBoundExecutablePath':has_cycle(edges),'intendedWorkflowAssessment':'unresolved_without_model_contract' if not contractDefined else 'declared_contract_requires_executable_dependency_verification','reason':'next_model_identity_component_and_acceptance_rules_not_bound; cannot equate pretraining input checks with posttraining release quality'},'sourceParentQualificationInventory':parentRows,'nextExecutableStep':'freeze_full111_candidate_and_parent_reference_inventory_and_preregister_near_duplicate_recall_with_positive_controls_and_native_adjudication; resolve_marker_model_contract_without_lowering_gates','trainingAllowed':False,'formalTrainingApprovedImages':0,'full30PilotAllowed':False,'newModelCalls':0,'optimizerSteps':0,'productHold':True}

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--execution',type=Path);ap.add_argument('--output',type=Path);ap.add_argument('--verify-report',type=Path);a=ap.parse_args()
 if a.verify_report:
  old=json.loads(a.verify_report.read_bytes());r=analyze(old['execution'])
  if r!=old:raise ValueError('reconstruction_mismatch: evidence ledger')
  print(json.dumps({'reconstructionOk':True,'trainingAllowed':False,'decision':r['decision']}));return
 if not a.execution or not a.output:ap.error('--execution and --output required')
 r=analyze(bind(a.execution))
 with a.output.open('xb') as f:f.write((json.dumps(r,ensure_ascii=False,indent=2)+'\n').encode())
 print(json.dumps({'report':bind(a.output),'metadataConsistencyOk':r['metadataConsistencyOk'],'trainingAdmissionOk':r['ok'],'counts':r['currentCandidateCounts'],'nativeCoverage':{k:v for k,v in r['nativeInputControls'].items() if k!='missingIdentities'},'roiCoverage':{k:v for k,v in r['conditionalInputs'].items() if k!='missingIdentities'},'cycleAssessment':r['cycleAssessment']},ensure_ascii=False))
if __name__=='__main__':main()
