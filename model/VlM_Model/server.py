"""WeVisOne-VL 抠图服务（本机常驻，仅监听 127.0.0.1）。

启动：
    python server.py                       # 默认 127.0.0.1:8008
    python server.py --port 8010           # 换端口
    python server.py --max-pixels 524288   # 降分辨率换速度（单图约 3.3s）

三条设计约束：
* **所有 CUDA 调用都在主线程**。模型在主线程加载、在主线程推理；HTTP 服务跑在
  子线程里，只负责收包和回收结果。原因：quantized（TinyGemm）模型跨线程推理会
  直接报 `fatal : Memory allocation failure`，实测必现。
* GPU 并发固定为 1：队列深度 1，正在推理时新请求立即 503（busy），由调用方
  （Next.js 路由）回退浏览器本地路径，不排队堆积。
* 不落盘：图片只在内存里解码，alpha 以 data URI 返回。命令行模式的 matting.py
  才写文件，那是人工调试用的。

接口见 README.md。
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import sys
import threading
import time
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from matting import DEFAULT_MAX_PIXELS, DEFAULT_MODEL, MatteEngine, decode_image, log

MAX_BODY_BYTES = 12 * 1024 * 1024
JOB_TIMEOUT_S = 120.0
STATE: dict[str, Any] = {}


class Job:
    """一次推理请求。字段由 HTTP 线程填，由主线程消费。"""

    __slots__ = ("image", "task", "query", "boxes", "done", "result", "error")

    def __init__(self, image, task: str, query: str, boxes):
        self.image = image
        self.task = task
        self.query = query
        self.boxes = boxes
        self.done = threading.Event()
        self.result: dict[str, Any] | None = None
        self.error: BaseException | None = None


def worker_loop(jobs: "queue.Queue[Job | None]", engine: MatteEngine) -> None:
    """主线程：唯一的 CUDA 执行者。"""
    while True:
        job = jobs.get()
        if job is None:
            return
        try:
            job.result = engine.matte(job.image, task=job.task, query=job.query, boxes=job.boxes)
        except BaseException as exc:  # noqa: BLE001
            engine.failures += 1
            job.error = exc
            log(f"推理失败：{type(exc).__name__}: {exc}")
        finally:
            job.image = None
            job.done.set()


def json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "JiaRuMatte/1.0"
    sys_version = ""

    def reply(self, status: int, payload: dict[str, Any]) -> None:
        body = json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        # 只记方法、路径、状态与耗时；绝不记录请求体（可能含图片）。
        log(f"{self.client_address[0]} {fmt % args}")

    def authorized(self) -> bool:
        token = STATE["token"]
        if not token:
            return True
        return self.headers.get("Authorization", "") == f"Bearer {token}"

    # ── GET ──
    def do_GET(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        engine: MatteEngine = STATE["engine"]
        if path == "/health":
            self.reply(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "ready": engine.engine is not None,
                    "busy": STATE["jobs"].qsize() > 0,
                    "model": engine.model_dir.name,
                    "quant": engine.quant,
                    "device": engine.device,
                    "maxPixels": engine.max_pixels,
                    "loadSeconds": round(engine.load_seconds or 0.0, 1),
                    "requests": engine.requests,
                    "failures": engine.failures,
                    "lastLatencySeconds": engine.last_latency_s,
                    "uptimeSeconds": round(time.time() - STATE["started_at"], 1),
                },
            )
            return
        if path == "/stats":
            self.reply(
                HTTPStatus.OK,
                {
                    "requests": engine.requests,
                    "failures": engine.failures,
                    "lastLatencySeconds": engine.last_latency_s,
                    "queued": STATE["jobs"].qsize(),
                },
            )
            return
        self.reply(
            HTTPStatus.NOT_FOUND,
            {"error": "未知路径", "paths": ["GET /health", "GET /stats", "POST /matte"]},
        )

    # ── POST /matte ──
    def do_POST(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        if path != "/matte":
            self.reply(HTTPStatus.NOT_FOUND, {"error": "未知路径"})
            return
        if not self.authorized():
            self.reply(HTTPStatus.UNAUTHORIZED, {"error": "token 无效"})
            return

        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            self.reply(HTTPStatus.BAD_REQUEST, {"error": "缺少请求体"})
            return
        if length > MAX_BODY_BYTES:
            self.reply(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                {"error": f"请求体超过 {MAX_BODY_BYTES // (1024 * 1024)} MB，请先压缩图片"},
            )
            return

        try:
            payload = json.loads(self.rfile.read(length))
        except Exception:  # noqa: BLE001
            self.reply(HTTPStatus.BAD_REQUEST, {"error": "请求体不是合法 JSON"})
            return

        source = payload.get("image") or payload.get("imagePath") or ""
        if not source:
            self.reply(HTTPStatus.BAD_REQUEST, {"error": "缺少 image（data URI）或 imagePath"})
            return

        task = str(payload.get("task") or "matting")
        if task not in {"matting", "segmentation", "visual_prompt"}:
            self.reply(HTTPStatus.BAD_REQUEST, {"error": "task 只支持 matting / segmentation / visual_prompt"})
            return

        boxes = payload.get("boxes") or None
        if boxes is not None and (
            not isinstance(boxes, list) or any(not isinstance(b, list) or len(b) != 4 for b in boxes)
        ):
            self.reply(HTTPStatus.BAD_REQUEST, {"error": "boxes 需要 [[x1,y1,x2,y2], ...]"})
            return

        try:
            image = decode_image(source)
        except Exception as exc:  # noqa: BLE001
            self.reply(HTTPStatus.BAD_REQUEST, {"error": f"图片无法解码：{type(exc).__name__}"})
            return
        if max(image.width, image.height) > 4096:
            self.reply(
                HTTPStatus.BAD_REQUEST,
                {"error": f"图片长边 {max(image.width, image.height)} 超过 4096，请先缩放"},
            )
            return

        job = Job(image, task, str(payload.get("query") or "指甲"), boxes)
        try:
            STATE["jobs"].put_nowait(job)
        except queue.Full:
            self.reply(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": "服务正在处理另一张图片，请稍后重试或使用本地抠图", "busy": True, "retryAfterSeconds": 3},
            )
            return

        if not job.done.wait(timeout=JOB_TIMEOUT_S):
            self.reply(HTTPStatus.GATEWAY_TIMEOUT, {"error": "推理超时", "busy": True})
            return
        if job.error is not None:
            self.reply(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": f"推理失败：{type(job.error).__name__}"},
            )
            return

        engine: MatteEngine = STATE["engine"]
        result = job.result or {}
        result["model"] = engine.model_dir.name
        result["quant"] = engine.quant
        self.reply(HTTPStatus.OK, result)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8008)
    ap.add_argument("--model", default=str(DEFAULT_MODEL))
    ap.add_argument("--quant", default="int4", choices=["int4", "none"])
    ap.add_argument("--max-pixels", type=int, default=DEFAULT_MAX_PIXELS)
    ap.add_argument("--token", default=os.environ.get("VLM_MATTE_TOKEN", ""))
    ap.add_argument(
        "--device-map",
        type=float,
        default=None,
        metavar="GIB",
        help="混合卸载：给定显存预算（GiB），放不下的层留在内存；必须配合 --quant none",
    )
    args = ap.parse_args()

    log(f"Python {sys.version.split()[0]} | {sys.executable}")

    engine = MatteEngine(
        Path(args.model), args.quant, args.max_pixels, "cuda", args.device_map
    )
    engine.load()  # 主线程加载

    jobs: "queue.Queue[Job | None]" = queue.Queue(maxsize=1)
    STATE.update(
        {
            "engine": engine,
            "jobs": jobs,
            "token": args.token,
            "started_at": time.time(),
        }
    )

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.daemon_threads = True
    http_thread = threading.Thread(target=server.serve_forever, name="http", daemon=True)
    http_thread.start()
    log(f"监听 http://{args.host}:{args.port} | 端点 /health /stats /matte | 鉴权 {'开' if args.token else '关'}")

    try:
        worker_loop(jobs, engine)  # 主线程成为推理线程
    except KeyboardInterrupt:
        log("收到中断，正在退出")
    finally:
        jobs.put(None)
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
