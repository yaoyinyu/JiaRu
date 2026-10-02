"""全45固定最终权重输出保真及共享梯度诊断，零优化、不选阈值。"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import numpy as np
import torch


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


t=module('terminal_gradient_capacity',Path(__file__).with_name('train-native-band-objective-microfit.py'))
a=t.a
stats=module('terminal_gradient_statistics',Path(__file__).with_name('native-gradient-statistics.py'))


def validate(plan):
    for binding in plan['inputs'].values():
        a.checked(binding)
    scope=a.read(a.checked(plan['inputs']['scope']))
    for binding in scope['inputs'].values():
        a.checked(binding)
    if plan['maximumHeadForwards']!=45 or plan['maximumBackwards']!=45 or plan['optimizerSteps']!=0 or plan['additionalQualityForwards']!=0:
        raise ValueError('fixed all45 zero optimization budget')
    if scope['reachability']['witnessJointCount']<scope['reachability']['requiredCount']:
        raise ValueError('unreachable')
    for key,path in [('runnerSource',Path(__file__)),('statisticsSource',Path(stats.__file__))]:
        if plan['inputs'][key]!=a.bind(path):
            raise ValueError('executed source not bound: '+key)
    report_path=a.checked(scope['inputs']['capacityReport'])
    replay=t.verify(report_path)
    capacity=a.read(report_path)
    frozen=a.read(a.checked(scope['inputs']['capacityPlan']))
    _,parent,records=t.validate(frozen)
    if capacity['decision']!='native_capacity_fail_no_full30' or capacity['metrics']!=replay['metrics'] or scope['candidateIds']!=parent['candidateIds'] or scope['qualityGatesUnchanged']!=frozen['gates']:
        raise ValueError('frozen quality failure/identities/gates')
    if scope['inputs']['finalWeights']!=capacity['finalWeights'] or scope['inputs']['finalDeltas']!=capacity['finalDeltas']:
        raise ValueError('final artifact identity')
    return scope,capacity,frozen,parent,records


def load_data(scope,parent,records):
    h,data=t.s.native_data(parent,records)
    with np.load(a.checked(scope['inputs']['finalDeltas']),allow_pickle=False) as saved:
        if saved['candidateIds'].tolist()!=scope['candidateIds']:
            raise ValueError('reconstruction_mismatch: saved identities')
        deltas=[saved[f'delta_{i:03d}'].copy() for i in range(45)]
    return h,data,deltas


def audit(plan_path,output):
    plan=a.read(plan_path)
    scope,capacity,frozen,parent,records=validate(plan)
    if output.exists():
        raise FileExistsError('single diagnostic budget already claimed; no restart')
    output.mkdir(parents=True)
    t.j.write_durable_new(output/'claim.json',{'plan':a.bind(plan_path),'attemptConsumed':True,'restartAllowed':False,'maximumHeadForwards':45})
    completed=[]
    calls=0
    try:
        h,data,expected=load_data(scope,parent,records)
        torch.set_num_threads(2)
        torch.backends.cuda.matmul.allow_tf32=False
        torch.backends.cudnn.allow_tf32=False
        torch.backends.cudnn.deterministic=True
        torch.backends.cudnn.benchmark=False
        head=h.NativeBoundaryNailRefiner().cuda().eval()
        state=torch.load(a.checked(scope['inputs']['finalWeights']),map_location='cpu',weights_only=True)
        head.load_state_dict(state,strict=True)
        head.requires_grad_(True)
        parameter_names=[name for name,_ in head.named_parameters()]
        if sum(param.numel() for param in head.parameters())!=20385:
            raise ValueError('fixed parameter count')
        loss_model=module('terminal_gradient_loss',a.checked(scope['inputs']['lossSource']))
        vectors=[]
        actual_deltas=[]
        torch.cuda.reset_peak_memory_stats()
        for item,reference in zip(data,expected,strict=True):
            head.zero_grad(set_to_none=True)
            packed=torch.from_numpy(item['packed'][None].copy()).cuda()
            base=torch.from_numpy(item['base'][None,None].copy()).cuda()
            target=torch.from_numpy(item['target'][None,None].copy()).cuda()
            band=torch.from_numpy(item['band'][None,None].copy()).cuda()
            calls+=1
            delta=head(packed)
            delta.retain_grad()
            actual=delta.detach().cpu().numpy()[0,0].copy()
            if actual.shape!=reference.shape or not np.isfinite(actual).all() or not np.array_equal(actual,reference):
                raise ValueError('reconstruction_mismatch: final delta must match saved float32 values exactly')
            actual_deltas.append(actual)
            logits=h.compose_native_logits(base,delta,band)
            loss,components=loss_model.conditional_mask_loss(logits,target,editable_band=band,boundary_weight=frozen['loss']['boundaryWeight'])
            if not torch.isfinite(loss):
                raise ValueError('nonfinite terminal loss')
            loss.backward()
            if any(param.grad is None or not torch.isfinite(param.grad).all() for param in head.parameters()) or torch.count_nonzero(delta.grad[~band]):
                raise ValueError('finite used gradients/outside delta contract')
            vector=np.concatenate([param.grad.detach().cpu().numpy().reshape(-1).copy() for param in head.parameters()]).astype(np.float32)
            if not item['row']['presenceTarget'] and np.count_nonzero(vector):
                raise ValueError('valid-empty gradient not inherited zero')
            vectors.append(vector)
            completed.append({'id':item['row']['id'],'positive':bool(item['row']['presenceTarget']),
                              'finalDeltaExactlyMatchesSaved':True,'actualDeltaSha256':hashlib.sha256(actual.tobytes()).hexdigest(),
                              'loss':float(loss.detach()),'components':components,'finiteUsedParameterTensors':len(parameter_names),
                              'outsideBandDeltaGradientZero':True})
            print(json.dumps({'phase':'terminal-gradient','completed':len(completed),'total':45},ensure_ascii=False),flush=True)
            del packed,base,target,band,delta,logits,loss
        rows,metrics=t.metrics(data,actual_deltas,h)
        if rows!=capacity['perCandidate'] or metrics!=capacity['metrics']:
            raise ValueError('reconstruction_mismatch: all45 reconstructed final quality')
        if any(not torch.equal(value,head.state_dict()[name].detach().cpu()) for name,value in state.items()):
            raise ValueError('zero optimization weights changed')
        values=np.stack(vectors)
        with (output/'parameter-gradients.npz').open('xb') as stream:
            np.savez_compressed(stream,candidateIds=np.array(scope['candidateIds']),positiveFlags=np.array([item['row']['presenceTarget'] for item in data],bool),
                                parameterNames=np.array(parameter_names),gradients=values)
        summary=stats.summarize(values,scope['candidateIds'],[item['row']['presenceTarget'] for item in data])
        report={'schemaVersion':1,'ok':True,'decision':'all45_terminal_output_fidelity_and_gradient_diagnostic_pass',
                'inputs':{'plan':a.bind(plan_path),**plan['inputs']},'gradients':a.bind(output/'parameter-gradients.npz'),
                'parameterNames':parameter_names,'parameterCount':20385,'perCandidate':completed,'statistics':summary,
                'metrics':metrics,'qualityDecisionUnchanged':capacity['decision'],'weightsUnchanged':True,
                'actualHeadForwards':45,'actualBackwards':45,'optimizerSteps':0,'upstreamModelCalls':0,
                'cudaPeakAllocatedBytes':torch.cuda.max_memory_allocated(),'formalTrainingApprovedImages':0,'full30PilotAllowed':False,
                'scope':'Instantaneous raw loss gradients only; positive cosine does not prove optimization adequate, negative cosine does not prove capacity impossible. No AdamW-preconditioned direction or quality improvement.'}
        t.j.write_durable_new(output/'gradient-report.json',report)
        return report
    except BaseException as error:
        t.j.write_durable_new(output/'execution-failure-report.json',{'schemaVersion':1,'ok':False,'decision':'reconstruction_mismatch' if 'reconstruction_mismatch' in str(error) else 'terminal_gradient_execution_failed',
                   'plan':a.bind(plan_path),'actualHeadForwardsAttempted':calls,'confirmedGradientCandidates':len(completed),
                   'exception':repr(error),'attemptConsumed':True,'restartAllowed':False,'conclusionAllowed':False})
        raise


def verify(path):
    saved=a.read(path)
    plan_path=a.checked(saved['inputs']['plan'])
    plan=a.read(plan_path)
    for binding in saved['inputs'].values():
        a.checked(binding)
    scope,capacity,_,parent,records=validate(plan)
    _,_,deltas=load_data(scope,parent,records)
    with np.load(a.checked(saved['gradients']),allow_pickle=False) as stored:
        if stored['candidateIds'].tolist()!=scope['candidateIds'] or stored['parameterNames'].tolist()!=saved['parameterNames'] or stored['gradients'].shape!=(45,20385):
            raise ValueError('reconstruction_mismatch: gradient array identities')
        result=stats.summarize(stored['gradients'],stored['candidateIds'].tolist(),stored['positiveFlags'].tolist())
    if result!=saved['statistics'] or saved['metrics']!=capacity['metrics'] or saved['qualityDecisionUnchanged']!=capacity['decision']:
        raise ValueError('reconstruction_mismatch: gradient summary/quality')
    if [row['id'] for row in saved['perCandidate']]!=scope['candidateIds'] or saved['actualHeadForwards']!=45 or saved['actualBackwards']!=45 or saved['optimizerSteps']!=0:
        raise ValueError('fixed45 identities/budget')
    for row,delta in zip(saved['perCandidate'],deltas,strict=True):
        if row['actualDeltaSha256']!=hashlib.sha256(delta.tobytes()).hexdigest() or not row['finalDeltaExactlyMatchesSaved'] or row['finiteUsedParameterTensors']!=11 or not row['outsideBandDeltaGradientZero']:
            raise ValueError('final output/gradient record fidelity')
    return {'ok':True,'decision':'verified_all45_terminal_artifacts_no_model_rerun','report':a.bind(path),'modelCalls':0,'optimizerSteps':0,
            'statistics':{key:saved['statistics'][key] for key in ('negativePairCount','pairCount','positiveMeanGradientNorm','meanGradientNormToMeanIndividualNorm','opposedToPositiveMeanIds')}}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--plan',type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--verify-report',type=Path)
    args=parser.parse_args()
    plan_path=args.plan.resolve() if args.plan else Path(a.read(args.verify_report)['inputs']['plan']['path'])
    scope=a.read(a.read(plan_path)['inputs']['scope']['path'])
    parent=a.read(a.read(scope['inputs']['capacityPlan']['path'])['inputs']['parentPlan']['path'])
    guard=module('terminal_gradient_readonly_guard',Path(__file__).with_name('train-yolo-seg.py'))
    guard.install_read_only_ultralytics_image_check()
    try:
        result=verify(args.verify_report) if args.verify_report else audit(plan_path,args.output.resolve())
        print(json.dumps(result if args.verify_report else {'ok':result['ok'],'decision':result['decision'],'statistics':{key:result['statistics'][key] for key in ('negativePairCount','pairCount','positiveMeanGradientNorm','meanGradientNormToMeanIndividualNorm','opposedToPositiveMeanIds')},'report':a.bind(args.output.resolve()/'gradient-report.json')},ensure_ascii=False),flush=True)
    finally:
        for directory in parent['cacheCleanupRoots']:
            guard.remove_ultralytics_label_caches(Path(directory))


if __name__=='__main__':
    main()
