"""用明确HTTP错误验证合成字节捕获恢复；断连后按SHA确认文件，不重复模型执行。"""
import argparse
import hashlib
import importlib.util
import json
import os
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
s = importlib.util.spec_from_file_location('capture_transport_data', HERE / 'reviewed-role-development-data.py')
d = importlib.util.module_from_spec(s); s.loader.exec_module(d)

HTML = r'''<!doctype html><html lang="zh"><meta charset="utf-8"><title>捕获传输零推理验证</title><link rel="icon" href="data:,"><h1>合成字节传输验证</h1><button id="run">验证应答丢失与持久化前断连</button><pre id="result">未执行；模型输入0。</pre><script>
const hex=b=>Array.from(new Uint8Array(b)).map(x=>x.toString(16).padStart(2,'0')).join('');
async function capture(index,body,sha,report){
 for(let attempt=0;attempt<3;attempt++){
  try{const r=await fetch('/capture/'+index,{method:'POST',body});const text=await r.text();if(!r.ok)throw Error('HTTP '+r.status);const ack=JSON.parse(text);if(ack.sha256!==sha||ack.bytes!==body.length)throw Error('ACK binding');return;}
  catch(error){report.transportErrors.push({index,attempt,error:String(error)});const status=await fetch('/status/'+index);const text=await status.text();
   if(status.ok){const ack=JSON.parse(text);if(ack.sha256!==sha||ack.bytes!==body.length)throw Error('persisted identity differs');report.persistedAckRecoveries++;return;}
   if(status.status!==404)throw Error('status '+status.status);report.uploadOnlyRetries++;
  }
 }throw Error('bounded upload attempts exhausted');
}
document.querySelector('#run').onclick=async()=>{
 document.querySelector('#run').disabled=true;const report={ok:false,modelInputs:0,optimizerSteps:0,records:[],transportErrors:[],persistedAckRecoveries:0,uploadOnlyRetries:0,userAgent:navigator.userAgent};
 try{
  const config=await(await fetch('/config.json')).json();report.configSha256=config.sha256;
  for(let i=1;i<=config.count;i++){document.querySelector('#result').textContent='合成捕获 '+i+'/'+config.count;const body=new Uint8Array(i===config.count?config.maxTensorBytes:config.smallBytes);body.fill(i%251);
   const sha=hex(await crypto.subtle.digest('SHA-256',body));await capture(i,body,sha,report);report.records.push({index:i,bytes:body.length,sha256:sha});
  }report.ok=true;
 }catch(e){report.error=String(e);}
 const r=await fetch('/terminal',{method:'POST',body:JSON.stringify(report)});await r.text();document.querySelector('#result').textContent=JSON.stringify(report);
};</script></html>'''


def expected(index, config):
    if type(index) != int or not 1 <= index <= config['count']: raise ValueError('probe index')
    count = config['maxTensorBytes'] if index == config['count'] else config['smallBytes']
    body = bytes([index % 251])*count
    return {'index': index, 'bytes': count, 'sha256': hashlib.sha256(body).hexdigest()}


def prepare(root):
    root.mkdir(parents=True, exist_ok=False); (root / 'captures').mkdir(); (root / 'events').mkdir()
    config = {'purpose': 'synthetic_bytes_transport_no_models', 'count': 16, 'smallBytes': 16384, 'maxTensorBytes': 25240576,
              'dropAfterPersistIndex': 7, 'dropBeforePersistIndex': 8, 'modelInputs': 0, 'optimizerSteps': 0}
    d.new(root / 'config-base.json', config); config['sha256'] = d.bind(root / 'config-base.json')['sha256']; d.new(root / 'config.json', config)
    with (root / 'browser.html').open('xb') as f: f.write(HTML.encode('utf-8')); f.flush(); os.fsync(f.fileno())
    d.new(root / 'preparation.json', {'server': d.bind(__file__), 'config': d.bind(root / 'config.json'), 'html': d.bind(root / 'browser.html')})


def serve(root, port):
    prep = d.read(d.bind(root / 'preparation.json'))
    for ref in prep.values(): d.checked(ref)
    if prep['server'] != d.bind(__file__) or any((root / 'events').iterdir()): raise ValueError('frozen server/probe already started')
    config = d.read(prep['config']); attempts = {}; lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def response(self, code, value, content='application/json'):
            body = value if isinstance(value, bytes) else d.raw(value)
            self.send_response(code); self.send_header('Content-Type', content); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body); self.wfile.flush()

        def do_GET(self):
            if self.path == '/browser.html': self.response(200, d.checked(prep['html']).read_bytes(), 'text/html')
            elif self.path == '/config.json': self.response(200, config)
            elif self.path.startswith('/status/'):
                try:
                    index = int(self.path.removeprefix('/status/')); e = expected(index, config); p = root / 'captures' / f'{index}.bin'
                    if not p.exists(): self.response(404, {'present': False}); return
                    if p.stat().st_size != e['bytes'] or d.bind(p)['sha256'] != e['sha256']: raise ValueError('persisted bytes')
                    self.response(200, e)
                except ValueError: self.response(400, {'error': 'invalid status'})
            else: self.response(404, {'error': 'route'})

        def disconnect(self):
            self.close_connection = True
            self.connection.shutdown(socket.SHUT_RDWR); self.connection.close()

        def do_POST(self):
            with lock:
                if self.path == '/terminal':
                    count = int(self.headers.get('Content-Length', '0'))
                    if not 0 < count < 1_000_000: self.response(400, {'error': 'terminal size'}); return
                    d.new(root / 'live-browser.json', json.loads(self.rfile.read(count))); self.response(201, {'captured': True}); return
                try:
                    if not self.path.startswith('/capture/'): raise ValueError('route')
                    index = int(self.path.removeprefix('/capture/')); e = expected(index, config); count = int(self.headers.get('Content-Length', '0'))
                    if count != e['bytes']: raise ValueError('byte count')
                    body = self.rfile.read(count)
                    if len(body) != count or hashlib.sha256(body).hexdigest() != e['sha256']: raise ValueError('exact synthetic bytes')
                    attempt = attempts.get(index, 0) + 1; attempts[index] = attempt
                    d.new(root / 'events' / f'{index}-{attempt}.json', {'index': index, 'attempt': attempt, 'bodySha256': e['sha256']})
                    if index == config['dropBeforePersistIndex'] and attempt == 1: self.response(503, {'error': 'forced acknowledgment failure'}); return
                    path = root / 'captures' / f'{index}.bin'
                    if path.exists():
                        if path.stat().st_size != count or d.bind(path)['sha256'] != e['sha256']: raise ValueError('duplicate conflict')
                    else:
                        with path.open('xb') as f: f.write(body); f.flush(); os.fsync(f.fileno())
                    if index == config['dropAfterPersistIndex'] and attempt == 1: self.response(503, {'error': 'forced acknowledgment failure'}); return
                    self.response(201, e)
                except (ValueError, FileExistsError): self.response(400, {'error': 'capture contract'})

        def log_message(self, *args): pass

    print(f'CAPTURE_TRANSPORT_PROBE http://127.0.0.1:{port}/browser.html', flush=True)
    ThreadingHTTPServer(('127.0.0.1', port), Handler).serve_forever()


def reconstruct(root):
    prep = d.read(d.bind(root / 'preparation.json'))
    for ref in prep.values(): d.checked(ref)
    config = d.read(prep['config']); live = d.read(d.bind(root / 'live-browser.json'))
    rows = [expected(i, config) for i in range(1, config['count']+1)]
    if not live['ok'] or live['records'] != rows or live['modelInputs'] != 0 or live['optimizerSteps'] != 0 or live['configSha256'] != config['sha256']:
        raise ValueError('synthetic transport reconstruction_mismatch')
    if live['persistedAckRecoveries'] != 1 or live['uploadOnlyRetries'] != 1 or [r['index'] for r in live['transportErrors']] != [7, 8]: raise ValueError('forced disconnect recovery')
    captures = []
    for r in rows:
        ref = d.bind(root / 'captures' / f'{r["index"]}.bin')
        if ref['sha256'] != r['sha256'] or Path(ref['path']).stat().st_size != r['bytes']: raise ValueError('full capture SHA/size')
        captures.append(ref)
    events = [d.bind(p) for p in sorted((root / 'events').glob('*.json'))]
    if len(events) != config['count']+1 or len(list((root / 'captures').glob('*.bin'))) != config['count']: raise ValueError('full probe denominator')
    for ref in events:
        value = d.read(ref); e = expected(value['index'], config)
        if value['bodySha256'] != e['sha256'] or value['attempt'] != (2 if Path(ref['path']).stem == '8-2' else 1): raise ValueError('upload retry event')
    return {'schemaVersion': 1, 'ok': True, 'decision': 'synthetic_transport_recovery_verified', 'inputs': {'preparation': d.bind(root / 'preparation.json'), 'liveBrowser': d.bind(root / 'live-browser.json'), 'auditor': d.bind(__file__)}, 'captures': captures, 'events': events, 'uniqueCaptures': config['count'], 'uniqueFileBytes': sum(r['bytes'] for r in rows), 'uploadAttempts': len(events), 'forcedPersistedAckRecovery': 1, 'forcedBeforePersistUploadRetry': 1, 'modelInputs': 0, 'optimizerSteps': 0, 'projectImagesSent': 0, 'originalFetchFailureRootCauseEstablished': False, 'formalReleaseAllowed': False, 'productHold': True}


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--output', type=Path, required=True); p.add_argument('--serve', action='store_true'); p.add_argument('--audit', action='store_true'); p.add_argument('--verify-report', action='store_true'); p.add_argument('--port', type=int, default=8829); a = p.parse_args(); root = a.output.resolve()
    if a.serve: serve(root, a.port)
    elif a.audit or a.verify_report:
        result = reconstruct(root)
        if a.verify_report:
            if result != d.read(d.bind(root / 'report.json')): raise ValueError('report changed')
        else: d.new(root / 'report.json', result)
        print(json.dumps({k: result[k] for k in ('ok', 'decision', 'modelInputs', 'uniqueCaptures')}))
    else: prepare(root)
