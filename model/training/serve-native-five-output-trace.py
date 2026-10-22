"""完整图五输出提交原因跟踪：独占输出和有界日志窗口。"""
import argparse
import hashlib
import importlib.util
import json
import os
import time
import uuid
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('single_browser_io',HERE/'reviewed-role-development-data.py');d=importlib.util.module_from_spec(s);s.loader.exec_module(d)



def serve(root,port):
 p=d.read(d.bind(root/'plan.json'));assert p['server']==d.bind(__file__) and p['html']==d.bind(root/'browser.html')
 for ref in [*p['assets'].values(),*p['runtimeFiles'].values(),p['traceHelper']]:d.checked(ref)
 cases={(c['backend'],str(c['ordinal'])):c for c in p['schedule']};expected={f'{b}-{i}-{head}.bin':(4 if head=='presence' else c['h']*c['w']*4 if head=='mask' else (c['h']//2)*(c['w']//2)*32*4) for (b,i),c in cases.items() for head in p['outputs']}
 traces={'trace-setup.json',*(f'trace-run-{i}.json' for i in range(1,10))}
 class Handler(BaseHTTPRequestHandler):
  def end_headers(self):
   self.send_header('Cross-Origin-Opener-Policy','same-origin');self.send_header('Cross-Origin-Embedder-Policy','require-corp');self.send_header('Cache-Control','no-store');super().end_headers()
  def do_GET(self):
   if self.path in ['/','/browser.html']:path=root/'browser.html'
   elif self.path=='/config.json':path=root/'config.json'
   elif self.path=='/trace-helper.js':path=d.checked(p['traceHelper'])
   elif self.path.startswith('/assets/') and self.path[8:] in p['assets']:path=d.checked(p['assets'][self.path[8:]])
   elif self.path.startswith('/ort/') and self.path[5:] in p['runtimeFiles']:path=d.checked(p['runtimeFiles'][self.path[5:]])
   else:self.send_error(404);return
   content=path.read_bytes();mime='application/wasm' if path.suffix=='.wasm' else 'text/javascript' if path.suffix in ['.mjs','.js'] else 'text/html; charset=utf8' if path.suffix=='.html' else 'application/json' if path.suffix=='.json' else 'application/octet-stream';self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(content)));self.end_headers();self.wfile.write(content)
  def do_POST(self):
   count=int(self.headers.get('Content-Length',0));rid=self.headers.get('X-Request-Id','');sha=self.headers.get('X-Content-SHA256','');d.new(root/'http-events'/f'{uuid.uuid4().hex}.json',{'path':self.path,'requestId':rid,'declaredSha256':sha,'declaredBytes':count,'startedUnixNs':time.time_ns()})
   if not rid or len(rid)>200 or len(sha)!=64:self.send_error(400);return
   if self.path=='/claim':target=root/'claim.json';limit=4096
   elif self.path.startswith('/started/'):
    parts=self.path.split('/')
    if len(parts)!=4 or (parts[2],parts[3]) not in cases:self.send_error(400);return
    target=root/'started'/f'{parts[2]}-{parts[3]}.json';limit=4096
   elif self.path.startswith('/capture/'):
    name=self.path[9:]
    if name=='live-browser.json':limit=1048576
    elif name in traces:limit=33554432
    elif name in expected:limit=expected[name]
    else:self.send_error(400);return
    if name!='live-browser.json' and name not in traces and count!=limit:self.send_error(400);return
    target=root/'capture'/name
   else:self.send_error(404);return
   if count<=0 or count>limit:self.send_error(400);return
   body=self.rfile.read(count)
   if len(body)!=count or hashlib.sha256(body).hexdigest()!=sha:self.send_error(400);return
   if self.path=='/claim':
    value=json.loads(body)
    if value.get('planSha256')!=d.bind(root/'plan.json')['sha256'] or rid!=value.get('claim','')+'-claim':self.send_error(400);return
   else:
    if not (root/'claim.json').exists():self.send_error(403);return
    claim=json.loads((root/'claim.json').read_bytes())['claim']
    if not rid.startswith(claim+'-'):self.send_error(403);return
    if self.path.startswith('/started/'):
     value=json.loads(body);c=cases[(parts[2],parts[3])]
     if value!={'claim':claim,'requestId':claim+'-'+parts[2]+'-'+parts[3],'backend':parts[2],'ordinal':int(parts[3]),'h':c['h'],'w':c['w'],'inputSha256':c['input']['sha256']}:self.send_error(400);return
   metadata=root/'metadata'/f'{target.parent.name}-{target.name}.json'
   if target.exists():
    if not metadata.exists() or hashlib.sha256(target.read_bytes()).hexdigest()!=sha or json.loads(metadata.read_bytes())['requestId']!=rid:self.send_error(409);return
    self.send_response(200);self.end_headers();self.wfile.write(b'inherited exact same request');return
   try:
    with target.open('xb') as stream:stream.write(body);stream.flush();os.fsync(stream.fileno())
    d.new(metadata,{'requestId':rid,'sha256':sha,'bytes':count,'savedUnixNs':time.time_ns()})
   except FileExistsError:self.send_error(409);return
   self.send_response(201);self.end_headers();self.wfile.write(b'captured')
  def log_message(self,*args):pass
 print(f'FULL_TWO_HEAD_SERVER http://127.0.0.1:{port}/browser.html',flush=True);ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()


if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--root',type=Path,required=True);a.add_argument('--port',type=int,required=True);v=a.parse_args();serve(v.root.resolve(),v.port)
