"""固定公开HF清单的有界分段下载；完整对象哈希通过才交付，不调用模型。"""
import argparse,concurrent.futures,hashlib,json,os,shutil,threading,time
from pathlib import Path
import httpx


def raw(v):return (json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode('utf8')
def put(p,v):
 with p.open('xb') as f:f.write(raw(v));f.flush();os.fsync(f.fileno())
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(8*1024*1024):h.update(b)
 return h.hexdigest()


def main():
 a=argparse.ArgumentParser();a.add_argument('--manifest',type=Path,required=True);a.add_argument('--output',type=Path,required=True);args=a.parse_args();plan=json.loads(args.manifest.read_bytes());assert len(plan['revision'])==40 and plan['license']=='apache-2.0';root=args.output.resolve();root.mkdir(parents=True,exist_ok=True);assets=root/'assets';assets.mkdir(exist_ok=True);parts=root/'parts';parts.mkdir(exist_ok=True);events=root/'events';events.mkdir(exist_ok=True)
 if (root/'report.json').exists():raise ValueError('completed report immutable')
 manifest_ref={'path':str(args.manifest.resolve()),'sha256':digest(args.manifest)}
 if not (root/'plan.json').exists():
  if shutil.disk_usage(root).free<plan['totalBytes']*2.2:raise ValueError('insufficient bounded staging space')
  put(root/'plan.json',{'source':manifest_ref,'reader':{'path':str(Path(__file__).resolve()),'sha256':digest(Path(__file__))},'chunkBytes':32*1024*1024,'workers':4,'perChunkAttempts':3,'modelInputs':0,'imageUploadBytes':0,'transportResumeNotNeuralBudgetRestart':True})
 else:assert json.loads((root/'plan.json').read_bytes())['source']==manifest_ref
 local=threading.local();lock=threading.Lock();completed=0;total_chunks=0
 def client():
  if not hasattr(local,'client'):local.client=httpx.Client(follow_redirects=True,timeout=httpx.Timeout(35,connect=15))
  return local.client
 def task(job):
  nonlocal completed
  item,start,end=job;key=f'{item["name"]}.{start:012d}-{end:012d}';path=parts/key;receipt=parts/(key+'.json')
  if receipt.exists():
   saved=json.loads(receipt.read_bytes());assert path.stat().st_size==end-start+1 and digest(path)==saved['sha256'];return
  url=f'https://huggingface.co/{plan["model"]}/resolve/{plan["revision"]}/{item["name"]}'
  for attempt in range(1,4):
   event=events/f'{key}.{attempt}.json'
   if event.exists():continue
   started=time.monotonic();buffers=[];count=0
   try:
    with client().stream('GET',url,headers={'Range':f'bytes={start}-{end}'}) as response:
     assert response.status_code==206 and response.headers.get('content-range')==f'bytes {start}-{end}/{item["bytes"]}'
     for block in response.iter_bytes(chunk_size=1024*1024):
      count+=len(block)
      if count>end-start+1 or time.monotonic()-started>90:raise ValueError('bounded segment exceeded')
      buffers.append(block)
    assert count==end-start+1;data=b''.join(buffers)
    if path.exists():assert path.read_bytes()==data
    else:
     with path.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
    saved={'file':item['name'],'start':start,'end':end,'bytes':count,'sha256':hashlib.sha256(data).hexdigest()};put(receipt,saved);put(event,{'ok':True,**saved,'seconds':time.monotonic()-started})
    with lock:
     completed+=1
     if completed%16==0:print(json.dumps({'chunksConfirmedThisRun':completed,'chunksTotal':total_chunks,'confirmedBytesLowerBound':completed*32*1024*1024}),flush=True)
    return
   except BaseException as e:put(event,{'ok':False,'error':repr(e),'receivedBytes':count,'seconds':time.monotonic()-started})
  raise ValueError('segment attempts exhausted '+key)
 jobs=[]
 for item in plan['files']:
  if item['lfsSha256']:
   for start in range(0,item['bytes'],32*1024*1024):jobs.append((item,start,min(item['bytes']-1,start+32*1024*1024-1)))
 total_chunks=len(jobs);print(json.dumps({'model':plan['model'],'revision':plan['revision'],'chunks':total_chunks,'bytes':plan['totalBytes']}),flush=True)
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(task,jobs))
 records=[]
 for item in plan['files']:
  output=assets/item['name']
  if not output.exists():
   with output.open('xb') as f:
    if item['lfsSha256']:
     for start in range(0,item['bytes'],32*1024*1024):
      end=min(item['bytes']-1,start+32*1024*1024-1);part=parts/f'{item["name"]}.{start:012d}-{end:012d}';shutil.copyfileobj(part.open('rb'),f,8*1024*1024)
    else:
     response=client().get(f'https://huggingface.co/{plan["model"]}/resolve/{plan["revision"]}/{item["name"]}');response.raise_for_status();assert len(response.content)==item['bytes'];f.write(response.content)
    f.flush();os.fsync(f.fileno())
  assert output.stat().st_size==item['bytes'];h=digest(output)
  if item['lfsSha256']:assert h==item['lfsSha256']
  else:assert hashlib.sha1(('blob '+str(item['bytes'])+'\0').encode()+output.read_bytes()).hexdigest()==item['gitBlobSha1']
  records.append({'path':str(output),'sha256':h,'bytes':item['bytes'],'remoteExact':True})
 put(root/'report.json',{'ok':True,'plan':{'path':str(root/'plan.json'),'sha256':digest(root/'plan.json')},'source':manifest_ref,'files':records,'totalBytes':sum(v['bytes'] for v in records),'allOfficialObjectsExact':True,'modelInputs':0,'imageUploadBytes':0});print(json.dumps({'ok':True,'bytes':plan['totalBytes'],'modelInputs':0}),flush=True)


if __name__=='__main__':main()
