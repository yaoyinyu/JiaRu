"""复用精确图片身份的完整实审页；只继承图片证据，不继承图对或角色资格。"""
import hashlib,json
from pathlib import Path
def checked(ref):
 p=Path(ref['path']);assert p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==ref['sha256'],'reconstruction_mismatch: inherited binding';return p
def read(ref):return json.loads(checked(ref).read_bytes())
def validate_record(ref,image):
 record=read(ref);prior=read(record['inputs']['reviewReport']);matches=[r for r in prior['images'] if r['image']['sha256']==image['image']['sha256']];assert len(matches)==1
 original=matches[0];d=record['decision'];assert d['actuallyViewed'] is True and d['toolScalingNotice'] is False and d['coordinateOriginsChecked'] is True and d['nativeContentSummary'];assert record['trainingAllowed'] is False
 assert record['image']['sha256']==image['image']['sha256']==original['image']['sha256'];checked(image['image']);checked(record['image'])
 assert record['originalSize']==original['originalSize']==image['originalSize'];assert original['originalRgbSha256']==image['originalRgbSha256']
 assert record['pages']==original['pages'] and len(record['pages'])==len(image['pages']);assert {p['page']['sha256'] for p in record['pages']}=={p['page']['sha256'] for p in image['pages']}
 for pg in record['pages']:checked(pg['page']);assert pg['resampling'] is False
 return record
