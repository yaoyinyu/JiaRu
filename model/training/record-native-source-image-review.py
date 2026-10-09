"""持久化调用者实际目视的完整原像素图片页；绝不按页生成批准。"""
import argparse,hashlib,json,os
from pathlib import Path
def bind(p):return {'path':str(p.resolve()),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def record(report_path,entry_path):
 report=json.loads(report_path.read_bytes());entry=json.loads(entry_path.read_bytes());images=[i for i in report['images'] if i['imageOrdinal']==entry['imageOrdinal']];assert len(images)==1;image=images[0];expected={Path(p['page']['path']).name:p for p in image['pages']};assert set(entry['viewedPageNames'])==set(expected) and len(entry['viewedPageNames'])==len(expected)
 assert entry['actuallyViewed'] and entry['toolScalingNotice'] is False and entry['coordinateOriginsChecked'] and entry['nativeContentSummary']
 assert bind(Path(image['image']['path']))==image['image']
 for page in expected.values():assert bind(Path(page['page']['path']))==page['page'] and page['resampling'] is False
 obj={'schemaVersion':1,'inputs':{'reviewReport':bind(report_path),'writer':bind(Path(__file__)),'entry':bind(entry_path)},'image':image['image'],'originalSize':image['originalSize'],'pages':[expected[n] for n in entry['viewedPageNames']],'decision':entry,'reviewer':'Codex','scope':'original_pixel_source_content_description_only_not_mask_or_independence_approval','trainingAllowed':False};out=report_path.parent/'actual-native';out.mkdir(exist_ok=True);p=out/f"image-{entry['imageOrdinal']:03d}.json"
 with p.open('xb') as f:f.write((json.dumps(obj,ensure_ascii=False,indent=2)+'\n').encode('utf-8'));f.flush();os.fsync(f.fileno())
 print(json.dumps({'record':bind(p),'actuallyViewedPages':len(expected),'imageOrdinal':entry['imageOrdinal']},ensure_ascii=False))
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--report',type=Path,required=True);ap.add_argument('--entry',type=Path,required=True);a=ap.parse_args();record(a.report.resolve(),a.entry.resolve())
