"""真实浏览器从原尺寸计算全部比例，逐字节验证，不调用任何模型。"""
import argparse
import hashlib
import importlib.util
import json
import os
import threading
import uuid
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path

HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('host_ratio_data',HERE/'reviewed-role-development-data.py')
d=importlib.util.module_from_spec(s);s.loader.exec_module(d)

HTML='''<!doctype html><meta charset="utf-8"><title>主机比例字节核验</title><link rel="icon" href="data:,"><button id="run">核验全68两处比例；模型输入0</button><pre id="result">未执行</pre><script>
const hex=b=>Array.from(new Uint8Array(b)).map(x=>x.toString(16).padStart(2,'0')).join('');
async function post(path,bytes){const r=await fetch(path,{method:'POST',body:bytes}),s=await r.text();if(!r.ok)throw Error(path+' '+r.status);const a=JSON.parse(s);if(a.bytes!==bytes.length||a.sha256!==hex(await crypto.subtle.digest('SHA-256',bytes)))throw Error('ACK');}
document.querySelector('#run').onclick=async()=>{document.querySelector('#run').disabled=true;const c=await(await fetch('/config')).json(),r={executionSha256:c.executionSha256,pageRequestId:crypto.randomUUID(),userAgent:navigator.userAgent,records:[],errors:[],modelCalls:0};try{await post('/claim',new TextEncoder().encode(JSON.stringify({pageRequestId:r.pageRequestId,executionSha256:c.executionSha256})));for(const row of c.cases)for(let i=0;i<2;i++){const op=row.operations[i],v=new Float32Array([Math.fround(op.input.shape[2]/op.expected.shape[2]),Math.fround(op.input.shape[3]/op.expected.shape[3])]),b=new Uint8Array(v.buffer),sha=hex(await crypto.subtle.digest('SHA-256',b));if(sha!==op.hostRatios.sha256)throw Error('ratio bytes '+row.ordinal+' '+i);await post('/ratio/'+row.ordinal+'-'+i+'.bin',b);r.records.push({ordinal:row.ordinal,operationIndex:i,candidateIdentity:row.candidateIdentity,sha256:sha,bytes:b.length});}r.complete=r.records.length===136;}catch(e){r.complete=false;r.errors.push(String(e));}await post('/terminal',new TextEncoder().encode(JSON.stringify(r)));document.querySelector('#result').textContent=JSON.stringify(r);};</script>'''


def prepare(execution,root):
    e=d.read(d.bind(execution));p=d.read(e['scope'])
    if e['hostRatioAuditor']!=d.bind(__file__) or len(p['cases'])!=68 or p['newFullModelInputsAllowed']!=0:raise ValueError('fixed host ratio scope')
    if root.exists():raise ValueError('ratio preflight may not restart')
    root.mkdir();(root/'ratios').mkdir();d.new(root/'config.json',{'executionSha256':d.bind(execution)['sha256'],'cases':p['cases']})
    with (root/'browser.html').open('xb') as f:f.write(HTML.encode());f.flush();os.fsync(f.fileno())
    d.new(root/'preparation.json',{'execution':d.bind(execution),'auditor':d.bind(__file__),'config':d.bind(root/'config.json'),'html':d.bind(root/'browser.html')})


def serve(root,port):
    prep=d.read(d.bind(root/'preparation.json'));d.checked(prep['auditor']);config=d.read(prep['config']);e=d.read(prep['execution']);scope=d.read(e['scope'])
    if prep['auditor']!=d.bind(__file__) or e['hostRatioAuditor']!=prep['auditor'] or config!={'executionSha256':prep['execution']['sha256'],'cases':scope['cases']}:raise ValueError('frozen source / config')
    d.checked(prep['html'])
    if (root/'claim.json').exists():raise ValueError('preflight consumed')
    rows=config['cases'];order=[f'{r["ordinal"]}-{i}.bin' for r in rows for i in range(2)];saved=[];lock=threading.Lock()
    class Handler(BaseHTTPRequestHandler):
        protocol_version='HTTP/1.1'
        def reply(self,code,body,content='application/json'):
            b=body if isinstance(body,bytes) else d.raw(body);self.send_response(code);self.send_header('Content-Length',str(len(b)));self.send_header('Content-Type',content);self.end_headers();self.wfile.write(b);self.wfile.flush()
        def do_GET(self):
            if self.path=='/config':self.reply(200,d.checked(prep['config']).read_bytes())
            elif self.path=='/browser.html':self.reply(200,d.checked(prep['html']).read_bytes(),'text/html')
            else:self.reply(404,{})
        def do_POST(self):
            with lock:
                try:
                    n=int(self.headers.get('Content-Length','0'))
                    if self.path.startswith('/ratio/') and n!=8:raise ValueError('ratio byte count')
                    if not 0<n<1_000_000:raise ValueError('body bound')
                    b=self.rfile.read(n);ack={'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
                    if len(b)!=n:raise ValueError('truncated body')
                    if self.path=='/claim':
                        r=json.loads(b)
                        if r['executionSha256']!=config['executionSha256'] or str(uuid.UUID(r['pageRequestId']))!=r['pageRequestId']:raise ValueError('claim')
                        d.new(root/'claim.json',r)
                    elif self.path.startswith('/ratio/'):
                        name=self.path.removeprefix('/ratio/')
                        if not (root/'claim.json').exists() or len(saved)>=136 or name!=order[len(saved)]:raise ValueError('ordered ratio identity')
                        row=rows[len(saved)//2];i=len(saved)%2
                        if ack['sha256']!=row['operations'][i]['hostRatios']['sha256']:raise ValueError('ratio SHA')
                        with (root/'ratios'/name).open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
                        saved.append(name)
                    elif self.path=='/terminal':
                        r=json.loads(b)
                        if r['pageRequestId']!=d.read(d.bind(root/'claim.json'))['pageRequestId']:raise ValueError('terminal identity')
                        d.new(root/'terminal.json',r)
                    else:raise ValueError('route')
                    self.reply(201,ack)
                except (ValueError,KeyError,FileExistsError):self.reply(409,{'error':'preflight contract'})
        def log_message(self,*args):pass
    print(f'HOST_RATIO_SERVER http://127.0.0.1:{port}/browser.html',flush=True);ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()


def reconstruct(root):
    prep=d.read(d.bind(root/'preparation.json'));e=d.read(prep['execution']);scope=d.read(e['scope']);live=d.read(d.bind(root/'terminal.json'));d.checked(prep['auditor'])
    claim=d.read(d.bind(root/'claim.json'));config=d.read(prep['config']);d.checked(prep['html'])
    if e['hostRatioAuditor']!=prep['auditor'] or config!={'executionSha256':prep['execution']['sha256'],'cases':scope['cases']} or live['pageRequestId']!=claim['pageRequestId'] or claim['executionSha256']!=prep['execution']['sha256']:raise ValueError('claim / frozen config')
    if prep['auditor']!=d.bind(__file__) or not live['complete'] or live['errors'] or live['modelCalls']!=0 or live['executionSha256']!=prep['execution']['sha256'] or len(live['records'])!=136 or len(list((root/'ratios').glob('*.bin')))!=136:raise ValueError('whole136 browser ratios / zero model')
    records=[]
    for index,r in enumerate(live['records']):
        c=scope['cases'][index//2];i=index%2;op=c['operations'][i];path=root/'ratios'/f'{c["ordinal"]}-{i}.bin'
        if r!={'ordinal':c['ordinal'],'operationIndex':i,'candidateIdentity':c['candidateIdentity'],'sha256':op['hostRatios']['sha256'],'bytes':8}:raise ValueError('stable ratio record')
        if d.checked({k:op['hostRatios'][k] for k in ('path','sha256')}).read_bytes()!=path.read_bytes():raise ValueError('Python/browser bitwise')
        records.append(r|{'actualBrowser':d.bind(path),'originalPython':op['hostRatios']})
    return {'schemaVersion':1,'ok':True,'decision':'full68_python_browser_host_ratios_bitwise_identical','inputs':{'preparation':d.bind(root/'preparation.json'),'auditor':d.bind(__file__),'terminal':d.bind(root/'terminal.json')},'records':records,'ratioRecords':136,'newModelCalls':0,'newSourcePixels':0,'newChatImageInputs':0,'formalReleaseAllowed':False,'productHold':True}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execution',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--serve',action='store_true');p.add_argument('--audit',action='store_true');p.add_argument('--verify-report',action='store_true');p.add_argument('--port',type=int,default=8838);a=p.parse_args();root=a.output.resolve()
    if a.serve:serve(root,a.port)
    elif a.audit or a.verify_report:
        r=reconstruct(root)
        if a.verify_report:
            if r!=d.read(d.bind(root/'report.json')):raise ValueError('ratio reconstruction_mismatch')
        else:d.new(root/'report.json',r)
        print(json.dumps({k:r[k] for k in ('ok','decision','ratioRecords','newModelCalls')}))
    else:prepare(a.execution.resolve(),root)
