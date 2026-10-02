"""双路径原像素纠正头全候选零优化梯度、动态ONNX及接口控制；不批准发布。"""
from __future__ import annotations
import argparse
import copy
import json
from pathlib import Path
import numpy as np
import onnx
import onnxruntime as ort
import torch
from PIL import Image
import importlib.util


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


core=module('native_static_core',Path(__file__).with_name('train-conditional-nail-refinement-microfit.py'));a=core.a


h=module('dual_static_head',Path(__file__).with_name('native-dual-path-nail-refinement.py'))


def architecture_proof(seed):
    torch.manual_seed(seed)
    old=h.context_module.NativeBoundaryNailRefiner(); rng=torch.get_rng_state().clone()
    torch.manual_seed(seed)
    new=h.NativeBoundaryNailRefiner()
    if any(not torch.equal(v,new.context.state_dict()[k]) for k,v in old.state_dict().items()) or not torch.equal(rng,torch.get_rng_state()):
        raise ValueError('context initial tensors/external RNG')
    for branch,expected in [(new.context,[1,3,9]),(new.local,[1,1,1])]:
        if [list(branch.features[i].dilation) for i in (0,3,6)]!=[[v,v] for v in expected]:raise ValueError('branch dilations')
        if any(branch.features[i].padding!=branch.features[i].dilation for i in (0,3,6)):raise ValueError('branch padding')
    count=sum(p.numel() for p in new.parameters())
    if count!=40770 or len(list(new.parameters()))!=22:raise ValueError('dual parameter count')
    return {'parameterCount':count,'parameterTensors':22,'contextDilations':[1,3,9],'localDilations':[1,1,1],
            'contextInitialTensorsEqual':True,'externalCpuRngEqual':True,'localSeed':1606,'zeroOutputBranches':2,
            'scope':'Native local plus context untrained architecture; not learned quality or capacity proof.'}


def validate(plan):
    for binding in plan['inputs'].values():a.checked(binding)
    parent=a.read(a.checked(plan['inputs']['parentPlan']))
    scope=a.read(a.checked(plan['inputs']['dualScope']))
    for document in (parent,scope):
        for binding in document['inputs'].values():a.checked(binding)
    if parent['trainingAllowed'] or scope['trainingAllowed'] or scope['optimizerSteps'] or scope['reachability']['witnessJointCount']<scope['reachability']['requiredCount']:raise ValueError('prerequisites/reachability')
    if scope['candidateIds']!=parent['candidateIds'] or scope['qualityGatesUnchanged']!=parent['qualityGatesUnchanged']:raise ValueError('scope denominator/gates')
    if scope['inputs']['parentNativePlan']!=plan['inputs']['parentPlan'] or scope['inputs']['newHeadSource']!=plan['inputs']['headSource'] or scope['inputs']['lossSource']!=plan['inputs']['lossSource']:raise ValueError('scope identity')
    if plan['optimizerSteps']!=0 or plan['upstreamModelCalls']!=0 or plan['maximumGradientCandidates']!=45 or plan['trainingAllowed'] or plan['full30PilotAllowed']:raise ValueError('zero optimization budget')
    if plan['staticBudget']!={'exportTraceCalls':2,'torchProbeCalls':6,'ortProbeRuns':6} or plan['browserBudget']!={'modelRunsPerBackend':6,'nativePackingCompositionControls':45}:raise ValueError('interface budget')
    for key,path in [('staticRunner',Path(__file__)),('headSource',Path(h.__file__)),('oldContextSource',Path(h.context_module.__file__)),('nativeHelperSource',Path(h.context_module.base.__file__)),('lossSource',Path(__file__).with_name('native-band-objective-loss.py'))]:
        if plan['inputs'][key]!=a.bind(path):raise ValueError('executed source not bound: '+key)
    if plan['interfaceControl']!={'seed':1605,'branchSeeds':{'context':1605,'local':1606},'outputWeightScale':.01,'outputBias':.02,'optimizerSteps':0,'qualityEvidence':False}:raise ValueError('nonzero control contract')
    records=a.read(a.checked(parent['inputs']['manifest']))['records']
    if [r['id'] for r in records]!=parent['candidateIds'] or len(records)!=45 or sum(r['presenceTarget'] for r in records)!=34:raise ValueError('reconstruction_mismatch: all45 identities')
    if plan['runtimeProbeIds']!=['source-014-proposal-01','source-010-proposal-06','source-008-proposal-05'] or plan['requiredBackends']!=['wasm','webgpu']:raise ValueError('fixed runtime probes')
    architecture_proof(parent['model']['seed'])
    return parent,records


def native_data(parent,records):
    # Packaging stays identical to frozen helper; head is the newly bound dual prototype.
    with np.load(a.checked(parent['inputs']['frozenLogits']),allow_pickle=False) as saved:
        if saved['candidateIds'].tolist()!=parent['candidateIds']:raise ValueError('logits identity')
        logits=saved['logits'].copy()
    data=[]
    for row,values in zip(records,logits,strict=True):
        probability=(1/(1+np.exp(-np.clip(values,-80,80)))).astype(np.float32)
        base=np.asarray(Image.fromarray(probability).resize(tuple(row['nativeSize']),Image.Resampling.BILINEAR)).copy()
        with Image.open(a.checked(row['paths']['nativeRgb'])) as im:rgb=np.asarray(im.convert('RGB')).copy()
        with Image.open(a.checked(row['paths']['nativeCoarse'])) as im:coarse=np.asarray(im).copy()
        with Image.open(a.checked(row['paths']['nativeTarget'])) as im:target=(np.asarray(im).copy()>=128).astype(np.float32)
        packed,band=h.pack_native_input(rgb,coarse,base)
        data.append({'row':row,'rgb':rgb,'coarse':coarse,'base':base,'target':target,'packed':packed,'band':band})
    return h,data


def control_head(h,seed):
    torch.manual_seed(seed);head=h.NativeBoundaryNailRefiner()
    for branch,branch_seed in [(head.context,seed),(head.local,1606)]:
        generator=torch.Generator().manual_seed(branch_seed)
        with torch.no_grad():
            branch.output.weight.copy_(torch.randn(branch.output.weight.shape,generator=generator)*.01)
            branch.output.bias.fill_(.02)
    return head.eval()


def gradient_evidence(head,delta,band,positive):
    grads={name:p.grad for name,p in head.named_parameters()}
    if len(grads)!=22 or any(g is None or not torch.isfinite(g).all() for g in grads.values()):raise ValueError('used parameter gradients')
    branches={name:bool(torch.count_nonzero(grads[name+'.output.weight'])) for name in ('context','local')}
    if any(value!=positive for value in branches.values()):raise ValueError('positive both output / valid empty zero gradient')
    if delta.grad is None or not torch.isfinite(delta.grad).all() or torch.count_nonzero(delta.grad[~band]):raise ValueError('outside-band gradient leakage')
    if any(torch.count_nonzero(g) for name,g in grads.items() if '.features.' in name):raise ValueError('zero output initialization feature gradient contract')
    return branches


def inspect(path):
    graph=onnx.load(str(path));onnx.checker.check_model(graph,full_check=True)
    operators={}
    for node in graph.graph.node:operators[node.op_type]=operators.get(node.op_type,0)+1
    options=ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1
    session=ort.InferenceSession(str(path),options,providers=['CPUExecutionProvider'])
    if session.get_inputs()[0].name!='native_input' or session.get_outputs()[0].name!='delta':raise ValueError('ONNX names')
    if session.get_inputs()[0].shape[:2]!=[1,6] or session.get_outputs()[0].shape[:2]!=[1,1]:raise ValueError('ONNX native channels')
    if session.get_inputs()[0].shape[2:]!=['height','width'] or session.get_outputs()[0].shape[2:]!=['height','width']:raise ValueError('ONNX dynamic spatial dimensions')
    return session,operators


def audit(plan_path,output):
    plan=a.read(plan_path);parent,records=validate(plan)
    parity=module('native_parity_prerequisite',a.checked(plan['inputs']['parityVerifier']))
    parity.verify(Path(parent['inputs']['inputParity']['path']))
    h,data=native_data(parent,records)
    if output.exists():raise FileExistsError('once-only feasibility directory exists')
    output.mkdir(parents=True);a.write_new(output/'claim.json',{'inputs':{'plan':a.bind(plan_path)},'maximumGradientCandidates':45,'optimizerSteps':0})
    torch.set_num_threads(2);torch.manual_seed(parent['model']['seed'])
    if not torch.cuda.is_available():raise RuntimeError('CUDA required for frozen gradient audit')
    torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    torch.backends.cudnn.deterministic=True;torch.backends.cudnn.benchmark=False
    head=h.NativeBoundaryNailRefiner().cuda().train();parameters=sum(p.numel() for p in head.parameters())
    if parameters>parent['model']['maximumParameters']:raise ValueError('parameter cap')
    loss_model=module('native_mask_loss',a.checked(plan['inputs']['lossSource']))
    gradients=[];torch.cuda.reset_peak_memory_stats()
    for item in data:
        row=item['row'];head.zero_grad(set_to_none=True)
        packed=torch.from_numpy(item['packed'][None]).cuda();base=torch.from_numpy(item['base'][None,None]).cuda()
        target=torch.from_numpy(item['target'][None,None]).cuda();band=torch.from_numpy(item['band'][None,None]).cuda()
        delta=head(packed);delta.retain_grad()
        if not torch.isfinite(delta).all() or tuple(delta.shape)!=(1,1,*item['base'].shape) or torch.count_nonzero(delta):raise ValueError('initial finite/zero native output')
        logits=h.compose_native_logits(base,delta,band)
        loss,components=loss_model.conditional_mask_loss(logits,target,editable_band=band,boundary_weight=plan['loss']['boundaryWeight'])
        if not torch.isfinite(loss):raise ValueError('native loss nonfinite')
        loss.backward()
        branches=gradient_evidence(head,delta,band,bool(row['presenceTarget']))
        grads={name:p.grad for name,p in head.named_parameters()};nonzero=all(branches.values())
        # 无优化步：初始feature梯度全零是零输出层的结构性质，不能声称已学会。
        initial=h.apply_native_delta(item['base'],delta.detach().cpu().numpy()[0,0],item['band'])
        if not np.array_equal(initial>=.5,item['base']>=.5):raise ValueError('initial frozen mask parity')
        if not np.array_equal(initial[~item['band']].view(np.uint32),item['base'][~item['band']].view(np.uint32)):raise ValueError('outside native probability bits')
        gradients.append({'id':row['id'],'positive':bool(row['presenceTarget']),'loss':float(loss.detach()),'components':components,
                          'finiteUsedParameterTensors':len(grads),'branchOutputWeightGradientsNonzero':branches,'outputWeightGradientNonzero':nonzero,'featureGradientsZeroAtZeroOutput':True,
                          'outsideBandDeltaGradientZero':True,'initialMaskParity':True,'outsideProbabilityBitParity':True})
        a.write_new(output/f'gradient-record-{len(gradients):03d}.json',gradients[-1])
        print(json.dumps({'phase':'initial-gradient','completed':len(gradients),'total':45,'id':row['id']},ensure_ascii=False),flush=True)
        del packed,base,target,band,delta,logits,loss,grads
    peak=torch.cuda.max_memory_allocated();head.zero_grad(set_to_none=True);head=head.cpu().eval();torch.cuda.empty_cache()
    torch.save(head.state_dict(),output/'zero-initial-weights.pt')
    control=control_head(h,parent['model']['seed']);torch.save(control.state_dict(),output/'interface-control-weights.pt')
    selected=[next(v for v in data if v['row']['id']==identity) for identity in plan['runtimeProbeIds']]
    models={};probes=[]
    for key,model in [('zero',head),('control',control)]:
        path=output/f'{key}.onnx';probe=torch.from_numpy(selected[0]['packed'][None])
        with torch.inference_mode():
            torch.onnx.export(model,(probe,),str(path),input_names=['native_input'],output_names=['delta'],
                              dynamic_axes={'native_input':{2:'height',3:'width'},'delta':{2:'height',3:'width'}},
                              opset_version=17,dynamo=False,do_constant_folding=True)
        if path.stat().st_size>parent['model']['maximumOnnxBytes']:raise ValueError('ONNX bytes')
        session,operators=inspect(path)
        models[key]={'file':a.bind(path),'bytes':path.stat().st_size,'weights':a.bind(output/('zero-initial-weights.pt' if key=='zero' else 'interface-control-weights.pt')),
                     'operators':operators,'role':'untrained_zero_initial_head' if key=='zero' else 'untrained_deterministic_nonzero_interface_control_not_quality'}
        for item in selected:
            values=item['packed'][None]
            with torch.inference_mode():eager=model(torch.from_numpy(values)).numpy()
            cpu=session.run(None,{'native_input':values})[0];error=float(np.max(np.abs(eager-cpu)))
            if not np.isfinite(cpu).all() or cpu.shape!=(1,1,*item['base'].shape) or error>plan['limits']['cpuAbsoluteError']:raise ValueError('native CPU parity')
            if key=='control' and (float(cpu.std())<=1e-6 or not np.count_nonzero(cpu)):raise ValueError('nonzero control failed to exercise feature path')
            folder=output/item['row']['id'];folder.mkdir(exist_ok=True);cpu.tofile(folder/f'{key}-cpu.bin')
            probes.append({'id':item['row']['id'],'modelKey':key,'dims':list(cpu.shape),'cpuMaxAbsoluteError':error,
                           'outputStd':float(cpu.std()),'cpu':a.bind(folder/f'{key}-cpu.bin')})
    controls=[]
    for item in data:
        row=item['row'];folder=output/row['id'];folder.mkdir(exist_ok=True)
        # 固定非模型delta压力组合，覆盖带内翻转/带外保真；不作质量预测。
        delta=((np.arange(item['base'].size).reshape(item['base'].shape)%3)-1).astype(np.float32)*2
        modified=h.apply_native_delta(item['base'],delta,item['band']);mask=(modified>=.5).astype(np.uint8)
        files={}
        for name,values in [('rgb',item['rgb']),('coarse',item['coarse']),('base',item['base']),('packed',item['packed']),
                            ('band',item['band'].astype(np.uint8)),('composition-delta',delta),('composition-probability',modified),('composition-mask',mask)]:
            file=folder/f'{name}.bin';values.tofile(file);files[name]=a.bind(file)
        controls.append({'id':row['id'],'nativeSize':row['nativeSize'],'cropBox':row['cropBox'],'positive':bool(row['presenceTarget']),
                         'kind':'mask' if mask.any() else 'rejected','files':files})
    report={'schemaVersion':1,'ok':True,'decision':'native_head_all45_initial_gradient_dynamic_static_pass_pending_browser',
            'inputs':{'plan':a.bind(plan_path),**plan['inputs']},'architecture':architecture_proof(parent['model']['seed']),'parameterCount':parameters,'models':models,
            'gradient':{'candidateCount':45,'positiveCount':34,'emptyCount':11,'finiteUsedParameterTensorsPerCandidate':len(list(head.parameters())),
                        'peakAllocatedBytes':peak,'device':torch.cuda.get_device_name(0),'precision':'float32','perCandidate':gradients},
            'runtimeProbes':probes,'nativeControls':controls,'optimizerSteps':0,'upstreamModelCalls':0,
            'callAccounting':{'gradientRealHeadForwards':45,'staticExportTraces':2,'staticTorchProbeForwards':6,'staticOrtProbeRuns':6},
            'trainingApprovedImages':0,'qualityEvidence':False,'full30PilotAllowed':False,
            'scope':'Frozen base predictions. Actual zero-initial45 gradients finite; features gradients zero by design, positive output gradients nonzero; valid empty all zero. Nonzero control is untrained interface-only, no optimizer or threshold selection.'}
    a.write_new(output/'feasibility-report.json',report);return report


def verify(path):
    saved=a.read(path);plan=a.read(a.checked(saved['inputs']['plan']));parent,records=validate(plan)
    for binding in saved['inputs'].values():a.checked(binding)
    if saved['optimizerSteps']!=0 or saved['upstreamModelCalls']!=0 or saved['qualityEvidence']:raise ValueError('scope')
    h,data=native_data(parent,records);torch.set_num_threads(2)
    for key,info in saved['models'].items():
        session,operators=inspect(a.checked(info['file']));a.checked(info['weights'])
        if operators!=info['operators'] or info['bytes']!=Path(info['file']['path']).stat().st_size:raise ValueError('ONNX identity')
        torch.manual_seed(parent['model']['seed']);head=h.NativeBoundaryNailRefiner() if key=='zero' else control_head(h,parent['model']['seed'])
        state=torch.load(info['weights']['path'],map_location='cpu',weights_only=True)
        if any(not torch.equal(state[n],v) for n,v in head.state_dict().items()):raise ValueError('untrained initialization identity')
        for probe in [p for p in saved['runtimeProbes'] if p['modelKey']==key]:
            item=next(v for v in data if v['row']['id']==probe['id']);a.checked(probe['cpu'])
            result=session.run(None,{'native_input':item['packed'][None]})[0]
            expected=np.fromfile(probe['cpu']['path'],np.float32).reshape(probe['dims'])
            if not np.array_equal(result,expected):raise ValueError('reconstruction_mismatch: CPU control')
    if [r['id'] for r in saved['gradient']['perCandidate']]!=parent['candidateIds']:raise ValueError('gradient denominator')
    if saved['architecture']!=architecture_proof(parent['model']['seed']):raise ValueError('dual architecture reconstruction')
    if saved['gradient']['finiteUsedParameterTensorsPerCandidate']!=22 or saved['gradient']['candidateCount']!=45:raise ValueError('gradient tensor/count')
    flags=['featureGradientsZeroAtZeroOutput','outsideBandDeltaGradientZero','initialMaskParity','outsideProbabilityBitParity']
    for i,row in enumerate(saved['gradient']['perCandidate'],1):
        if a.read(path.parent/f'gradient-record-{i:03d}.json')!=row or row['finiteUsedParameterTensors']!=22 or row['branchOutputWeightGradientsNonzero']!={k:row['positive'] for k in ('context','local')} or not all(row[k] for k in flags):raise ValueError('bound executed gradient record')
    for info in saved['models'].values():
        graph=onnx.load(str(a.checked(info['file'])))
        dilation=[list(next(attr.ints for attr in n.attribute if attr.name=='dilations')) for n in graph.graph.node if n.op_type=='Conv']
        if dilation!=[[1,1],[3,3],[9,9],[1,1],[1,1],[1,1],[1,1],[1,1]]:raise ValueError('dual ONNX branch dilations')
    for recorded,item in zip(saved['nativeControls'],data,strict=True):
        for binding in recorded['files'].values():a.checked(binding)
        original={'rgb':item['rgb'],'coarse':item['coarse'],'base':item['base'],'packed':item['packed'],'band':item['band'].astype(np.uint8)}
        for name,values in original.items():
            if Path(recorded['files'][name]['path']).read_bytes()!=values.tobytes():raise ValueError('reconstruction_mismatch: native inputs')
        delta=((np.arange(item['base'].size).reshape(item['base'].shape)%3)-1).astype(np.float32)*2
        changed=h.apply_native_delta(item['base'],delta,item['band'])
        for name,values in [('composition-delta',delta),('composition-probability',changed),('composition-mask',(changed>=.5).astype(np.uint8))]:
            if Path(recorded['files'][name]['path']).read_bytes()!=values.tobytes():raise ValueError('reconstruction_mismatch: native composition')
    return {'ok':True,'decision':'verified_native_static_artifacts_and_all45_inputs','report':a.bind(path),'optimizerSteps':0,
            'scope':'No gradient/model rerun; original executed gradient record remains bound evidence.'}


def main():
    p=argparse.ArgumentParser();p.add_argument('--plan',type=Path);p.add_argument('--output',type=Path);p.add_argument('--verify-report',type=Path);args=p.parse_args()
    plan_path=args.plan.resolve() if args.plan else Path(a.read(args.verify_report)['inputs']['plan']['path'])
    plan=a.read(plan_path);parent=a.read(plan['inputs']['parentPlan']['path'])
    guard=module('native_static_guard',Path(__file__).with_name('train-yolo-seg.py'));guard.install_read_only_ultralytics_image_check()
    try:
        result=verify(args.verify_report) if args.verify_report else audit(plan_path,args.output.resolve())
        print(json.dumps({'ok':True,'result':result if args.verify_report else {'decision':result['decision'],'parameters':result['parameterCount'],
                          'gradientCount':result['gradient']['candidateCount'],'cudaPeak':result['gradient']['peakAllocatedBytes'],
                          'models':result['models'],'report':a.bind(args.output.resolve()/'feasibility-report.json')}},ensure_ascii=False))
    except BaseException as error:
        if args.output and args.output.exists():
            records=list(args.output.glob('gradient-record-*.json'))
            failure=args.output/'execution-failure-report.json'
            if not failure.exists():a.write_new(failure,{'ok':False,'inputs':{'plan':a.bind(plan_path),'runner':a.bind(Path(__file__))},'confirmedGradientLowerBound':len(records),'exception':repr(error),'restartAllowed':False})
        raise
    finally:
        for directory in parent['cacheCleanupRoots']:guard.remove_ultralytics_label_caches(Path(directory))


if __name__=='__main__':main()
