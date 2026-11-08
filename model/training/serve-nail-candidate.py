"""本机候选模型 /matte 服务；仅内存推理，沿用业务逐甲复核流程。"""
import argparse
import base64
import hashlib
import hmac
import importlib.util
import io
import json
import os
from pathlib import Path
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
HERE = Path(__file__).resolve().parent
MAX_BODY = 8 * 1024 * 1024
MAX_PIXELS = 9_000_000


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def checked(ref):
    path = Path(ref['path'])
    if hashlib.sha256(path.read_bytes()).hexdigest() != ref['sha256']:
        raise ValueError('候选资产哈希不一致')
    return path


def decode_image(value):
    from PIL import Image, ImageOps
    import numpy as np
    if not isinstance(value, str) or ',' not in value:
        raise ValueError('缺少图片')
    prefix, encoded = value.split(',', 1)
    if prefix.lower() not in ('data:image/png;base64', 'data:image/jpeg;base64',
                              'data:image/jpg;base64', 'data:image/webp;base64'):
        raise ValueError('图片格式错误')
    raw = base64.b64decode(encoded, validate=True)
    with Image.open(io.BytesIO(raw)) as image:
        if image.width * image.height > MAX_PIXELS:
            raise ValueError('图片分辨率过大')
        return np.asarray(ImageOps.exif_transpose(image).convert('RGB')).copy()


def radial_input(rgb, coarse, field, strip_module):
    import numpy as np
    ys, xs = np.nonzero(coarse)
    if not len(xs):
        raise ValueError('候选掩膜为空')
    center = np.asarray((xs.mean(), ys.mean()), np.float64)
    bins, distance = field.lattice(coarse.shape, center, 2048)
    radii = field.fit_radius(coarse, bins, distance, 2048)
    strip = strip_module.build_strip(rgb, coarse, center, radii)
    return strip, radii, bins, distance


class CandidateModel:
    def __init__(self, config):
        import torch
        guard = load('candidate_image_guard', HERE / 'train-yolo-seg.py')
        guard.install_read_only_ultralytics_image_check()
        for ref in config['sources'].values():
            checked(ref)
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        torch.backends.cudnn.benchmark = False
        torch.use_deterministic_algorithms(True)
        self.device = config.get('device', 'cuda:0')
        self.stage_a = torch.load(checked(config['stageA']), map_location='cpu', weights_only=False)['model'].float().to(self.device).eval()
        self.net = load('candidate_geometry', HERE / 'native-geometry-radial-refiner.py')
        self.field = load('candidate_field', HERE / 'native-pixel-radial-field.py')
        self.strip = load('candidate_strip', HERE / 'native-radial-strip-refiner.py')
        self.roi = load('candidate_roi', HERE / 'analyze-saved-nail-roi-coverage.py')
        self.model = self.net.NativeGeometryRadialRefiner().float().to(self.device).eval()
        self.model.load_state_dict(torch.load(checked(config['stageB']), map_location='cpu', weights_only=True), strict=True)
        torch.set_num_threads(2)
        self.version = config['version']
        self.weights = {k: config[k]['sha256'] for k in ('stageA', 'stageB')}
        self.lock = threading.Lock()

    def predict(self, rgb):
        import numpy as np
        import torch
        from PIL import Image
        height, width = rgb.shape[:2]
        from ultralytics.data.augment import LetterBox
        from ultralytics.utils import nms, ops
        bgr = rgb[:, :, ::-1].copy()
        image = LetterBox((512, 512), auto=False, stride=32)(image=bgr)
        packed = np.ascontiguousarray(image[..., ::-1].transpose(2, 0, 1), dtype=np.float32) / np.float32(255)
        with torch.inference_mode():
            output = self.stage_a(torch.from_numpy(packed)[None].to(self.device))
        det, proto = (a.detach().cpu() for a in output[0])
        accepted = nms.non_max_suppression(det.clone(), .35, .7, max_det=10, nc=1, end2end=False)[0]
        if not len(accepted):
            return []
        accepted[:, :4] = ops.scale_boxes((512, 512), accepted[:, :4], (height, width, 3))
        masks = ops.process_mask_native(proto[0], accepted[:, 6:], accepted[:, :4], (height, width))
        keep = masks.amax((-2, -1)) > 0
        boxes = accepted[keep, :4].numpy()
        masks = masks[keep].numpy().astype(bool)
        if masks.shape != (len(boxes), height, width):
            raise RuntimeError('原图掩膜尺寸失配')
        instances = []
        for index, (box, mask) in enumerate(zip(boxes, masks, strict=True)):
            crop = self.roi.crop_box(box, width, height, 'square_context_035')
            if crop is None:
                continue
            x0, y0, x1, y1 = crop
            coarse = mask[y0:y1, x0:x1].copy()
            if not coarse.any():
                continue
            arrays = radial_input(rgb[y0:y1, x0:x1].copy(), coarse, self.field, self.strip)
            args = [torch.from_numpy(a.astype(np.int64) if i == 2 else a)[None].to(self.device)
                    for i, a in enumerate(arrays)]
            with torch.inference_mode():
                logits, presence = self.model(*args)
            if not torch.isfinite(logits).all() or not torch.isfinite(presence).all():
                raise RuntimeError('模型输出非有限值')
            if presence.item() < 0:
                continue
            native = logits.cpu().numpy()[0, 0] >= 0
            ys, xs = np.nonzero(native)
            if not len(xs):
                continue
            alpha = np.zeros((height, width), np.uint8)
            alpha[y0:y1, x0:x1] = native.astype(np.uint8) * 255
            encoded = io.BytesIO()
            Image.fromarray(alpha).save(encoded, format='PNG')
            bounds = [int(xs.min()) + x0, int(ys.min()) + y0,
                      int(xs.max()) + x0 + 1, int(ys.max()) + y0 + 1]
            instances.append(dict(index=index, box=bounds, bbox=bounds, area=int(native.sum()),
                                  alphaPng='data:image/png;base64,' + base64.b64encode(encoded.getvalue()).decode(),
                                  width=width, height=height))
        return instances


def handler(model, token):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # 请求图片、鉴权和路径均不记录。

        def reply(self, code, value):
            data = json.dumps(value, ensure_ascii=False).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(data)

        def authorized(self):
            return hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + token)

        def do_GET(self):
            if not self.authorized():
                return self.reply(401, {'error': 'unauthorized'})
            if self.path != '/health':
                return self.reply(404, {'error': 'not_found'})
            self.reply(200, dict(ready=True, busy=model.lock.locked(), model=model.version,
                                 weights=model.weights, productHold=True, requiresReview=True))

        def do_POST(self):
            if not self.authorized():
                return self.reply(401, {'error': 'unauthorized'})
            if self.path != '/matte':
                return self.reply(404, {'error': 'not_found'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= MAX_BODY:
                    return self.reply(413, {'error': 'too_large'})
            except ValueError:
                return self.reply(400, {'error': 'invalid_length'})
            if not model.lock.acquire(blocking=False):
                return self.reply(503, {'busy': True, 'retryAfterSeconds': 3})
            try:
                value = json.loads(self.rfile.read(length))
                rgb = decode_image(value.get('image'))
                start = time.monotonic()
                instances = model.predict(rgb)
                self.reply(200, dict(width=rgb.shape[1], height=rgb.shape[0], instances=instances,
                                     model=model.version, quant='none', elapsedMs=(time.monotonic()-start)*1000,
                                     productHold=True, requiresReview=True))
            except (ValueError, TypeError, AttributeError, OSError):
                self.reply(400, {'error': 'invalid_image'})
            except Exception:
                self.reply(500, {'error': 'candidate_inference_failed'})
            finally:
                model.lock.release()
    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    parser.add_argument('--port', type=int, default=8011)
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text('utf-8'))
    if len(config.get('token', '')) < 32:
        raise ValueError('本机候选服务须配置独立长令牌')
    model = CandidateModel(config)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler(model, config['token']))
    server.daemon_threads = True
    print(json.dumps({'ready': True, 'model': model.version, 'port': args.port}), flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
