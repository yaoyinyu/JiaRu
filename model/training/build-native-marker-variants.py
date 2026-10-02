"""在已复审完整mask之外构建原像素标记对照；不调用模型或批准训练。"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def bind(p): return {'path': str(Path(p).resolve()), 'sha256': sha(p)}
def checked(ref):
    p = Path(ref['path']).resolve()
    if not p.is_file() or sha(p) != ref['sha256']: raise ValueError('binding mismatch: '+str(p))
    return p
def read(ref): return json.loads(checked(ref).read_text(encoding='utf-8'))
def module(ref, name):
    p = checked(ref); sys.path.insert(0,str(p.parent))
    spec = importlib.util.spec_from_file_location(name,p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m
def boxes(w,h):
    return {'badgeBox':[w-56,h-42,w-4,h-4], 'blankControlBox':[w-128,h-42,w-76,h-4],
            'relocationBox':[w-200,h-42,w-148,h-4]}
def validate_boxes(row,w,h,protected):
    import numpy as np
    keys = ('badgeBox','blankControlBox','relocationBox')
    regions = []
    for key in keys:
        x1,y1,x2,y2 = row[key]
        if not (0 <= x1 < x2 <= w and 0 <= y1 < y2 <= h): raise ValueError('window outside source')
        if protected[y1:y2,x1:x2].any(): raise ValueError('window touches protected nail pixels')
        regions.append((x2-x1,y2-y1))
    if len(set(regions)) != 1: raise ValueError('matched control window size mismatch')
    for i,k in enumerate(keys):
        a = row[k]
        for j in keys[i+1:]:
            b = row[j]
            if min(a[2],b[2]) > max(a[0],b[0]) and min(a[3],b[3]) > max(a[1],b[1]):
                raise ValueError('control windows overlap')
def raster(document,size):
    from PIL import Image, ImageDraw
    import numpy as np
    im = Image.new('L',size); draw = ImageDraw.Draw(im)
    for a in document['annotations']: draw.polygon([(p['x'],p['y']) for p in a['polygon']], fill=255)
    return np.asarray(im)>0
def png(output,name,image,verify):
    from PIL import Image
    p = output / (name+'.png')
    if verify:
        with Image.open(checked(bind(p))) as im:
            if im.mode!='RGB' or im.size!=image.size or im.tobytes()!=image.tobytes(): raise ValueError('pixel reconstruction mismatch')
    else:
        with p.open('xb') as f: image.save(f,format='PNG')
    return bind(p)
def panel(output,name,images,verify):
    from PIL import Image, ImageDraw
    # Two columns, exactly native pixels, no interpolation.
    widths = [im.width for _,im in images]; heights = [im.height for _,im in images]
    cell_w,cell_h=max(widths),max(heights)+26
    page=Image.new('RGB',(cell_w*2+12,cell_h*((len(images)+1)//2)),'white')
    draw=ImageDraw.Draw(page)
    for i,(title,im) in enumerate(images):
        x=(i%2)*(cell_w+12); y=(i//2)*cell_h
        draw.text((x,y+3),title,fill='black');page.paste(im,(x,y+26))
    if max(page.size)>900: raise ValueError('review page would be resized')
    return png(output,name,page,verify)


def build(execution_ref,output,verify=False,windows_only=False):
    execution=read(execution_ref); inputs=execution['inputs']
    if checked(inputs['runnerSource'])!=Path(__file__).resolve(): raise ValueError('runner identity changed')
    guard=module(inputs['readOnlyGuard'],'marker_guard');guard.install_read_only_ultralytics_image_check()
    from PIL import Image, ImageFilter, ImageDraw
    import numpy as np
    import cv2
    try:
        scope=read(inputs['scope']);baseline=read(scope['inputs']['manualMaskDisposition'])
        approved={d['ordinal']:d for d in baseline['sourceDispositions']}
        if not windows_only and output.exists() and not verify: raise FileExistsError(output)
        if windows_only and output.exists() and not verify: raise FileExistsError(output)
        manifest=read(inputs['windowDecisions']) if not windows_only else None
        if manifest and manifest['inputs']['scope']!=inputs['scope']: raise ValueError('window scope identity mismatch')
        if manifest and [r['ordinal'] for r in manifest['sources']] != [s['ordinal'] for s in scope['sources']]:
            raise ValueError('complete window source denominator changed')
        if not verify: output.mkdir(parents=True)
        records=[]
        for index,s in enumerate(scope['sources']):
            d=approved[s['ordinal']]
            if d['decision']!='mask_visual_pass_pending_role_and_marker_gates' or d['failedNailIndices']: raise ValueError('mask not visually approved')
            for k in ('fileName','sourceGroup','sourceImage','sourceLabel','annotation','completeVisibleNails'):
                if s[k]!=d[k]:raise ValueError('scope mask identity drift')
            checked(s['sourceLabel']);doc=read(s['annotation'])
            if len(doc['annotations'])!=s['completeVisibleNails']:raise ValueError('mask denominator changed')
            with Image.open(checked(s['sourceImage'])) as opened: im=opened.convert('RGB')
            w,h=im.size;nails=raster(doc,im.size)
            protected=cv2.dilate(nails.astype(np.uint8),np.ones((21,21),np.uint8))>0
            row=boxes(w,h) if windows_only else manifest['sources'][index]
            validate_boxes(row,w,h,protected)
            corner_box=[max(0,w-260),max(0,h-170),w,h]
            if windows_only:
                raw=im.crop(corner_box); overlay=raw.copy();draw=ImageDraw.Draw(overlay)
                for key,color in [('badgeBox','red'),('blankControlBox','blue'),('relocationBox','orange')]:
                    x1,y1,x2,y2=row[key];draw.rectangle([x1-corner_box[0],y1-corner_box[1],x2-corner_box[0]-1,y2-corner_box[1]-1],outline=color)
                page=panel(output,f"source-{s['ordinal']:03d}-window-review",[('original lower-right',raw),('red badge / blue blank / orange move',overlay)],verify)
                records.append({**s,**row,'imageSize':[w,h],'cornerBox':corner_box,'page':page,'protectedWindowPixels':0})
                continue
            for k in ('fileName','sourceImage','annotation'):
                if row[k]!=s[k]:raise ValueError('window source identity mismatch')
            if row['decision']!='original_pixel_windows_confirmed' or row['trainingUse']!='prohibited':raise ValueError('windows not manually approved')
            arr=np.asarray(im);variants={'original':im.copy()};variant_meta={}
            cw,ch=round(w*.88),round(h*.88)
            crop=im.crop((0,0,cw,ch));variants['crop12_native']=crop
            cropped_nails=int(nails.sum()-nails[:ch,:cw].sum());cropped_guard=int(protected.sum()-protected[:ch,:cw].sum())
            variant_meta['crop12_native']={'cropBox':[0,0,cw,ch],'nailPixelsLost':cropped_nails,'protectedPixelsLost':cropped_guard,
                                           'mapping':'original=local+[0,0]; native pixels, no resize'}
            blur=im.copy();blur_box=[round(w*.8),round(h*.8),w,h]
            blur.paste(im.crop(blur_box).filter(ImageFilter.GaussianBlur(max(12,round(min(im.size)*.02)))),blur_box[:2])
            variants['blur_corner']=blur
            badge=np.zeros((h,w),np.uint8);blank=badge.copy()
            x1,y1,x2,y2=row['badgeBox'];badge[y1:y2,x1:x2]=255
            bx1,by1,bx2,by2=row['blankControlBox'];blank[by1:by2,bx1:bx2]=255
            removed=cv2.inpaint(arr,badge,9,cv2.INPAINT_TELEA)
            control=cv2.inpaint(arr,blank,9,cv2.INPAINT_TELEA)
            occluded=arr.copy();occluded[badge>0]=np.median(arr[blank>0],axis=0).astype(np.uint8)
            blank_occluded=arr.copy();blank_occluded[blank>0]=np.median(arr[blank>0],axis=0).astype(np.uint8)
            moved=removed.copy();mx1,my1,mx2,my2=row['relocationBox']
            # Raw badge is visibly transferred; release/quality gates still require visual interpretability.
            moved[my1:my2,mx1:mx2]=arr[y1:y2,x1:x2]
            variants.update(remove=Image.fromarray(removed),blank_remove_control=Image.fromarray(control),
                            occlude=Image.fromarray(occluded),blank_occlude_control=Image.fromarray(blank_occluded),
                            move_marker=Image.fromarray(moved))
            refs={}
            for name,image in variants.items():
                if name=='crop12_native':
                    changed_nails=cropped_nails;changed_guard=cropped_guard
                else:
                    changed=np.any(np.asarray(image)!=arr,axis=2)
                    changed_nails=int((changed&nails).sum());changed_guard=int((changed&protected).sum())
                    if name not in ('original','blur_corner') and not changed.any(): raise ValueError('local control unchanged')
                    if changed_nails or changed_guard: raise ValueError('variant modifies protected nail pixels: '+name)
                    variant_meta[name]={'nailPixelsChanged':changed_nails,'protectedPixelsChanged':changed_guard,
                                        'changedPixels':int(changed.sum()),'pixelMapping':'identity_original_coordinates'}
                refs[name]=png(output,f"source-{s['ordinal']:03d}-{name}",image,verify)
            views=[]
            names=['original','remove','blank_remove_control','occlude','blank_occlude_control','move_marker','blur_corner']
            for offset in (0,4):
                entries=[(name,variants[name].crop(corner_box)) for name in names[offset:offset+4]]
                views.append(panel(output,f"source-{s['ordinal']:03d}-corner-controls-{offset}",entries,verify))
            records.append({**s,**{k:row[k] for k in ('badgeBox','blankControlBox','relocationBox')},'imageSize':[w,h],
                            'cornerBox':corner_box,'variants':refs,'variantPixelEvidence':variant_meta,'reviewPages':views,
                            'cropDiagnosticEligible':cropped_nails==0 and cropped_guard==0,
                            'visualUsability':'pending_original_pixel_review'})
        return {'schemaVersion':1,'ok':True,'decision':'native_marker_windows_pending_visual_review' if windows_only else 'native_marker_variants_built_visual_review_pending',
                'execution':execution_ref,'inputs':inputs,'records':records,
                'counts':{'sourceImages':len(records),'completeVisibleNails':sum(r['completeVisibleNails'] for r in records),
                          'sourceGroups':len({r['sourceGroup'] for r in records})},
                'modelCalls':0,'optimizerSteps':0,'formalTrainingApprovedImages':0,'trainingAllowed':False,'full30PilotAllowed':False}
    finally:guard.remove_ultralytics_label_caches(Path(execution['datasetRoot']))


def main():
    p=argparse.ArgumentParser();p.add_argument('--execution',type=Path);p.add_argument('--output',type=Path)
    p.add_argument('--windows-only',action='store_true');p.add_argument('--verify-report',type=Path)
    args=p.parse_args()
    if args.verify_report:
        report=json.loads(args.verify_report.read_text(encoding='utf-8'))
        windows=report['decision']=='native_marker_windows_pending_visual_review'
        if build(report['execution'],args.verify_report.parent,verify=True,windows_only=windows)!=report:raise ValueError('report reconstruction mismatch')
        print(json.dumps({'ok':True,'decision':'native_marker_replay_identical'}))
    else:
        if not args.execution or not args.output:p.error('--execution and --output required')
        report=build(bind(args.execution),args.output,windows_only=args.windows_only)
        out=args.output/'marker-report.json'
        with out.open('x',encoding='utf-8') as f:f.write(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({k:report[k] for k in ('ok','decision','counts')}))
if __name__=='__main__':main()
