"""重放原像素纠正头输入合同；只读保存输出，不调用模型或优化器。"""
from __future__ import annotations
import argparse
import importlib.util
from pathlib import Path
import cv2
import numpy as np
from PIL import Image


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


def verify(path):
    core=module('native_parity_core',Path(__file__).with_name('train-conditional-nail-refinement-microfit.py'));a=core.a
    report=a.read(path)
    for binding in report['inputs'].values():a.checked(binding)
    plan=a.read(report['inputs']['diagnosticPlan']['path'])
    guard=module('native_parity_guard',Path(__file__).with_name('train-yolo-seg.py'));guard.install_read_only_ultralytics_image_check()
    try:
        diagnostic=module('native_parity_diagnostic',a.checked(plan['inputs']['auditorSource']))
        h=module('native_parity_head',a.checked(report['inputs']['headSource']))
        accepted=a.read(report['inputs']['diagnosticReport']['path'])
        rebuilt=diagnostic.build(Path(report['inputs']['diagnosticPlan']['path']),path.parent,False)
        for panel in accepted['visualPanels']:a.checked(panel['file'])
        rebuilt['visualPanels']=accepted['visualPanels']
        if rebuilt!=accepted:raise ValueError('reconstruction_mismatch: diagnostic report')
        capacity=a.read(report['inputs']['capacityReport']['path']);capacity_plan=a.read(a.checked(capacity['inputs']['plan']))
        trainer=module('native_parity_trainer',a.checked(capacity_plan['inputs']['trainerSource']));trainer.t.validate=trainer.validate
        records,_=trainer.validate(capacity_plan)
        with np.load(a.checked(capacity['finalLogits']),allow_pickle=False) as saved:
            if saved['candidateIds'].tolist()!=[r['id'] for r in records]:raise ValueError('reconstruction_mismatch: candidate identities')
            logits=saved['logits'].copy()
        rows=[]
        for original,values in zip(records,logits,strict=True):
            probability=(1/(1+np.exp(-np.clip(values,-80,80)))).astype(np.float32)
            base=np.asarray(Image.fromarray(probability).resize(tuple(original['nativeSize']),Image.Resampling.BILINEAR));prediction=base>=.5
            expected_band=cv2.dilate(diagnostic.edge(prediction),np.ones((9,9),np.uint8)).astype(bool)
            with Image.open(a.checked(original['paths']['nativeRgb'])) as image:rgb=np.asarray(image.convert('RGB')).copy()
            with Image.open(a.checked(original['paths']['nativeCoarse'])) as image:coarse=np.asarray(image).copy()
            packed,band=h.pack_native_input(rgb,coarse,base);initial=h.apply_native_delta(base,np.zeros_like(base),band)
            if not np.array_equal(band,expected_band) or not np.array_equal(initial>=.5,prediction):raise ValueError('reconstruction_mismatch: band/initial mask')
            if not np.array_equal(initial[~band].view(np.uint32),base[~band].view(np.uint32)):raise ValueError('outside probability bits')
            if not original['presenceTarget'] and (band.any() or (initial>=.5).any()):raise ValueError('valid empty preservation')
            rows.append({'id':original['id'],'nativeSize':original['nativeSize'],'positive':bool(original['presenceTarget']),
                         'bandPixels':int(band.sum()),'packedShape':list(packed.shape),'bandMatchesWitness':True,
                         'initialMaskMatchesFrozen':True,'outsideProbabilityBitsPreserved':True})
        if rows!=report['perCandidate'] or report['modelCalls']!=0 or report['optimizerSteps']!=0:raise ValueError('reconstruction_mismatch: all45 parity')
        if sum(r['positive'] for r in rows)!=report['positiveCount'] or len(rows)-report['positiveCount']!=report['emptyCount']:raise ValueError('count mismatch')
        print({'ok':True,'decision':'verified_native_input_parity','candidates':len(rows),'modelCalls':0,'optimizerSteps':0,'report':a.bind(path)})
    finally:
        for directory in plan['cacheCleanupRoots']:guard.remove_ultralytics_label_caches(Path(directory))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--verify-report',type=Path,required=True);verify(parser.parse_args().verify_report.resolve())
