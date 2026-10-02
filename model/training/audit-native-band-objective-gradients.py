"""新BCE平均域的全45零优化梯度门；复用身份相同的原像素接口证据。"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import torch
import importlib.util


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


c=module('band_gradient_context',Path(__file__).with_name('audit-native-context-head-feasibility.py'))
a=c.a
b=module('band_gradient_browser',Path(__file__).with_name('verify-native-boundary-head-browser.py'))
loss_model=module('band_gradient_loss',Path(__file__).with_name('native-band-objective-loss.py'))


def validate(plan):
    for value in plan['inputs'].values():
        a.checked(value)
    scope=a.read(plan['inputs']['bandScope']['path'])
    for value in scope['inputs'].values():
        a.checked(value)
    interface=a.read(a.checked(plan['inputs']['interfaceExecutionPlan']))
    parent,records=c.validate(interface)
    static=a.read(a.checked(plan['inputs']['staticReport']))
    browser=a.read(a.checked(plan['inputs']['browserReport']))
    if b.build(Path(browser['inputs']['staticReport']['path']),Path(browser['inputs']['liveBrowser']['path']))!=browser:
        raise ValueError('reconstruction_mismatch: reused actual browser evidence')
    if not static['ok'] or not browser['ok'] or static['inputs']['plan']!=plan['inputs']['interfaceExecutionPlan'] or browser['inputs']['staticReport']!=plan['inputs']['staticReport']:
        raise ValueError('interface prerequisites/identity')
    if scope['inputs']['staticReport']!=plan['inputs']['staticReport'] or scope['inputs']['browserReport']!=plan['inputs']['browserReport']:
        raise ValueError('frozen scope interface binding')
    if scope['candidateIds']!=parent['candidateIds'] or scope['qualityGatesUnchanged']!=parent['qualityGatesUnchanged']:
        raise ValueError('fixed denominator/gates')
    if plan['maximumGradientCandidates']!=45 or plan['optimizerSteps']!=0 or plan['upstreamModelCalls']!=0 or plan['additionalInterfaceModelRuns']!=0:
        raise ValueError('frozen zero optimization budget')
    for key,path in [('gradientRunner',Path(__file__)),('bandLossSource',Path(loss_model.__file__)),('headSource',Path(c.h.__file__)),('nativeHelperSource',Path(c.__file__))]:
        if plan['inputs'][key]!=a.bind(path):
            raise ValueError('executed source not bound: '+key)
    if static['architecture']!=c.architecture_proof(parent['model']['seed']):
        raise ValueError('architecture changed')
    if scope['reachability']['witnessJointCount']<scope['reachability']['requiredCount'] or scope['closedBranch']['decision']!='native_capacity_fail_no_full30':
        raise ValueError('reachability/previous failure')
    return parent,records,static


def data_with_reused_interface(parent,records,static):
    h,data=c.native_data(parent,records)
    if [row['id'] for row in static['nativeControls']]!=parent['candidateIds']:
        raise ValueError('reconstruction_mismatch: interface identities')
    for item,control in zip(data,static['nativeControls'],strict=True):
        for name,value in [('packed',item['packed']),('base',item['base']),('band',item['band'].astype(np.uint8))]:
            if a.checked(control['files'][name]).read_bytes()!=value.tobytes():
                raise ValueError('reconstruction_mismatch: interface input/band')
    torch.manual_seed(parent['model']['seed'])
    seeded=h.NativeBoundaryNailRefiner().state_dict()
    for info in static['models'].values():
        a.checked(info['file'])
        a.checked(info['weights'])
    zero=torch.load(static['models']['zero']['weights']['path'],map_location='cpu',weights_only=True)
    if zero.keys()!=seeded.keys() or any(not torch.equal(zero[key],value) for key,value in seeded.items()):
        raise ValueError('reused initial model tensor identity')
    return h,data


def audit(plan_path,output):
    plan=a.read(plan_path)
    parent,records,static=validate(plan)
    if output.exists():
        raise FileExistsError('gradient budget already claimed; no restart')
    output.mkdir(parents=True)
    a.write_new(output/'claim.json',{'plan':a.bind(plan_path),'maximumGradientCandidates':45,'attemptConsumed':True,'restartAllowed':False})
    completed=[]
    try:
        h,data=data_with_reused_interface(parent,records,static)
        if not torch.cuda.is_available():
            raise RuntimeError('CUDA required')
        torch.set_num_threads(2)
        torch.manual_seed(parent['model']['seed'])
        torch.backends.cuda.matmul.allow_tf32=False
        torch.backends.cudnn.allow_tf32=False
        torch.backends.cudnn.deterministic=True
        torch.backends.cudnn.benchmark=False
        head=h.NativeBoundaryNailRefiner().cuda().train()
        torch.cuda.reset_peak_memory_stats()
        for item in data:
            head.zero_grad(set_to_none=True)
            packed=torch.from_numpy(item['packed'][None].copy()).cuda()
            base=torch.from_numpy(item['base'][None,None].copy()).cuda()
            target=torch.from_numpy(item['target'][None,None].copy()).cuda()
            band=torch.from_numpy(item['band'][None,None].copy()).cuda()
            delta=head(packed)
            delta.retain_grad()
            if not torch.isfinite(delta).all() or torch.count_nonzero(delta) or tuple(delta.shape)!=(1,1,*item['base'].shape):
                raise ValueError('initial native output')
            logits=h.compose_native_logits(base,delta,band)
            loss,parts=loss_model.conditional_mask_loss(logits,target,editable_band=band,boundary_weight=.2)
            if not torch.isfinite(loss):
                raise ValueError('nonfinite band loss')
            loss.backward()
            gradients={name:param.grad for name,param in head.named_parameters()}
            if any(value is None or not torch.isfinite(value).all() for value in gradients.values()):
                raise ValueError('nonfinite/missing used gradient')
            positive=bool(item['row']['presenceTarget'])
            nonzero=bool(torch.count_nonzero(gradients['output.weight']))
            if positive!=nonzero or torch.count_nonzero(delta.grad[~band]):
                raise ValueError('positive/empty/outside gradient')
            if any(torch.count_nonzero(value) for name,value in gradients.items() if name.startswith('features.')):
                raise ValueError('zero output feature gradient contract')
            initial=h.apply_native_delta(item['base'],delta.detach().cpu().numpy()[0,0],item['band'])
            if not np.array_equal(initial>=.5,item['base']>=.5) or not np.array_equal(initial[~item['band']].view(np.uint32),item['base'][~item['band']].view(np.uint32)):
                raise ValueError('initial mask/outside bits')
            completed.append({'id':item['row']['id'],'positive':positive,'loss':float(loss.detach()),'components':parts,
                              'finiteUsedParameterTensors':len(gradients),'outputWeightGradientNonzero':nonzero,
                              'featureGradientsZeroAtZeroOutput':True,'outsideBandDeltaGradientZero':True,
                              'initialMaskParity':True,'outsideProbabilityBitParity':True})
            print(json.dumps({'phase':'band-objective-initial-gradient','completed':len(completed),'total':45},ensure_ascii=False),flush=True)
            del packed,base,target,band,delta,logits,loss,gradients
        report={'schemaVersion':1,'ok':True,'decision':'all45_band_objective_gradient_pass_with_identical_reused_interface',
                'inputs':{'plan':a.bind(plan_path),**plan['inputs']},'architecture':static['architecture'],
                'gradient':{'candidateCount':45,'positiveCount':34,'emptyCount':11,'perCandidate':completed,
                            'peakAllocatedBytes':torch.cuda.max_memory_allocated(),'precision':'float32','device':torch.cuda.get_device_name(0)},
                'callAccounting':{'actualHeadGradientForwards':45,'additionalTorchInterfaceRuns':0,'additionalOrtInterfaceRuns':0,'additionalBrowserRuns':0},
                'optimizerSteps':0,'upstreamModelCalls':0,'formalTrainingApprovedImages':0,'full30PilotAllowed':False,
                'qualityEvidence':False,'scope':'Only loss BCE averaging domain changes; initial native model/input/ONNX and all45 browser captures have identical bound evidence. No trained quality claim.'}
        a.write_new(output/'gradient-report.json',report)
        return report
    except BaseException as error:
        a.write_new(output/'execution-failure-report.json',{'ok':False,'inputs':{'plan':a.bind(plan_path),'runner':a.bind(Path(__file__))},
                      'confirmedGradientCandidates':len(completed),'exception':repr(error),'attemptConsumed':True,'restartAllowed':False})
        raise


def verify(path):
    saved=a.read(path)
    plan=a.read(a.checked(saved['inputs']['plan']))
    for value in saved['inputs'].values():
        a.checked(value)
    parent,records,static=validate(plan)
    data_with_reused_interface(parent,records,static)
    rows=saved['gradient']['perCandidate']
    if saved['architecture']!=static['architecture'] or [row['id'] for row in rows]!=parent['candidateIds'] or len(rows)!=45:
        raise ValueError('reconstruction_mismatch: gradient identity')
    flags=['featureGradientsZeroAtZeroOutput','outsideBandDeltaGradientZero','initialMaskParity','outsideProbabilityBitParity']
    if not saved['ok'] or saved['optimizerSteps'] or saved['qualityEvidence'] or any(row['finiteUsedParameterTensors']!=11 or row['outputWeightGradientNonzero']!=row['positive'] or not all(row[key] for key in flags) for row in rows):
        raise ValueError('gradient gates')
    return {'ok':True,'decision':'verified_bound_band_gradient_record_and_all45_interface_inputs','report':a.bind(path),
            'replayHeadForwards':0,'optimizerSteps':0,'scope':'No gradient rerun; finite-gradient record remains original executed evidence.'}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--plan',type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--verify-report',type=Path)
    args=parser.parse_args()
    plan_path=args.plan.resolve() if args.plan else Path(a.read(args.verify_report)['inputs']['plan']['path'])
    parent=a.read(a.read(plan_path)['inputs']['parentPlan']['path'])
    guard=module('band_gradient_guard',Path(__file__).with_name('train-yolo-seg.py'))
    guard.install_read_only_ultralytics_image_check()
    try:
        result=verify(args.verify_report) if args.verify_report else audit(plan_path,args.output.resolve())
        print(json.dumps(result if args.verify_report else {'ok':result['ok'],'decision':result['decision'],'report':a.bind(args.output.resolve()/'gradient-report.json')},ensure_ascii=False),flush=True)
    finally:
        for directory in parent['cacheCleanupRoots']:
            guard.remove_ultralytics_label_caches(Path(directory))


if __name__=='__main__':
    main()
