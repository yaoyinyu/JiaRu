"""新版完整建页在新报告继承已有完整原像素页，保留原建页字节证据。"""
import argparse,hashlib,importlib.util,json,os,sys
from pathlib import Path
def module(name,path):
 sp=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(sp);sys.modules[name]=m;sp.loader.exec_module(m);return m
R=Path(__file__).resolve().parents[2];legacy=module('native_build_v1_frozen',R/'model/training/build-native-source-pair-review.py');reuse=module('native_reuse',R/'model/training/native-source-view-reuse.py')
def build(queue,plan,out,targets,registry_path):
 registry_ref=legacy.bind(registry_path);registry=reuse.read(registry_ref);assert registry['trainingAllowed'] is False;by={r['imageSha256']:r for r in registry['images']};assert len(by)==len(registry['images'])
 legacy.build(queue,plan,out,targets);generated=out/'generated-pages-report.json';original=out/'report.json';assert original.is_file() and not generated.exists();original.rename(generated);report=json.loads(generated.read_bytes());report['inputs'].update({'generatedPagesReport':legacy.bind(generated),'nativeViewRegistry':registry_ref,'reuseHelper':legacy.bind(R/'model/training/native-source-view-reuse.py'),'writerV2':legacy.bind(Path(__file__))});reused=0
 for image in report['images']:
  digest=image['image']['sha256']
  if digest not in by:continue
  registered=by[digest];assert registered['originalSize']==image['originalSize'] and registered['originalRgbSha256']==image['originalRgbSha256']
  oldpages=image['pages'];image['pages']=registered['pages'];reuse.validate_record(registered['actualView'],image);image['inheritedActualView']=registered['actualView'];image['generatedUnusedPages']=oldpages;image['nativeViewed']=False;image['imageOnlyInheritedNotNewPairDecision']=True;reused+=1
 report['schemaVersion']=2;report['counts'].update({'reusedActualImages':reused,'reusedActualPages':sum(len(i['pages']) for i in report['images'] if 'inheritedActualView' in i),'newImagesToView':len(report['images'])-reused,'newPagesToView':sum(len(i['pages']) for i in report['images'] if 'inheritedActualView' not in i)})
 legacy.write(original,report);print(json.dumps({'report':legacy.bind(original),'counts':report['counts'],'images':[{'ordinal':i['imageOrdinal'],'sha':i['image']['sha256'][:12],'size':i['originalSize'],'pages':len(i['pages']),'reused':'inheritedActualView' in i} for i in report['images']]},ensure_ascii=False))
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--queue',type=Path,required=True);ap.add_argument('--plan',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--target-sha',action='append',required=True);ap.add_argument('--native-registry',type=Path,required=True);a=ap.parse_args();build(a.queue.resolve(),a.plan.resolve(),a.output.resolve(),a.target_sha,a.native_registry.resolve())
