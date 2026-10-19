"""下载固定版本的公开视觉教师，逐文件核验远端对象；不运行模型或上传图片。"""
import argparse,hashlib,json,os,shutil,time
from pathlib import Path


def write(path,value):
 raw=(json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf8')
 with path.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())


def main():
 a=argparse.ArgumentParser();a.add_argument('--model',required=True);a.add_argument('--output',type=Path,required=True);a.add_argument('--metadata-only',action='store_true');args=a.parse_args()
 os.environ['HF_HUB_DISABLE_TELEMETRY']='1';os.environ['HF_HUB_DISABLE_XET']='1'
 from huggingface_hub import HfApi,hf_hub_download
 root=args.output.resolve();root.mkdir(parents=True,exist_ok=True);meta=root/'source-manifest.json'
 if meta.exists():
  plan=json.loads(meta.read_bytes());assert plan['model']==args.model
 else:
  info=HfApi(token=False).model_info(args.model,files_metadata=True);files=[]
  assert info.card_data.license=='apache-2.0' and len(info.sha)==40
  for row in info.siblings:
   name=row.rfilename
   if not (name.endswith(('.safetensors','.json','.txt')) or name in ['README.md','LICENSE']):continue
   if '/' in name or '\\' in name:raise ValueError('unexpected nested asset')
   lfs=row.lfs
   files.append({'name':name,'bytes':row.size,'gitBlobSha1':row.blob_id,'lfsSha256':lfs.sha256 if lfs else None})
  assert files and any(v['name'].endswith('.safetensors') for v in files) and all(type(v['bytes']) is int and v['bytes']>0 for v in files)
  plan={'model':args.model,'revision':info.sha,'license':info.card_data.license,'sourceUrl':'https://huggingface.co/'+args.model,'files':files,'totalBytes':sum(v['bytes'] for v in files),'anonymousPublicDownload':True,'projectImageUploadBytes':0,'modelInputs':0,'createdUnix':time.time()};write(meta,plan)
 print(json.dumps({'revision':plan['revision'],'files':len(plan['files']),'totalBytes':plan['totalBytes'],'metadataOnly':args.metadata_only}),flush=True)
 if args.metadata_only:return
 if (root/'download-report.json').exists():raise ValueError('completed download is immutable')
 if shutil.disk_usage(root).free<plan['totalBytes']*1.2:raise ValueError('insufficient disk for bounded model download')
 events=root/'download-events';events.mkdir(exist_ok=True);records=[]
 for i,item in enumerate(plan['files'],1):
  attempt=1
  while (events/f'{i:03d}-{attempt:03d}-start.json').exists():attempt+=1
  write(events/f'{i:03d}-{attempt:03d}-start.json',{'file':item,'revision':plan['revision'],'unix':time.time()});print(json.dumps({'downloading':item['name'],'bytes':item['bytes']}),flush=True)
  try:
   path=Path(hf_hub_download(args.model,item['name'],revision=plan['revision'],local_dir=root/'assets',token=False));h=hashlib.sha256();g=hashlib.sha1();g.update(('blob '+str(item['bytes'])+'\0').encode());count=0
   with path.open('rb') as f:
    while block:=f.read(8*1024*1024):count+=len(block);h.update(block);g.update(block)
   assert count==item['bytes']
   assert h.hexdigest()==item['lfsSha256'] if item['lfsSha256'] else g.hexdigest()==item['gitBlobSha1']
   record={'name':item['name'],'path':str(path),'bytes':count,'sha256':h.hexdigest(),'remoteObjectExact':True};records.append(record);write(events/f'{i:03d}-{attempt:03d}-done.json',record)
  except BaseException as e:write(events/f'{i:03d}-{attempt:03d}-failure.json',{'error':repr(e),'file':item,'modelInputs':0});raise
 write(root/'download-report.json',{'ok':True,'sourceManifest':{'path':str(meta),'sha256':hashlib.sha256(meta.read_bytes()).hexdigest()},'files':records,'totalBytes':sum(v['bytes'] for v in records),'modelInputs':0,'projectImageUploadBytes':0});print(json.dumps({'ok':True,'downloadBytes':plan['totalBytes'],'modelInputs':0}),flush=True)


if __name__=='__main__':main()
