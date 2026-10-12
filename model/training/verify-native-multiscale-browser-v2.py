"""真实双后端两头全有限/存在性判决/完整解码零差核验。"""
import argparse,importlib.util,json
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('browser_complete_data',HERE/'reviewed-role-development-data.py');d=importlib.util.module_from_spec(s);s.loader.exec_module(d)
def compare_outputs(expected_mask,expected_presence,actual_mask,actual_presence,h,w):
 arrays=(expected_mask,expected_presence,actual_mask,actual_presence)
 if any(a.dtype!=np.float32 or a.ndim!=1 for a in arrays) or [a.size for a in arrays]!=[h*w,1,h*w,1]:raise ValueError('float32 native output domain')
 if any(not np.isfinite(a).all() for a in arrays):raise ValueError('reference/captured head nonfinite')
 error=max(float(np.abs(expected_mask-actual_mask).max()),float(np.abs(expected_presence-actual_presence).max()))
 expected_present=bool(expected_presence[0]>=0);actual_present=bool(actual_presence[0]>=0)
 expected=(expected_mask>=0)&expected_present;actual=(actual_mask>=0)&actual_present
 difference=int((expected!=actual).sum())
 return {'maxAbsoluteDifference':error,'requiredMaximumDifference':1e-4,'numericGatePassed':error<=1e-4,
  'decodedMaskPixelDifference':difference,'decodedPixelGatePassed':difference==0,
  'presenceDecisionMatched':expected_present==actual_present,'allReferenceAndCapturedHeadsFinite':True}
def build(root):
 static=d.read(d.bind(root/'report.json'));meta=d.read(d.bind(root/'controls.json'));live=d.read(d.bind(root/'browser-capture/live-browser.json'))
 d.checked(static['onnx']);d.checked(static['modelSource'])
 shapes=[[16,16],[31,37],[128,128],[333,341]]
 if meta['model']!=static['onnx'] or [[a['h'],a['w']] for a in meta['controls']]!=shapes or len(live['controls'])!=8 or live['errors']:raise ValueError('full8 controls contract')
 records=[];captured=[]
 for backend in ('wasm','webgpu'):
  for c in meta['controls']:
   h,w=c['h'],c['w'];matching=[r for r in live['controls'] if r['backend']==backend and r['shape']==[h,w]]
   if len(matching)!=1 or matching[0]['dims']!=[1,1,h,w] or matching[0]['presenceDims']!=[1,1]:raise ValueError('native output shape')
   arrays=[]
   for name,count in (('mask',h*w),('presence',1)):
    ref=c['paths'][name];path=d.checked({'path':ref['path'],'sha256':ref['sha256']});cp=root/'browser-capture'/f'{backend}-{h}x{w}-{name}.bin'
    if path.name!=ref['file'] or path.stat().st_size!=count*4 or cp.stat().st_size!=count*4:raise ValueError('exact float32 byte cardinality')
    arrays.append((np.fromfile(path,dtype=np.float32),np.fromfile(cp,dtype=np.float32)));captured.append(d.bind(cp))
   stats=compare_outputs(arrays[0][0],arrays[1][0],arrays[0][1],arrays[1][1],h,w)
   records.append({'backend':backend,'shape':[h,w],**stats})
 ok=all(r['numericGatePassed'] and r['decodedPixelGatePassed'] and r['presenceDecisionMatched'] for r in records)
 return {'schemaVersion':2,'ok':ok,'decision':'all_native_browser_controls_pass_untrained' if ok else 'native_browser_control_gate_failed_no_training',
  'inputs':{'static':d.bind(root/'report.json'),'controlManifest':d.bind(root/'controls.json'),'liveBrowser':d.bind(root/'browser-capture/live-browser.json'),'verifier':d.bind(__file__)},
  'records':records,'capturedOutputs':captured,'actualBrowserUserAgent':live['userAgent'],'requiredTolerance':1e-4,
  'requiredDecodedPixelDifference':0,'allBothBackendOutputsFinite':True,'trainingBudgetConsumed':False,'formalReleaseAllowed':False,'productHold':True}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--export-dir',type=Path);p.add_argument('--output',type=Path);p.add_argument('--verify-report',type=Path);a=p.parse_args()
 if a.verify_report:
  old=json.loads(a.verify_report.read_bytes());root=Path(old['inputs']['static']['path']).parent;result=build(root)
  if result!=old:raise ValueError('browser report reconstruction_mismatch')
 else:result=build(a.export_dir.resolve());d.new(a.output.resolve(),result)
 print(json.dumps({'ok':result['ok'],'decision':result['decision'],'maxAbs':max(r['maxAbsoluteDifference'] for r in result['records']),
 'decodedPixelDifferences':sum(r['decodedMaskPixelDifference'] for r in result['records'])}))
