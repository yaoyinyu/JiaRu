"""新版像素重放支持精确实审页继承；区别本轮实看与已见证据覆盖。"""
import argparse,hashlib,importlib.util,json,sys
from pathlib import Path
R=Path(__file__).resolve().parents[2]
def module(name,path):
 sp=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(sp);sys.modules[name]=m;sp.loader.exec_module(m);return m
legacy=module('native_pixel_v1',R/'model/training/audit-native-source-review-pages.py');reuse=module('native_view_reuse_v2',R/'model/training/native-source-view-reuse.py')
def run(p):
 report=json.loads(p.read_bytes());ref={'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()};assert report['schemaVersion']==2
 pixel=legacy.run(p,False);current=old=pages=newpages=0
 for item in report['images']:
  if 'inheritedActualView' in item:reuse.validate_record(item['inheritedActualView'],item);old+=1;pages+=len(item['pages'])
  else:
   record=json.loads((p.parent/'actual-native'/f"image-{item['imageOrdinal']:03d}.json").read_bytes());legacy.validate_view(record,item,ref)
   for binding in record['inputs'].values():reuse.checked(binding)
   current+=1;newpages+=len(item['pages'])
 assert current==report['counts']['newImagesToView'] and old==report['counts']['reusedActualImages'] and pages==report['counts']['reusedActualPages'] and newpages==report['counts']['newPagesToView']
 return {**pixel,'actuallyViewedImages':None,'currentActuallyViewedImages':current,'inheritedCompleteViewImages':old,'currentActuallyViewedPages':newpages,'inheritedCompleteViewPages':pages,'evidenceCoveredImages':current+old,'sourceParentIndependenceQualified':False,'trainingAllowed':False}
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--report',type=Path,required=True);a=ap.parse_args();print(json.dumps(run(a.report.resolve()),ensure_ascii=False))
