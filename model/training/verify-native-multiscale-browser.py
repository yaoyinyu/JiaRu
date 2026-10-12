"""重放真实浏览器原始float32捕获，统一1e-4门不以像素相同放宽数值门。"""
import argparse,importlib.util,json
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
sp=importlib.util.spec_from_file_location('mc_browser_verify_data',HERE/'reviewed-role-development-data.py');d=importlib.util.module_from_spec(sp);sp.loader.exec_module(d)
def build(root):
 static=d.read(d.bind(root/'report.json'));meta=d.read(d.bind(root/'controls.json'));live=d.read(d.bind(root/'browser-capture/live-browser.json'))
 d.checked(static['onnx']);d.checked(static['modelSource'])
 if meta['model']!=static['onnx'] or len(meta['controls'])!=4 or len(live['controls'])!=8 or live['errors']:raise ValueError('browser full control denominator')
 records=[];captured=[]
 for backend in ('wasm','webgpu'):
  for control in meta['controls']:
   h,w=control['h'],control['w'];matching=[r for r in live['controls'] if r['backend']==backend and r['shape']==[h,w]]
   if len(matching)!=1 or matching[0]['dims']!=[1,1,h,w] or matching[0]['presenceDims']!=[1,1]:raise ValueError('browser native shape')
   error=0.;decoded_pixel_difference=0
   for name,count in [('mask',h*w),('presence',1)]:
    ref=control['paths'][name];p=d.checked({'path':ref['path'],'sha256':ref['sha256']})
    if p.name!=ref['file']:raise ValueError('control basename')
    expected=np.fromfile(p,dtype=np.float32);cp=root/'browser-capture'/f'{backend}-{h}x{w}-{name}.bin';actual=np.fromfile(cp,dtype=np.float32)
    if len(actual)!=count or len(expected)!=count or not np.isfinite(actual).all():raise ValueError('captured float32 size/finite')
    error=max(error,float(np.abs(actual-expected).max()));captured.append(d.bind(cp))
    if name=='mask':decoded_pixel_difference=int(((actual>=0)!=(expected>=0)).sum())
   records.append({'backend':backend,'shape':[h,w],'maxAbsoluteDifference':error,'requiredMaximumDifference':1e-4,
                   'numericGatePassed':error<=1e-4,'decodedMaskPixelDifference':decoded_pixel_difference})
 ok=all(r['numericGatePassed'] for r in records)
 return {'schemaVersion':1,'ok':ok,'decision':'all_native_browser_controls_pass_untrained' if ok else 'native_browser_numeric_gate_failed_no_training',
         'inputs':{'static':d.bind(root/'report.json'),'controlManifest':d.bind(root/'controls.json'),'liveBrowser':d.bind(root/'browser-capture/live-browser.json'),'verifier':d.bind(__file__)},
         'records':records,'capturedOutputs':captured,'actualBrowserUserAgent':live['userAgent'],'requiredTolerance':1e-4,
         'trainingBudgetConsumed':False,'formalReleaseAllowed':False,'productHold':True}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--export-dir',type=Path);p.add_argument('--output',type=Path);p.add_argument('--verify-report',type=Path);a=p.parse_args()
 if a.verify_report:
  old=json.loads(a.verify_report.read_bytes());root=Path(old['inputs']['static']['path']).parent;r=build(root)
  if r!=old:raise ValueError('browser report reconstruction_mismatch')
 else:r=build(a.export_dir.resolve());d.new(a.output.resolve(),r)
 print(json.dumps({'ok':r['ok'],'decision':r['decision'],'controls':r['records']}))
