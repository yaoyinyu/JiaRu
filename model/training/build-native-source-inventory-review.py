"""按冻结图片库存生成完整RAW原像素审核页；不生成来源或mask资格。"""
import argparse
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from PIL import Image, ImageDraw

def bind(path):
    path=Path(path).resolve();return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
def read(ref):
    if bind(ref['path'])!=ref:raise ValueError('reconstruction_mismatch: '+ref['path'])
    return json.loads(Path(ref['path']).read_bytes())
def freeze(path,value):
    with path.open('xb') as f:f.write((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode());f.flush();os.fsync(f.fileno())

def build(manifest_path,plan_path,out):
    manifest_ref=bind(manifest_path);manifest=read(manifest_ref);plan_ref=bind(plan_path);plan=read(plan_ref)
    inventory=read(plan['inputs']['referenceInventory']);sources=manifest['sources']
    hashes=[r['image']['sha256'] for r in sources]
    if not sources or len(set(hashes))!=len(hashes):raise ValueError('empty or duplicate source inventory')
    for row in sources:
        if bind(row['image']['path'])!=row['image']:raise ValueError('source SHA drift before pixels')
    guard_ref=plan['inputs']['readOnlyGuard']
    if bind(guard_ref['path'])!=guard_ref:raise ValueError('guard binding drift')
    path=Path(guard_ref['path']);sys.path.insert(0,str(path.parent));sp=importlib.util.spec_from_file_location('source_inventory_guard',path)
    guard=importlib.util.module_from_spec(sp);sys.modules[sp.name]=guard;sp.loader.exec_module(guard);guard.install_read_only_ultralytics_image_check()
    roots=[Path(read(inventory['inputs'][k])['outputDir']) for k in ('cycle012Materialization','cleanDevelopmentEvaluation')]
    out.mkdir(exist_ok=False);(out/'pages').mkdir();images=[]
    try:
        for number,row in enumerate(sources,1):
            with Image.open(row['image']['path']) as im:im.load();raw=im.convert('RGB')
            w,h=raw.size
            if list(raw.size)!=row['originalSize']:raise ValueError('source dimensions drift')
            tiles=[(x,y,min(w,x+660),min(h,y+800)) for y in range(0,h,800) for x in range(0,w,660)];pages=[]
            for part in range(0,len(tiles),2):
                boxes=tiles[part:part+2];page=Image.new('RGB',(sum(b[2]-b[0] for b in boxes)+8*(len(boxes)-1),40+max(b[3]-b[1] for b in boxes)),'#222222');draw=ImageDraw.Draw(page);offset=0;layout=[]
                for box in boxes:
                    crop=raw.crop(box);page.paste(crop,(offset,40));draw.text((offset+4,4),f'I{number:03d} RAW {box}',fill='white')
                    if page.crop((offset,40,offset+crop.width,40+crop.height)).tobytes()!=crop.tobytes():raise ValueError('RAW pixel mismatch')
                    layout.append({'sourceBox':list(box),'pageOrigin':[offset,40],'rawRgbSha256':hashlib.sha256(crop.tobytes()).hexdigest()});offset+=crop.width+8
                p=out/'pages'/f'image-{number:03d}-page-{part//2+1:02d}.png';page.save(p);pages.append({'page':bind(p),'size':list(page.size),'tiles':layout,'resampling':False})
            images.append({'imageOrdinal':number,'image':row['image'],'originalSize':[w,h],'originalRgbSha256':hashlib.sha256(raw.tobytes()).hexdigest(),
                           'pages':pages,'sourcePixelCoverage':w*h,'tilePixelCoverage':sum((b[2]-b[0])*(b[3]-b[1]) for b in tiles),'nativeViewed':False})
        report={'schemaVersion':1,'inputs':{'manifest':manifest_ref,'plan':plan_ref,'writer':bind(Path(__file__))},'images':images,
                'counts':{'uniqueImages':len(images),'nativePages':sum(len(i['pages']) for i in images)},'pixelFidelityOk':True,'nativeVisualApproved':False,
                'scope':'full_original_pixels_only_not_source_independence_or_mask_approval','trainingAllowed':False}
        freeze(out/'report.json',report);print(json.dumps({'report':bind(out/'report.json'),'counts':report['counts']}))
    finally:
        for root in roots:guard.remove_ultralytics_label_caches(root)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',type=Path,required=True);parser.add_argument('--plan',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();build(args.manifest,args.plan,args.output)
