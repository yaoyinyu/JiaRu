"""只绑定回环的未训练控制页服务器；实际浏览器捕获只创建一次。"""
import argparse,urllib.parse
from pathlib import Path
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
R=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--port',type=int,default=8816);a=p.parse_args();out=a.output.resolve();ort=(R/'node_modules/onnxruntime-web/dist').resolve()
if not(out/'report.json').is_file() or not(out/'controls.json').is_file():raise ValueError('control evidence missing')
class Handler(SimpleHTTPRequestHandler):
 extensions_map=SimpleHTTPRequestHandler.extensions_map|{'.mjs':'text/javascript','.wasm':'application/wasm','.bin':'application/octet-stream'}
 def translate_path(self,path):
  route=urllib.parse.unquote(urllib.parse.urlsplit(path).path);base=ort if route.startswith('/ort/') else out;tail=route[5:] if base==ort else route.lstrip('/');target=(base/tail).resolve()
  return str(target if target.is_relative_to(base) else base/'nonexistent')
 def end_headers(self):
  self.send_header('Cross-Origin-Opener-Policy','same-origin');self.send_header('Cross-Origin-Embedder-Policy','require-corp');super().end_headers()
 def do_POST(self):
  name=self.path.removeprefix('/capture/');count=int(self.headers.get('Content-Length','0'))
  if not self.path.startswith('/capture/') or Path(name).name!=name or not(name=='live-browser.json' or name.endswith('.bin')) or not(0<count<=16000000):self.send_error(400);return
  folder=out/'browser-capture';folder.mkdir(exist_ok=True)
  try:
   with(folder/name).open('xb') as f:f.write(self.rfile.read(count));f.flush()
  except FileExistsError:self.send_error(409);return
  self.send_response(201);self.end_headers();self.wfile.write(b'captured')
 def log_message(self,*args):pass
print(f'MULTISCALE_BROWSER_SERVER http://127.0.0.1:{a.port}/browser.html',flush=True);ThreadingHTTPServer(('127.0.0.1',a.port),Handler).serve_forever()
