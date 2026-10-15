"""本机独占合成WASM验收页；仅白名单读取，原子持久化、同字节ACK恢复。"""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[2]


def bind(path):
    path = Path(path).resolve(strict=True)
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def new(path, raw):
    with Path(path).open('xb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())


def serve(reference, output, port):
    reference = reference.resolve(strict=True)
    report = json.loads(reference.read_bytes())
    plan_path = Path(report['plan']['path']); plan = json.loads(plan_path.read_bytes())
    assert hashlib.sha256(plan_path.read_bytes()).hexdigest() == report['plan']['sha256']
    assert plan['browserSyntheticMaskInputsAllowed'] == 4 and plan['projectModelInputsAllowed'] == 0
    output = output.resolve()
    assert output.is_relative_to(ROOT / 'model/reviews')
    allowed = {}
    def collect(obj):
        if isinstance(obj, dict):
            if 'path' in obj and 'sha256' in obj:
                path = Path(obj['path']).resolve(strict=True)
                assert path.is_relative_to(ROOT)
                allowed[str(path)] = obj['sha256']
            for value in obj.values(): collect(value)
        elif isinstance(obj, list):
            for value in obj: collect(value)
    # 只提供本批合成文件和运行时，不将编译器/项目原图作为HTTP资源。
    collect({key: report[key] for key in ['plan', 'records', 'erfInput', 'erfReference']})
    collect({key: plan[key] for key in ['sources', 'config', 'weights', 'wasm']})
    allowed[str(reference)] = bind(reference)['sha256']
    modules = {name: ROOT / 'model/runtime' / name for name in [
        'audit-mask-f64-synthetic.mjs', 'nail-mask-f64-v2.mjs', 'nail-mask-f64.mjs']}
    for path in modules.values(): allowed[str(path)] = bind(path)['sha256']
    output.mkdir(exist_ok=False)
    ref = bind(reference)
    execution = {'reference': ref, 'backend': 'browser', 'port': port,
        'sources': [bind(__file__), *[bind(p) for p in modules.values()]],
        'resourceBindings': allowed, 'browserSyntheticMaskInputsAllowed': 4,
        'learnedInputsAllowed': 0, 'restartAllowed': False}
    new(output / 'execution.json', (json.dumps(execution, ensure_ascii=False, indent=2) + '\n').encode())
    lock = threading.Lock()
    page = '''<!doctype html><meta charset="utf-8"><title>WASM合成控制</title><pre id="status">准备中</pre>
<script type="module">
import { auditSynthetic } from '/module/audit-mask-f64-synthetic.mjs';
const status=document.getElementById('status');
async function post(name,raw) {
  const sha=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',raw)),x=>x.toString(16).padStart(2,'0')).join('');
  for(let attempt=0;attempt<3;attempt++){
    try {const response=await fetch('/output?name='+encodeURIComponent(name),{method:'POST',headers:{'X-Content-Sha256':sha},body:raw});
      const body=await response.text();if(!response.ok)throw Error(body);return;}
    catch(error){if(attempt===2)throw error;}
  }
}
const encode=x=>new TextEncoder().encode(JSON.stringify(x,null,2)+'\\n');
try {
  const claim=await fetch('/claim',{method:'POST',body:encode({userAgent:navigator.userAgent,hardwareConcurrency:navigator.hardwareConcurrency})});
  const message=await claim.text();if(!claim.ok)throw Error(message);
  await auditSynthetic(REFERENCE,{
    read:async p=>{const r=await fetch('/resource?path='+encodeURIComponent(p));if(!r.ok)throw Error(await r.text());return r.arrayBuffer();},
    json:async(name,value)=>post(name,encode(value)),
    raw:async(name,value)=>post(name,value),
    progress:async value=>{status.textContent=JSON.stringify(value);}
  },'browser');
  status.textContent='PASS: 4/4完整WASM合成mask；presence未执行，正式HOLD保持';
}catch(error){status.textContent='FAIL: '+error.stack;await post('browser-failure.json',encode({error:error.stack,restartAllowed:false}));}
</script>'''.replace('REFERENCE', json.dumps(ref))
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            return
        def reply(self, status, raw, mime='application/json'):
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Cross-Origin-Opener-Policy', 'same-origin')
            self.send_header('Cross-Origin-Embedder-Policy', 'require-corp')
            self.end_headers(); self.wfile.write(raw)
        def do_GET(self):
            target = urlsplit(self.path)
            try:
                if target.path == '/':
                    return self.reply(200, page.encode(), 'text/html; charset=utf-8')
                if target.path == '/resource':
                    path = Path(parse_qs(target.query)['path'][0])
                elif target.path.startswith('/module/'):
                    path = modules[target.path.removeprefix('/module/')]
                else:
                    return self.reply(404, b'not found')
                assert str(path) in allowed
                raw = path.read_bytes()
                assert hashlib.sha256(raw).hexdigest() == allowed[str(path)]
                return self.reply(200, raw, 'text/javascript' if path.suffix == '.mjs' else 'application/octet-stream')
            except Exception as error:
                return self.reply(409, str(error).encode())
        def do_POST(self):
            target = urlsplit(self.path)
            try:
                size = int(self.headers.get('Content-Length', '-1'))
                assert 0 <= size <= 20 * 1024 * 1024
                raw = self.rfile.read(size)
                assert len(raw) == size
                with lock:
                    if target.path == '/claim':
                        new(output / 'claim.json', raw)
                        return self.reply(200, b'{"ok":true}')
                    assert target.path == '/output' and (output / 'claim.json').is_file()
                    name = parse_qs(target.query)['name'][0]
                    assert Path(name).name == name and name not in ['execution.json', 'claim.json']
                    assert hashlib.sha256(raw).hexdigest() == self.headers['X-Content-Sha256']
                    path = output / name
                    if path.exists():
                        assert path.read_bytes() == raw, 'existing output bytes mismatch'
                    else:
                        new(path, raw)
                    return self.reply(200, b'{"ok":true}')
            except Exception as error:
                return self.reply(409, str(error).encode())
    print(json.dumps({'ready': True, 'url': f'http://127.0.0.1:{port}/', 'output': str(output)}), flush=True)
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    try: server.serve_forever()
    finally: server.server_close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True); parser.add_argument('--port', type=int, default=8867)
    args = parser.parse_args(); serve(args.reference, args.output, args.port)
