"""固定FP32特征的线性可分性数学证书；精确有理数验真，不产生候选权重。"""
import argparse
from fractions import Fraction
import importlib.util
import json
from pathlib import Path
import numpy as np
import scipy
from scipy.optimize import linprog
HERE=Path(__file__).resolve().parent
def load(path,name):
    sp=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);return m
d=load(HERE/'reviewed-role-development-data.py','linear_certificate_data')
require=load(HERE/'train-reviewed-stage-b-normal-development.py','linear_certificate_require').require
CONTRACT={'domain':'exact_rationals_lifting_stored_float32_features_and_binary64_witness','bias':True,
    'labels':'positive_plus1_same_candidate_reject_minus1','requiredSignedMargin':1,
    'primal':'one_zero_objective_feasibility_solve_unbounded_coefficients_y_times_augmented_features_dot_w_ge1',
    'solver':'scipy.optimize.linprog_highs','solverOptions':{'primal_feasibility_tolerance':1e-9,'dual_feasibility_tolerance':1e-9,'maxiter':100000},
    'fixedWitnessScale':2,'exactCertificate':'all_signed_margins_ge1_without_tolerance',
    'infeasibleCertificate':'exact_opposite_label_duplicate_feature_pair_only_else_inconclusive',
    'runtimeFp32OrBrowserQualityClaimAllowed':False,'candidateWeightMaterializationAllowed':False}

def exact_margins(features,positive,witness):
    require(features.dtype==np.float32 and features.ndim==2 and np.isfinite(features).all(),'stored feature domain')
    flags=np.asarray(positive);w=np.asarray(witness)
    require(flags.dtype==bool and flags.shape==(len(features),) and w.dtype==np.float64 and w.shape==(features.shape[1]+1,) and np.isfinite(w).all(),'label/witness domain')
    coefficients=[Fraction.from_float(float(x)) for x in w]
    return [(1 if flag else -1)*(sum((Fraction.from_float(float(x))*a for x,a in zip(row,coefficients[:-1],strict=True)),coefficients[-1])) for row,flag in zip(features,flags,strict=True)]

def certify(features,positive):
    flags=np.asarray(positive)
    require(features.dtype==np.float32 and features.ndim==2 and len(features)>1 and np.isfinite(features).all() and flags.dtype==bool and flags.shape==(len(features),) and flags.any() and (~flags).any(),'full feature and two-class domain')
    labels=np.where(flags,1.,-1.);augmented=np.column_stack([features.astype(np.float64),np.ones(len(features))])
    result=linprog(np.zeros(augmented.shape[1]),A_ub=-labels[:,None]*augmented,b_ub=-np.ones(len(features)),
        bounds=[(None,None)]*augmented.shape[1],method='highs',options=CONTRACT['solverOptions'])
    common={'solverStatus':int(result.status),'solverMessage':str(result.message),'solverSuccess':bool(result.success),
        'primalSolves':1,'candidateInputs':len(features),'positiveInputs':int(flags.sum()),'rejectInputs':int((~flags).sum()),
        'mathematicalCertificateOnly':True,'runtimeQualityProven':False,'candidateWeightsWritten':False}
    if result.success:
        witness=np.asarray(result.x,dtype=np.float64)*2.;margins=exact_margins(features,flags,witness)
        passed=all(x>=1 for x in margins);minimum=min(margins)
        return {**common,'decision':'exact_linear_separability_certified' if passed else 'inconclusive_primal_exact_certificate_failed',
            'exactFeasible':passed,'exactInfeasible':False,'coefficientWitnessBinary64':witness.tolist(),
            'coefficientWitnessUse':'mathematical_certificate_only_never_load_as_model',
            'exactSignedMargins':[str(x) for x in margins],'minimumExactSignedMargin':str(minimum),
            'minimumSignedMarginApproximate':float(minimum),'allExactSignedMarginsAtLeastOne':passed}
    if result.status==2:
        for i in range(len(features)):
            for j in range(i):
                if flags[i]!=flags[j] and np.array_equal(features[i],features[j]):
                    return {**common,'decision':'exact_linear_infeasibility_certified_by_opposite_duplicate',
                        'exactFeasible':False,'exactInfeasible':True,'dualPairIndices':[j,i],
                        'dualCoefficients':['1/2','1/2'],'dualSumOne':True,'dualSignedAugmentedFeatureSumExactlyZero':True}
    return {**common,'decision':'inconclusive_solver_no_exact_certificate','exactFeasible':False,'exactInfeasible':False}

def verify_certificate(features,positive,saved):
    flags=np.asarray(positive)
    require(saved['candidateInputs']==len(features) and saved['positiveInputs']==int(flags.sum()) and saved['rejectInputs']==int((~flags).sum()),'certificate full label denominator')
    if saved['decision'] in ('exact_linear_separability_certified','inconclusive_primal_exact_certificate_failed'):
        margins=exact_margins(features,flags,np.asarray(saved['coefficientWitnessBinary64'],np.float64));passed=all(x>=1 for x in margins)
        require(saved['decision']==('exact_linear_separability_certified' if passed else 'inconclusive_primal_exact_certificate_failed'),'exact decision matches margins')
        require(saved['solverSuccess'] and saved['solverStatus']==0 and saved['exactFeasible']==passed and saved['exactInfeasible'] is False,'primal certificate decision')
        require(saved['exactSignedMargins']==[str(x) for x in margins] and saved['minimumExactSignedMargin']==str(min(margins)) and saved['minimumSignedMarginApproximate']==float(min(margins)) and saved['allExactSignedMarginsAtLeastOne']==passed,'exact rational full margins')
    elif saved['decision']=='exact_linear_infeasibility_certified_by_opposite_duplicate':
        i,j=saved['dualPairIndices'];require(0<=i<j<len(features) and flags[i]!=flags[j] and np.array_equal(features[i],features[j]),'exact opposing duplicate certificate')
        require(saved['dualCoefficients']==['1/2','1/2'] and saved['exactInfeasible'] and not saved['exactFeasible'] and saved['dualSumOne'] and saved['dualSignedAugmentedFeatureSumExactlyZero'],'dual certificate')
    else:
        require(saved['decision']=='inconclusive_solver_no_exact_certificate' and not saved['exactFeasible'] and not saved['exactInfeasible'],'no unsupported infeasibility claim')
    require(saved['primalSolves']==1 and saved['mathematicalCertificateOnly'] and not saved['runtimeQualityProven'] and not saved['candidateWeightsWritten'],'certificate diagnostic semantics')
    return saved

def analyze(execution_ref,capture_path,stored_certificate=None):
    e=d.read(execution_ref)
    for bound in [*e['inputs'].values(),*e['sources'].values()]:d.checked(bound)
    require(e['purpose']=='fixed_all_train_features_exact_linear_separability_only' and e['mathematics']==CONTRACT,'registered exact mathematical contract')
    require(d.checked(e['sources']['runner'])==Path(__file__).resolve(),'certificate runner identity')
    require(e['budget']=={'maximumAttempts':1,'primalSolves':1,'newModelInputs':0,'optimizerSteps':0,'headTrainingSteps':0,'candidateWeights':0},'certificate budget')
    require(e['solverEnvironment']=={'scipy':scipy.__version__,'numpy':np.__version__},'frozen mathematical runtime')
    capture=load(d.checked(e['sources']['captureRunner']),'certificate_capture_reader');proof=capture.verify(capture_path)
    saved=d.read(d.bind(capture_path));require(saved['execution']==e['inputs']['captureExecution'],'same fixed capture contract')
    scope=d.read(e['inputs']['scope']);require([r['candidateIdentity'] for r in saved['records']]==scope['candidateIdentities']==e['candidateIdentities'],'all original candidates')
    values=[]
    for record in saved['records']:
        with np.load(d.checked(record['capture']),allow_pickle=False) as archive:values.append(archive['features'][0].copy())
    matrix=np.stack(values);flags=np.asarray([r['positive'] for r in saved['records']],bool)
    require(matrix.shape==(74,128) and int(flags.sum())==71 and int((~flags).sum())==3,'entire 71 truths 3 rejects')
    require(capture.sha(matrix)==proof['featureMatrixSha256'],'exact full feature matrix reconstruction')
    result=certify(matrix,flags) if stored_certificate is None else verify_certificate(matrix,flags,stored_certificate)
    return {'schemaVersion':1,'ok':True,'execution':execution_ref,'captureReplay':proof,'solverEnvironment':{'scipy':scipy.__version__,'numpy':np.__version__},
        'mathematics':CONTRACT,'certificate':result,'candidateIdentities':e['candidateIdentities'],
        'allOldQualityFailuresAndBudgetsPreserved':True,'newModelCalls':0,'optimizerSteps':0,'newChatImageInputs':0,
        'headTrainingOrCandidateWeightsAllowed':False,'formalReleaseAllowed':False,'productHold':True}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execution',type=Path);p.add_argument('--capture',type=Path);p.add_argument('--output',type=Path);p.add_argument('--verify-report',type=Path);a=p.parse_args()
    if a.verify_report:
        saved=d.read(d.bind(a.verify_report));result=analyze(saved['execution'],Path(saved['captureReplay']['capture']['path']),saved['certificate']);require(a.verify_report.read_bytes()==d.raw(result),'full exact certificate report bytes')
    else:
        root=a.output.resolve().parent;root.mkdir(parents=True,exist_ok=False)
        d.new(root/'attempt.json',{'execution':d.bind(a.execution),'capture':d.bind(a.capture),'attemptConsumed':True,'restartAllowed':False})
        try:
            result=analyze(d.bind(a.execution),a.capture.resolve());d.new(a.output.resolve(),result)
        except BaseException as error:
            d.new(root/'failure.json',{'error':str(error),'restartAllowed':False,'conclusionsAllowed':False,'newModelCalls':0,'optimizerSteps':0})
            raise
    print(json.dumps({'ok':result['ok'],'decision':result['certificate']['decision'],'minimumSignedMarginApproximate':result['certificate'].get('minimumSignedMarginApproximate'),'candidateInputs':74,'newModelCalls':0},ensure_ascii=False))
