"""新图片默认整图无重采样页；继承原证据布局，保留冻结分块回退。"""
import argparse,importlib.util,json,sys
from pathlib import Path
R=Path(__file__).resolve().parents[2]
def module(n,p):
 sp=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(sp);sys.modules[n]=m;sp.loader.exec_module(m);return m
legacy=module('whole_build_legacy',R/'model/training/build-native-source-pair-review-v2.py');layout=module('whole_page_layout',R/'model/training/native-source-page-layout.py')
def build(queue,plan,out,targets,registry,tile_hashes=()):
 legacy.build(queue,plan,out,targets,registry);p=out/'report.json';old=out/'tile-pages-report.json';p.rename(old);r=json.loads(old.read_bytes());fresh={i['image']['sha256'] for i in r['images'] if not i.get('inheritedActualView')};assert set(tile_hashes)<=fresh
 r['inputs'].update({'tilePagesReport':layout.bind(old),'writerV3':layout.bind(Path(__file__)),'wholeLayoutHelper':layout.bind(R/'model/training/native-source-page-layout.py')})
 with layout.guarded_pixels(r):
  for im in r['images']:
   if im.get('inheritedActualView'):
    record=layout.read(im['inheritedActualView']);prior=layout.read(record['inputs']['reviewReport']);original=next(i for i in prior['images'] if i['image']['sha256']==im['image']['sha256']);im['nativeLayout']=original.get('nativeLayout','tiles');continue
   im['tileFallbackPages']=im['pages'];im['nativeLayout']='tiles' if im['image']['sha256'] in tile_hashes else 'whole'
   if im['nativeLayout']=='whole':im['pages']=[layout.whole_page(im,out/'pages'/f"image-{im['imageOrdinal']:03d}-whole.png")]
   layout.check_pixels(im)
 r['schemaVersion']=3;r['wholeImagePreferred']=True;r['toolScalingMustBeChecked']=True;r['counts']['nativePages']=sum(len(i['pages']) for i in r['images']);r['counts']['newPagesToView']=sum(len(i['pages']) for i in r['images'] if not i.get('inheritedActualView'))
 legacy.legacy.write(p,r);print(json.dumps({'report':layout.bind(p),'counts':r['counts'],'images':[{'ordinal':i['imageOrdinal'],'mode':i['nativeLayout'],'reused':bool(i.get('inheritedActualView')),'pages':[p['page']['path'] for p in i['pages']]} for i in r['images']]},ensure_ascii=False))
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--queue',type=Path,required=True);a.add_argument('--plan',type=Path,required=True);a.add_argument('--output',type=Path,required=True);a.add_argument('--target-sha',action='append',required=True);a.add_argument('--native-registry',type=Path,required=True);a.add_argument('--tile-sha',action='append',default=[]);x=a.parse_args();build(x.queue.resolve(),x.plan.resolve(),x.output.resolve(),x.target_sha,x.native_registry.resolve(),x.tile_sha)
