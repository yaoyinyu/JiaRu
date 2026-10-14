"""复用冻结训练循环的去增强对照；仅替换输入应用，保留全部RNG消费。"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
d=module(HERE/'reviewed-role-development-data.py','augmentation_control_data')
base=module(HERE/'train-reviewed-stage-b-normal-development.py','augmentation_control_base')
require=base.require
fresh_model=base.fresh_model
tensors_sha=base.tensors_sha
candidate_metric=base.candidate_metric
summarize=base.summarize
IDENTITY={'rotation':0,'flip':False,'brightness':1.,'contrast':1.}
AUGMENTATION={'spatial':'identity','resampling':False,'brightnessRange':[1.,1.],'contrastRange':[1.,1.],'originalMarkersRetained':True}

def choice(rng):
    return {'rotation':int(rng.integers(4)),'flip':bool(rng.integers(2)),
            'brightness':float(rng.uniform(.9,1.1)),'contrast':float(rng.uniform(.9,1.1))}

def identity_augment(rgb,coarse,target,rotation,flip,brightness,contrast):
    require(rotation in (0,1,2,3) and isinstance(flip,bool) and .9<=brightness<=1.1 and .9<=contrast<=1.1,'baseline RNG choice')
    require(rgb.dtype==coarse.dtype==target.dtype==np.uint8 and rgb.shape[:2]==coarse.shape==target.shape,'native control domain')
    return tuple(x.copy() for x in (rgb,coarse,target))

def pixel_hashes(values):
    return {name:hashlib.sha256(x.tobytes()).hexdigest() for name,x in zip(('nativeRgb','nativeCoarse','nativeTarget'),values,strict=True)}

def validate_plan(plan,baseline,scope):
    require(plan['purpose']=='fresh_stage_b_whole_augmentation_off_single_factor_train_control','control purpose')
    require(scope['purpose']=='single_factor_full_augmentation_pipeline_off_train_fit_control_design_not_training_permission','scope purpose')
    require(plan['inputs']['baselinePlan']==scope['inputs']['baselineNormalPlan'] and plan['inputs']['materialization']==scope['inputs']['nativeMaterialization']==baseline['inputs']['materialization'],'source scope bindings')
    for key in ('counts','candidateIdentities','initialization','precision','loss','training','quality','preflightBudget','budget'):
        require(plan[key]==baseline[key],'unchanged baseline '+key)
    require(plan['candidateIdentities']==scope['candidateIdentities'] and plan['counts']==scope['counts'],'all full source identities')
    require(plan['augmentation']==scope['singleIntervention']['new']==AUGMENTATION and scope['singleIntervention']['baseline']==baseline['augmentation'],'only identity augmentation')
    require(plan['control']=={'factor':'whole_training_augmentation_pipeline','sampleBaselineAugmentationButApplyIdentity':True,
        'rngSeed':20261015,'baselineRngConsumptionAndAllEpochOrdersRequired':True,'baselineWeightsOrOptimizerReadAllowed':False,
        'fixedFinalEpochOnly':True,'oldBudgetsMayResume':False},'control definition')
    require(not plan['formalReleaseAllowed'] and plan['productHold'] and not plan['automaticRestartAllowed'],'release/restart')

def resources(plan_path):
    plan=d.read(d.bind(plan_path))
    for ref in [*plan['inputs'].values(),*plan['sources'].values()]:d.checked(ref)
    require(d.checked(plan['sources']['trainer'])==Path(__file__).resolve(),'control runner identity')
    baseline=d.read(plan['inputs']['baselinePlan']);scope=d.read(plan['inputs']['designScope'])
    validate_plan(plan,baseline,scope)
    require(plan['sources']['baseTrainer']==baseline['sources']['trainer'],'frozen unchanged base trainer')
    audit=d.read(plan['inputs']['baselineReplay']);require(audit['ok'] and not audit['trainQualityGatePassed'] and audit['plan']==plan['inputs']['baselinePlan'],'failed baseline authority')
    _,data,rows,net,band,metric,guard,cleanup=base.resources(Path(plan['inputs']['baselinePlan']['path']))
    return plan,data,rows,net,band,metric,guard,cleanup

def engine(plan_path):
    plan=d.read(d.bind(plan_path));original=module(d.checked(plan['sources']['baseTrainer']),'augmentation_control_engine')
    # 独立加载的训练循环通过显式适配点调用新合同、输入应用和事件记录；不改写冻结源文件。
    original.resources=resources;pending={}
    def apply(*args,**kwargs):
        values=identity_augment(*args,**kwargs);pending['hashes']=pixel_hashes(values)
        return values
    original.augment=apply
    journal_class=original.Journal
    class ControlJournal(journal_class):
        def event(self,phase,**extra):
            if phase=='training_input_started':
                require('hashes' in pending,'input application must precede started event')
                extra.update({'augmentationApplied':IDENTITY,'appliedNativePixelSha256':pending.pop('hashes'),
                    'sampledAugmentationNotApplied':True})
            return super().event(phase,**extra)
    original.Journal=ControlJournal
    return original

def preflight(plan_path,root):return engine(plan_path).preflight(plan_path,root)
def train(plan_path,preflight_ref,root):return engine(plan_path).train(plan_path,preflight_ref,root)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--preflight-output',type=Path);p.add_argument('--preflight',type=Path);p.add_argument('--output',type=Path);a=p.parse_args()
    result=preflight(a.plan.resolve(),a.preflight_output.resolve()) if a.preflight_output else train(a.plan.resolve(),d.bind(a.preflight),a.output.resolve())
    print(json.dumps({'ok':result['ok'],'decision':result['decision'],'trainQualityGatePassed':result.get('trainQualityGatePassed'),'control':'whole_augmentation_off'},ensure_ascii=False))
