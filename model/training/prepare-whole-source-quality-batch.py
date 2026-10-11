"""整图批量审核准备：完整旧证据验真、角色不变、图片不改写。"""
import argparse,hashlib,importlib.util,json,os,sys
from pathlib import Path
R=Path(__file__).resolve().parents[2]
def bind(p):
 p=Path(p).resolve();assert p.is_file();return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def read(ref):assert bind(ref['path'])==ref;return json.loads(Path(ref['path']).read_bytes())
def module(name,file):
 sp=importlib.util.spec_from_file_location(name,R/'model/training'/file);m=importlib.util.module_from_spec(sp);sys.modules[name]=m;sp.loader.exec_module(m);return m
def key(row):return tuple(row['identity'][k] for k in ('split','fileName','imageSha256'))
def build(refs):
 plan=read(refs['plan']);pol=read(plan['inputs']['humanPolicy']);e=read(plan['inputs']['currentEligibility']);a=read(plan['inputs']['readiness']);reg=read(plan['inputs']['registry']);roles=read(refs['roles']);guard=read(refs['guard'])
 assert pol['wholeImageOnly'] and pol['newCropTileOrMontageInputsProhibited'] and plan['sourceCount']<=pol['batchSourceCount']
 allowed={key(x):x for x in e['currentQualityEligibleInventory']};seen={key(read(x)) for x in e['qualityReviewBindings']};ready={key(x):x for x in a['records']};selected=plan['selectedSources'];ordered=sorted([x for k,x in ready.items() if k in set(allowed)-seen],key=lambda x:(x['minimumNativeNailShortSidePixels'],x['minimumNativeNailAreaPixels'],x['identity']['split'],x['identity']['fileName'],x['identity']['imageSha256']))
 assert [key(x) for x in selected]==[key(x) for x in ordered[:len(selected)]] and len({key(x) for x in selected})==len(selected)
 layout=module('whole_batch_layout','native-source-page-layout.py');reuse=module('whole_batch_reuse','native-source-view-reuse.py');records=[]
 with layout.guarded_pixels(guard):
  for x in selected:
   identity=x['identity'];r=ready[key(x)];oldrow=allowed[key(x)];role=next(z for z in roles['records'] if z['identity']==identity)
   assert x['source']==oldrow['sourceImage']==r['source'] and x['annotation']==oldrow['annotation']==r['annotation'] and x['maskCount']==oldrow['maskCount']==r['maskCount'] and x['sourceGroup']==role['sourceGroup']
   truth=role['currentTruth'] if identity['split']=='train' else next(z for z in roles['currentInternalValTruthRecords'] if z['identity']==identity)
   assert truth['annotation']==x['annotation'] and bind(x['annotation']['path'])==x['annotation'] and not role['formalTrainingApproved'] and role['trainingUse']=='prohibited'
   oldpages=[];oldrgb=None
   if x['priorActualView']:
    view=next(z for z in reg['images'] if z['imageSha256']==identity['imageSha256']);assert view['actualView']==x['priorActualView'];old=read(view['actualView']);prior=read(old['inputs']['reviewReport']);im=next(z for z in prior['images'] if z['image']['sha256']==identity['imageSha256']);layout.check_pixels(im);reuse.validate_record(view['actualView'],im);oldpages=im['pages'];oldrgb=im['originalRgbSha256']
   else:assert not any(z['imageSha256']==identity['imageSha256'] for z in reg['images'])
   raw=layout.load_rgb(x['source']);w,h=raw.size;digest=hashlib.sha256(raw.tobytes()).hexdigest();assert [w,h]==r['size'] and (oldrgb is None or digest==oldrgb)
   size=Path(x['source']['path']).stat().st_size;assert size==x['fileBytes']<=pol['singleImageFileAndPayloadLimitBytes']
   page={'page':x['source'],'size':[w,h],'sourceBox':[0,0,w,h],'pageOrigin':[0,0],'rawRgbSha256':digest,'fileBytes':size,'resampling':False}
   canonical={'imageOrdinal':x['ordinal'],'image':x['source'],'originalSize':[w,h],'originalRgbSha256':digest,'nativeLayout':'whole','pages':[{'page':x['source'],'size':[w,h],'tiles':[{'sourceBox':[0,0,w,h],'pageOrigin':[0,0],'rawRgbSha256':digest}],'resampling':False}],'sourcePixelCoverage':w*h,'tilePixelCoverage':w*h,'trainingAllowed':False}
   layout.check_pixels(canonical)
   records.append({'ordinal':x['ordinal'],'identity':identity,'source':x['source'],'sourceGroup':x['sourceGroup'],'annotation':x['annotation'],'maskCount':x['maskCount'],'originalSize':[w,h],'originalRgbSha256':digest,'priorView':x['priorActualView'],'priorCanonicalPages':oldpages,'reviewPages':[page],'wholeImage':canonical,'fileBytes':size,'currentRoleRecordSha256':hashlib.sha256(json.dumps(role,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'reviewReason':'旧场景摘要不证明当前纹理可用性，需要一次完整图质量裁决。' if oldpages else '原像素查看库存新缺口，完整图首次实审。','trainingAllowed':False})
 total=sum(x['fileBytes'] for x in records);assert total==plan['originalFileBytes']<=pol['batchImageFileAndPayloadLimitBytes'] and total+plan.get('earlierTaskImageBytes',0)<=pol['turnImageFileAndPayloadLimitBytes']
 return {'schemaVersion':1,'ok':True,'inputs':refs,'writer':bind(__file__),'records':records,'images':[x['wholeImage'] for x in records],'sourceCount':len(records),'imageFileBytesTotal':total,'plannedResponseGroups':plan['modelResponseGroups'],'oldViewRelooks':sum(x['priorView'] is not None for x in records),'newStockImagesPlanned':sum(x['priorView'] is None for x in records),'newStockPagesPlanned':sum(x['priorView'] is None for x in records),'noNewCropsTilesResamplingOrLossyEncoding':True,'qualityDecisionsPending':True,'trainingAllowed':False,'productHold':True}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--plan',type=Path);ap.add_argument('--roles',type=Path);ap.add_argument('--guard',type=Path);ap.add_argument('--output',type=Path);ap.add_argument('--verify-report',type=Path);args=ap.parse_args()
 if args.verify_report:
  old=json.loads(args.verify_report.read_bytes());assert build(old['inputs'])==old;result=old
 else:
  assert args.plan and args.roles and args.guard and args.output;result=build({k:bind(getattr(args,k)) for k in ['plan','roles','guard']})
  with args.output.open('xb') as f:f.write((json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode());f.flush();os.fsync(f.fileno())
 print(json.dumps({'ok':True,'sources':result['sourceCount'],'fileBytes':result['imageFileBytesTotal'],'oldRelooks':result['oldViewRelooks'],'newStockPlanned':result['newStockImagesPlanned']},ensure_ascii=False))
if __name__=='__main__':main()
