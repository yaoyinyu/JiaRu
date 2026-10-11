"""严格重放整图/继承分块及实际查看绑定，不因像素一致批准视觉。"""
import argparse,importlib.util,json,sys
from pathlib import Path
R=Path(__file__).resolve().parents[2]
def module(n,p):
 sp=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(sp);sys.modules[n]=m;sp.loader.exec_module(m);return m
layout=module('whole_audit_layout',R/'model/training/native-source-page-layout.py');legacy=module('whole_audit_legacy',R/'model/training/audit-native-source-review-pages.py');reuse=module('whole_audit_reuse',R/'model/training/native-source-view-reuse.py')
def run(p):
 ref=layout.bind(p);r=layout.read(ref);assert r['schemaVersion']==3 and not r['trainingAllowed'] and not r['sourceParentIndependenceQualified'] and not r['nativeVisualApproved'];assert len({i['image']['sha256'] for i in r['images']})==len(r['images'])
 for binding in r['inputs'].values():layout.checked(binding)
 current=old=newpages=oldpages=pixels=0
 with layout.guarded_pixels(r):
  for im in r['images']:
   pixels+=layout.check_pixels(im)
   if im.get('inheritedActualView'):
    record=reuse.validate_record(im['inheritedActualView'],im);prior=layout.read(record['inputs']['reviewReport']);original=next(i for i in prior['images'] if i['image']['sha256']==im['image']['sha256']);assert im['nativeLayout']==original.get('nativeLayout','tiles');old+=1;oldpages+=len(im['pages'])
   else:
    record=json.loads((p.parent/'actual-native'/f"image-{im['imageOrdinal']:03d}.json").read_bytes());legacy.validate_view(record,im,ref)
    for binding in record['inputs'].values():layout.checked(binding)
    current+=1;newpages+=len(im['pages'])
 counts=r['counts'];assert counts['uniqueImages']==current+old and counts['nativePages']==newpages+oldpages and counts['newImagesToView']==current and counts['reusedActualImages']==old and counts['newPagesToView']==newpages and counts['reusedActualPages']==oldpages
 return {'ok':True,'meaning':'whole_or_tiles_pixel_and_actual_binding_not_visual_or_training_approval','images':current+old,'nativePages':newpages+oldpages,'sourcePixels':pixels,'currentActuallyViewedImages':current,'inheritedCompleteViewImages':old,'currentActuallyViewedPages':newpages,'inheritedCompleteViewPages':oldpages,'evidenceCoveredImages':current+old,'sourceParentIndependenceQualified':False,'trainingAllowed':False}
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--report',type=Path,required=True);x=a.parse_args();print(json.dumps(run(x.report.resolve()),ensure_ascii=False))
