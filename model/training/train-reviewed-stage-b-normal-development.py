"""完整已审train条件输入的正常原尺寸训练；新预算、严格FP32、不可覆盖事件。"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import math
import os
import time
import traceback
from pathlib import Path

import numpy as np
from PIL import Image
import torch
import torch.nn.functional as F

HERE = Path(__file__).resolve().parent


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


d = module(HERE/'reviewed-role-development-data.py', 'normal_stage_b_data')


def require(ok, message):
    if not ok: raise ValueError('reconstruction_mismatch: '+message)


PRECISION = {'dtype': 'float32', 'autocast': False, 'cudaMatmulAllowTf32': False,
             'cudnnAllowTf32': False, 'float32MatmulPrecision': 'highest'}
LOSS = {'positivePixelBce': 1.0, 'positiveDice': 1.0, 'positiveSoftBoundaryIou': 0.2,
        'positiveNativeBoundaryBandBce': 2.0, 'boundaryBandRadiusOriginalPixels': 4,
        'presenceBce': 0.5, 'presenceClassBalance': 'N/(2*class_count)',
        'rejectPixelBce': 0.0, 'presenceEncoderGradients': 'joint'}
AUGMENTATION = {'spatial': 'D4_integer_rot90_and_horizontal_flip', 'resampling': False,
                'brightnessRange': [0.9, 1.1], 'contrastRange': [0.9, 1.1],
                'originalMarkersRetained': True}
QUALITY = {'iou': 0.75, 'boundaryIou': 0.75, 'boundaryF1': 0.9, 'boundaryToleranceOriginalPixels': 2,
           'jointPositiveRate': 0.8, 'meanIou': 0.85, 'meanBoundaryF1': 0.9,
           'allPositivePresenceRequired': True, 'allRejectsZeroOutputRequired': True}


def resources(plan_path):
    plan = d.read(d.bind(plan_path))
    require(plan['purpose'] == 'fresh_normal_stage_b_train_only_native_development', 'training purpose')
    for ref in plan['inputs'].values(): d.checked(ref)
    for ref in plan['sources'].values(): d.checked(ref)
    require(d.checked(plan['sources']['trainer']) == Path(__file__).resolve(), 'trainer identity')
    require(plan['precision'] == PRECISION and plan['loss'] == LOSS and plan['augmentation'] == AUGMENTATION and plan['quality'] == QUALITY, 'recipe/quality/precision')
    require(plan['initialization'] == {'kind': 'fresh_model_no_prior_weights_or_optimizer', 'seed': 20261014}, 'fresh initialization')
    data = d.read(plan['inputs']['materialization']); scope = d.read(plan['inputs']['designScope'])
    require(data['ok'] and data['fullTruthIntegerCoordinateRoundtripExact'] and data['sourceTruthPixelsLost'] == 0, 'native pixel gate')
    require(plan['inputs']['materialization'] == scope['inputs']['nativeMaterialization'], 'design/materialization binding')
    rows = data['records']; counts = data['counts']['train']; n = len(rows)
    require(n == counts['candidateInputs'] and sum(r['presenceTarget'] for r in rows) == counts['truthNails'] == counts['positiveInputs'], 'full cohort counts')
    require(all(r['split'] == r['candidateIdentity']['identity']['split'] == 'train' for r in rows), 'val backflow')
    require(plan['candidateIdentities'] == scope['candidateIdentities'] == [r['candidateIdentity'] for r in rows], 'all candidate identities')
    require(plan['counts'] == data['counts'] and scope['zeroModelRepresentationReachability']['conflictingTargetSignatures'] == [], 'representation/counts')
    training = plan['training']
    require(training == {'epochs': 100, 'gradientAccumulation': 4, 'optimizer': 'AdamW', 'learningRate': 0.0003,
                         'minimumLearningRate': 0.00003, 'weightDecay': 0.0001, 'gradientClipNorm': 1.0,
                         'selection': 'fixed_final_epoch_only_no_val_selection', 'checkpointEveryEpochs': 10}, 'normal recipe')
    budget = {'maximumAttempts': 1, 'epochs': 100, 'optimizerSteps': 100*math.ceil(n/4),
              'augmentedTrainingInputs': 100*n, 'finalTrainInferenceInputs': n,
              'internalValInputs': 0, 'protectedHoldoutInputs': 0, 'oldBudgetsMayResume': False}
    require(plan['budget'] == budget and plan['preflightBudget'] == {'maximumAttempts': 1, 'trainForwardBackwardInputs': n, 'optimizerSteps': 0}, 'new execution budgets')
    materializer = module(d.checked(plan['sources']['materializer']), 'normal_input_materializer')
    execution, input_plan, _, _, cleanup_roots = materializer.resources(data['execution'])
    require(data['plan'] == execution['plan'], 'materialization execution')
    guard = d.load(d.checked(input_plan['inputs']['readOnlyGuard']), 'normal_read_only_guard')
    guard.install_read_only_ultralytics_image_check()
    net = module(d.checked(plan['sources']['model']), 'normal_native_model')
    band = module(d.checked(plan['sources']['boundaryBand']), 'normal_boundary_band')
    metric = module(d.checked(input_plan['inputs']['roiHelper']), 'normal_native_metrics')
    return plan, data, rows, net, band, metric, guard, cleanup_roots


def load_samples(rows):
    samples = []
    for row in rows:
        values = {}
        for name in ('nativeRgb', 'nativeCoarse', 'nativeTarget'):
            with Image.open(d.checked(row['paths'][name])) as image:
                image.load(); values[name] = np.asarray(image).copy()
        rgb, coarse, target = (values[k] for k in ('nativeRgb', 'nativeCoarse', 'nativeTarget'))
        require(rgb.dtype == coarse.dtype == target.dtype == np.uint8, 'native uint8 domain')
        require(set(np.unique(coarse)) <= {0,255} and set(np.unique(target)) <= {0,255}, 'binary native mask')
        require(rgb.shape[:2] == coarse.shape == target.shape and [rgb.shape[1],rgb.shape[0]] == row['nativeSize'], 'native shape')
        require(int((target>0).sum()) == row['nativeTargetPixels'] and bool(target.any()) == row['presenceTarget'], 'native target/presence')
        samples.append((rgb,coarse,target,row['presenceTarget']))
    return samples


def augment(rgb, coarse, target, rotation, flip, brightness, contrast):
    require(rotation in (0,1,2,3) and isinstance(flip,bool), 'integer augmentation')
    require(0.9 <= brightness <= 1.1 and 0.9 <= contrast <= 1.1, 'photometric range')
    out = [np.rot90(x,rotation,axes=(0,1)) for x in (rgb,coarse,target)]
    if flip: out = [np.flip(x,axis=1) for x in out]
    r,c,t = [x.copy() for x in out]
    # 光度增强只改训练RGB，原数据文件与整数几何目标不改。
    value = r.astype(np.float32); mean = value.mean(axis=(0,1),keepdims=True)
    r = np.rint(np.clip((value-mean)*contrast+mean,0,255)*brightness).clip(0,255).astype(np.uint8)
    require(int((t>0).sum()) == int((target>0).sum()) and int((c>0).sum()) == int((coarse>0).sum()), 'augmentation lost mask pixels')
    return r,c,t


def objective(logits, presence, truth, positive, counts, band):
    flag = torch.tensor([float(positive)],device=truth.device)
    class_count = counts['positiveInputs'] if positive else counts['rejectInputs']
    require(class_count > 0, 'presence class denominator')
    presence_loss = F.binary_cross_entropy_with_logits(presence.reshape(-1).float(),flag)
    result = 0.5*counts['candidateInputs']/(2*class_count)*presence_loss
    if positive:
        probability = logits.float().sigmoid(); truth = truth.float()
        bce = F.binary_cross_entropy_with_logits(logits.float(),truth)
        dice = 1-(2*(probability*truth).sum()+1)/(probability.sum()+truth.sum()+1)
        boundary = band.soft_boundary(probability,truth)
        result = result+bce+dice+0.2*boundary+2*band.boundary_band_bce(logits,truth,4)
    return result


def set_precision():
    torch.set_num_threads(4); torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False; torch.set_float32_matmul_precision('highest')


def fresh_model(net, device):
    torch.manual_seed(20261014); set_precision()
    model = net.NativeConditionalMaskRefiner().to(device).float(); model.requires_grad_(True)
    return model


def environment():
    return {'torch':torch.__version__,'numpy':np.__version__,'cuda':torch.version.cuda,
            'cudnn':torch.backends.cudnn.version(),'device':torch.cuda.get_device_name(0),
            'cudaMatmulAllowTf32':torch.backends.cuda.matmul.allow_tf32,
            'cudnnAllowTf32':torch.backends.cudnn.allow_tf32,'autocastEnabled':torch.is_autocast_enabled(),
            'float32MatmulPrecision':torch.get_float32_matmul_precision(),'torchThreads':torch.get_num_threads()}


def tensors_sha(model):
    return {name:hashlib.sha256(value.detach().cpu().contiguous().numpy().tobytes()).hexdigest() for name,value in model.state_dict().items()}


def full_canvas(mask, box, size):
    x0,y0,x1,y1 = box; width,height = size
    require(mask.shape == (y1-y0,x1-x0) and 0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height, 'native inverse mapping')
    canvas = np.zeros((height,width),bool); canvas[y0:y1,x0:x1] = mask
    return canvas


def candidate_metric(row, logits, presence, truth, size, net, metric):
    require(logits.dtype == np.float32 and logits.shape == truth.shape and np.isfinite(logits).all() and np.isfinite(presence), 'finite original logits')
    prediction = net.decode(logits,float(presence))
    base = {'candidateIdentity':row['candidateIdentity'],'positive':row['presenceTarget'],'presenceAccepted':bool(presence>=0)}
    if row['presenceTarget']:
        p = full_canvas(prediction,row['cropBox'],size); t = full_canvas(truth,row['cropBox'],size)
        iou = int((p&t).sum())/max(1,int((p|t).sum())); b = metric.boundary_stats(t,p,2)
        return {**base,'iou':iou,**b,'originalSourceSize':size,'jointPass':iou>=0.75 and b['boundaryIoU']>=0.75 and b['boundaryF1']>=0.9}
    return {**base,'outputPixels':int(prediction.sum()),'rejected':not prediction.any(), 'meaning':'same_candidate_not_empty_rgb'}


def summarize(records):
    pos = [r for r in records if r['positive']]; neg = [r for r in records if not r['positive']]
    require(bool(pos) and bool(neg), 'quality full two classes')
    summary = {'positiveCount':len(pos),'rejectCount':len(neg),'positivePresenceAccepted':sum(r['presenceAccepted'] for r in pos),
               'jointPassCount':sum(r['jointPass'] for r in pos),'jointPassRate':sum(r['jointPass'] for r in pos)/len(pos),
               'meanIou':float(np.mean([r['iou'] for r in pos])),'meanBoundaryIou':float(np.mean([r['boundaryIoU'] for r in pos])),
               'meanBoundaryF1':float(np.mean([r['boundaryF1'] for r in pos])),
               'rejectedCount':sum(r['rejected'] for r in neg),'rejectOutputPixels':sum(r['outputPixels'] for r in neg)}
    passed = summary['jointPassRate']>=0.8 and summary['meanIou']>=0.85 and summary['meanBoundaryF1']>=0.9 and summary['positivePresenceAccepted']==len(pos) and summary['rejectedCount']==len(neg) and summary['rejectOutputPixels']==0
    return summary,passed


class Journal:
    def __init__(self,root):
        self.root = root; self.sequence = 0; self.steps = 0; self.epochs = 0; self.inputs = 0
        self.in_flight = False; self.started = time.monotonic()
        (root/'events').mkdir()

    def event(self,phase,**extra):
        self.sequence += 1
        value = {'sequence':self.sequence,'phase':phase,'confirmedOptimizerSteps':self.steps,
                 'completedEpochs':self.epochs,'modelInputsStarted':self.inputs,'optimizerStepInFlight':self.in_flight,
                 'elapsedSeconds':time.monotonic()-self.started,**extra}
        d.new(self.root/'events'/f'{self.sequence:06d}.json',value)
        return value

    def terminal(self,phase,**extra):
        value = self.event(phase,**extra); d.new(self.root/'terminal.json',value)


def failure(root,journal,error,model=None,optimizer=None):
    checkpoint = None; checkpoint_error = None
    if model is not None:
        try:
            path = root/'termination-checkpoint.pt'
            with path.open('xb') as stream:
                torch.save({'model':model.state_dict(),'optimizer':optimizer.state_dict() if optimizer else None,
                            'confirmedOptimizerSteps':journal.steps,'completedEpochs':journal.epochs,
                            'use':'forensic_no_resume_authority'},stream); stream.flush(); os.fsync(stream.fileno())
            checkpoint = d.bind(path)
        except BaseException as problem: checkpoint_error = str(problem)
    d.new(root/'termination-report.json',{'type':type(error).__name__,'message':str(error),'traceback':traceback.format_exc(),
          'confirmedOptimizerSteps':journal.steps,'completedEpochs':journal.epochs,'modelInputsStarted':journal.inputs,
          'optimizerStepInFlight':journal.in_flight,'checkpoint':checkpoint,'checkpointError':checkpoint_error,'resumeAllowed':False})
    journal.terminal('failed')


def preflight(plan_path,root):
    plan,data,rows,net,band,metric,guard,cleanup = resources(plan_path)
    model = None
    try:
        root.mkdir(parents=True,exist_ok=False); journal = Journal(root)
        d.new(root/'attempt.json',{'plan':d.bind(plan_path),'stage':'preflight','attemptConsumed':True,'resumeAllowed':False})
        require(torch.cuda.is_available(),'registered CUDA unavailable')
        samples = load_samples(rows); model = fresh_model(net,'cuda').train(); before = tensors_sha(model); records = []
        d.new(root/'environment.json',environment())
        journal.event('claimed')
        for row,(rgb,coarse,target,positive) in zip(rows,samples,strict=True):
            x = torch.from_numpy(net.pack(rgb,coarse))[None].cuda(); t = torch.from_numpy((target>0).astype(np.float32))[None,None].cuda()
            model.zero_grad(set_to_none=True); journal.inputs += 1; journal.event('preflight_input_started',candidateIdentity=row['candidateIdentity'])
            logits,presence = model(x); loss = objective(logits,presence,t,positive,plan['counts']['train'],band)
            require(logits.dtype==presence.dtype==torch.float32 and logits.shape==t.shape and torch.isfinite(logits).all() and torch.isfinite(presence).all() and torch.isfinite(loss),'finite original heads/loss')
            loss.backward(); named = list(model.named_parameters())
            needed = [(name,p.grad) for name,p in named if positive or name.startswith(('enc1.','enc2.','enc3.','presence.'))]
            unused = [name for name,p in named if not positive and name.startswith(('dec1.','dec2.','delta.'))]
            require(all(g is not None and torch.isfinite(g).all() for _,g in needed),'required branch gradients')
            require(all(p.grad is None for name,p in named if name in unused),'reject decoder gradient')
            records.append({'candidateIdentity':row['candidateIdentity'],'positive':positive,'nativeSize':row['nativeSize'],
                            'loss':float(loss.detach()),'finiteUsedGradientTensors':len(needed),
                            'nonzeroGradientTensors':sum(bool(g.abs().max()>0) for _,g in needed),'expectedUnusedParameters':unused})
            journal.event('preflight_input_confirmed',candidateIdentity=row['candidateIdentity'])
        require(tensors_sha(model)==before,'zero-step weights changed')
        result = {'schemaVersion':1,'ok':True,'decision':'full_train_native_objective_gradients_finite_no_optimizer',
                  'plan':d.bind(plan_path),'records':records,'trainForwardBackwardInputs':len(rows),'optimizerSteps':0,
                  'initialTensorSha256':before,'precision':PRECISION,'initialWeightsUnchanged':True,
                  'environment':d.bind(root/'environment.json'),
                  'valModelInputs':0,'protectedModelInputs':0,'newChatImageInputs':0,'trainingAllowedByThisStage':True,
                  'formalReleaseAllowed':False,'productHold':True}
        d.new(root/'report.json',result); journal.terminal('closed',preflightOk=True)
        return result
    except BaseException as error:
        if 'journal' in locals(): failure(root,journal,error,model)
        raise
    finally:
        for path in [*cleanup,root]: guard.remove_ultralytics_label_caches(Path(path))


def train(plan_path,preflight_ref,root):
    plan,data,rows,net,band,metric,guard,cleanup = resources(plan_path)
    model = optimizer = None
    try:
        pre = d.read(preflight_ref)
        require(pre['ok'] and pre['plan']==d.bind(plan_path) and pre['optimizerSteps']==0 and [r['candidateIdentity'] for r in pre['records']]==plan['candidateIdentities'],'full preflight gate')
        root.mkdir(parents=True,exist_ok=False); journal = Journal(root); (root/'predictions').mkdir()
        d.new(root/'attempt.json',{'plan':d.bind(plan_path),'preflight':preflight_ref,'attemptConsumed':True,'resumeAllowed':False,'pid':os.getpid()})
        require(torch.cuda.is_available(),'registered CUDA unavailable')
        samples = load_samples(rows); model = fresh_model(net,'cuda').train()
        d.new(root/'environment.json',environment())
        require(tensors_sha(model)==pre['initialTensorSha256'],'fresh initialization reproducibility')
        optimizer = torch.optim.AdamW(model.parameters(),lr=0.0003,weight_decay=0.0001)
        rng = np.random.default_rng(20261015); journal.event('claimed')
        for epoch in range(100):
            lr = 0.00003+0.5*(0.0003-0.00003)*(1+math.cos(math.pi*epoch/99))
            for group in optimizer.param_groups: group['lr'] = lr
            order = rng.permutation(len(samples)).tolist(); total_loss = 0.0
            for start in range(0,len(order),4):
                window = order[start:start+4]; optimizer.zero_grad(set_to_none=True)
                for index in window:
                    rgb,coarse,target,positive = samples[index]
                    choice = {'rotation':int(rng.integers(4)),'flip':bool(rng.integers(2)),
                              'brightness':float(rng.uniform(0.9,1.1)),'contrast':float(rng.uniform(0.9,1.1))}
                    r,c,t = augment(rgb,coarse,target,**choice)
                    x = torch.from_numpy(net.pack(r,c))[None].cuda(); truth = torch.from_numpy((t>0).astype(np.float32))[None,None].cuda()
                    journal.inputs += 1; journal.event('training_input_started',epoch=epoch+1,candidateIdentity=rows[index]['candidateIdentity'],augmentation=choice)
                    logits,presence = model(x); loss = objective(logits,presence,truth,positive,plan['counts']['train'],band)
                    require(torch.isfinite(loss),'finite training loss')
                    (loss/len(window)).backward(); total_loss += float(loss.detach())
                torch.nn.utils.clip_grad_norm_(model.parameters(),1.0,error_if_nonfinite=True)
                journal.in_flight = True; journal.event('optimizer_in_flight',attemptedStep=journal.steps+1)
                optimizer.step(); torch.cuda.synchronize(); journal.steps += 1; journal.in_flight = False; journal.event('optimizer_confirmed')
            journal.epochs = epoch+1; journal.event('epoch_completed',meanLoss=total_loss/len(samples),learningRate=lr)
            if journal.epochs%10==0:
                path = root/f'forensic-epoch-{journal.epochs:03d}.pt'
                with path.open('xb') as stream:
                    torch.save({'model':model.state_dict(),'optimizer':optimizer.state_dict(),'rng':rng.bit_generator.state,
                                'torchRng':torch.get_rng_state(),'cudaRng':torch.cuda.get_rng_state_all(),
                                'completedEpochs':journal.epochs,'confirmedOptimizerSteps':journal.steps,'use':'forensic_no_resume_authority'},stream)
                    stream.flush(); os.fsync(stream.fileno())
            if journal.epochs%5==0: print(json.dumps({'epochs':journal.epochs,'steps':journal.steps,'inputs':journal.inputs,'meanLoss':total_loss/len(samples)}),flush=True)
        require(journal.steps==plan['budget']['optimizerSteps'] and journal.inputs==plan['budget']['augmentedTrainingInputs'],'complete normal training budget')
        model.eval(); records = []; predictions = []; source_sizes = {d.key(s['identity']):s['size'] for s in data['sourceRecords']}
        for row,(rgb,coarse,target,positive) in zip(rows,samples,strict=True):
            journal.inputs += 1; journal.event('final_train_input_started',candidateIdentity=row['candidateIdentity'])
            with torch.inference_mode(): logits,presence = model(torch.from_numpy(net.pack(rgb,coarse))[None].cuda())
            raw = logits[0,0].float().cpu().numpy().copy(); p = np.float32(float(presence[0,0]))
            path = root/'predictions'/f'{row["ordinal"]:03d}.npz'
            with path.open('xb') as stream: np.savez_compressed(stream,logits=raw,presenceLogit=p); stream.flush(); os.fsync(stream.fileno())
            predictions.append(d.bind(path))
            records.append(candidate_metric(row,raw,p,target>0,source_sizes[d.key(row['candidateIdentity']['identity'])],net,metric))
        summary,quality_ok = summarize(records)
        with (root/'final-weights.pt').open('xb') as stream: torch.save(model.state_dict(),stream); stream.flush(); os.fsync(stream.fileno())
        result = {'schemaVersion':1,'ok':True,'decision':'normal_training_complete_train_quality_passed' if quality_ok else 'normal_training_complete_train_quality_failed',
                  'inputs':{'plan':d.bind(plan_path),'preflight':preflight_ref,'weights':d.bind(root/'final-weights.pt')},
                  'metrics':summary,'perCandidate':records,'predictions':predictions,'trainQualityGatePassed':quality_ok,
                  'completedEpochs':journal.epochs,'confirmedOptimizerSteps':journal.steps,'modelInputsStarted':journal.inputs,
                  'augmentedTrainingInputs':plan['budget']['augmentedTrainingInputs'],'finalTrainInferenceInputs':len(rows),
                  'initialization':'fresh_no_prior_weights_or_optimizer','precision':PRECISION,'resumeAllowed':False,
                  'environment':d.bind(root/'environment.json'),
                  'valModelInputs':0,'protectedModelInputs':0,'newChatImageInputs':0,
                  'formalSourceIndependent':False,'formalReleaseAllowed':False,'productHold':True}
        d.new(root/'report.json',result); journal.terminal('closed',trainQualityGatePassed=quality_ok)
        return result
    except BaseException as error:
        if 'journal' in locals(): failure(root,journal,error,model,optimizer)
        raise
    finally:
        for path in [*cleanup,root]: guard.remove_ultralytics_label_caches(Path(path))


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--plan',type=Path,required=True)
    parser.add_argument('--preflight-output',type=Path); parser.add_argument('--preflight',type=Path); parser.add_argument('--output',type=Path)
    args = parser.parse_args()
    if args.preflight_output: result = preflight(args.plan.resolve(),args.preflight_output.resolve())
    else: result = train(args.plan.resolve(),d.bind(args.preflight),args.output.resolve())
    print(json.dumps({k:result[k] for k in ('ok','decision','optimizerSteps') if k in result}|{'trainQualityGatePassed':result.get('trainQualityGatePassed')},ensure_ascii=False))


if __name__=='__main__': main()
