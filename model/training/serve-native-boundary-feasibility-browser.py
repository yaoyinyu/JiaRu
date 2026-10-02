"""本地诊断页与ORT资源服务；独占保存实际浏览器捕获，不覆盖历史。"""
import argparse
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import urllib.parse
root=Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--port',type=int,default=8783);args=parser.parse_args()
out=args.output.resolve();ort=(root/'node_modules/onnxruntime-web/dist').resolve()
if not (out/'feasibility-report.json').is_file():raise ValueError('static report missing')


class Handler(SimpleHTTPRequestHandler):
    extensions_map=SimpleHTTPRequestHandler.extensions_map|{'.mjs':'text/javascript','.wasm':'application/wasm','.bin':'application/octet-stream'}

    def translate_path(self,path):
        decoded=urllib.parse.unquote(urllib.parse.urlsplit(path).path);base=ort if decoded.startswith('/ort/') else out
        relative=decoded[5:] if base==ort else decoded.lstrip('/');target=(base/relative).resolve()
        return str(target if target.is_relative_to(base) else base/'nonexistent')

    def end_headers(self):
        self.send_header('Cross-Origin-Opener-Policy','same-origin');self.send_header('Cross-Origin-Embedder-Policy','require-corp');super().end_headers()

    def do_POST(self):
        name=self.path.removeprefix('/capture/')
        if not self.path.startswith('/capture/') or Path(name).name!=name or not (name=='live-browser.json' or name.endswith('.bin')):self.send_error(400);return
        count=int(self.headers.get('Content-Length','0'))
        if count<1 or count>16000000:self.send_error(400);return
        capture=out/'browser-capture';capture.mkdir(exist_ok=True)
        try:
            with (capture/name).open('xb') as stream:stream.write(self.rfile.read(count));stream.flush()
        except FileExistsError:self.send_error(409);return
        self.send_response(201);self.end_headers();self.wfile.write(b'captured')

    def log_message(self,format,*args):pass


print(f'NATIVE_BOUNDARY_BROWSER_SERVER http://127.0.0.1:{args.port}/browser.html',flush=True)
ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()
