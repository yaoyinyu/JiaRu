"""WeVisOne-VL 本地抠图引擎。

4B 检查点整卡 bf16 需要约 9.7 GB，8 GB 显卡放不下；这里用 int4（optimum-quanto
TinyGemm）把权重压到约 2.4 GiB，峰值显存 5.8 GiB，单图约 6 秒。

本文件只负责「加载模型 + 推理」，对外 HTTP 服务见 server.py，命令行用法见 README.md。

命令行（单图调试）：
    python matting.py --image in.jpg --query 指甲
    python matting.py --image in.jpg --task visual_prompt --boxes 120,300,260,420
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Sequence

# transformers 5.x 默认用线程池「异步物化」权重（core_model_loading.GLOBAL_WORKERS=min(4,cpu)），
# 多个线程同时读 mmap 的 safetensors 在 Windows 上会随机触发 0xC0000005（访问冲突，
# 崩在 torch/storage.py __getitem__）。官方开关 HF_DEACTIVATE_ASYNC_LOAD 可退回同步加载，
# 代价是加载慢 1–2s。必须在 import transformers 之前设置。
os.environ.setdefault("HF_DEACTIVATE_ASYNC_LOAD", "1")

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src" / "WeVisOne-VL-main"
DEFAULT_MODEL = ROOT / "models" / "WeVisOne-VL-4B-bf16"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# 2026-10-28 参数基准（int4，RTX 4060 Laptop 8GB，业务同款 1600 长边 JPEG q0.85）：
# - 589824（约 0.59MP）在 hero-hand（5 甲）、ai-look-1/2/4/5（各 5 甲）、
#   ai-look-3（双手 9 甲）全部按 `<OBJ>` 逐甲返回，单图 11.8–18.7s；
# - 1048576 在 hero-hand 只返回 1 个 `<OBJ>`（响应里有 5 个框），可复现，故不作为默认；
# - bf16 卸载（--quant none --device-map 5）虽 5/5，但单图 51–55s，仅作对照。
DEFAULT_MAX_PIXELS = 589824


def vram_report() -> dict[str, float]:
    import torch

    if not torch.cuda.is_available():
        log("CUDA 不可用")
        return {}
    free, total = torch.cuda.mem_get_info()
    log(
        f"cuda: {torch.cuda.get_device_name(0)} | torch {torch.__version__} | "
        f"free {free / 2**30:.2f} / {total / 2**30:.2f} GiB"
    )
    return {"free_gib": free / 2**30, "total_gib": total / 2**30}


def install_cpu_dtype_shim() -> None:
    """让上游引擎在 CPU 上保持 bf16（它把 CPU 分支写死成 float32，4B 需要 19 GB 内存）。"""
    import torch

    import wevisone_vl.engine as engine_module

    class _Shim:
        def __init__(self, real, overrides):
            object.__setattr__(self, "_real", real)
            object.__setattr__(self, "_overrides", overrides)

        def __getattr__(self, name):
            overrides = object.__getattribute__(self, "_overrides")
            if name in overrides:
                return overrides[name]
            return getattr(object.__getattribute__(self, "_real"), name)

    engine_module.torch = _Shim(torch, {"float32": torch.bfloat16})
    log("已安装 CPU dtype shim（float32 -> bfloat16）")


def repoint_to_cuda(module) -> int:
    """绕过 quanto 的 .to()，把残余参数/缓冲区直接搬上卡。"""
    moved = 0
    for _, p in list(module.named_parameters(recurse=True)):
        if p.device.type != "cuda":
            p.data = p.data.to("cuda:0")
            moved += 1
    for _, b in list(module.named_buffers(recurse=True)):
        if b.device.type != "cuda":
            b.data = b.data.to("cuda:0")
            moved += 1
    return moved


def quantize_int4_streaming(engine) -> None:
    """逐容器在 GPU 上做 int4 量化。

    两条 quanto 限制决定了这个形状：
    * 对裸 nn.Linear 调 quantize() 会把 weight 置空，必须喂整层容器；
    * 量化后再 model.to("cuda") 会重打包全部张量，实测卡死（>7 分钟），
      所以每个容器先搬上卡、再原地量化、留在卡上。

    mask_decoder 故意保持 bf16：它只有 36 MB，却决定 alpha 的边缘质量。
    """
    import torch

    from optimum.quanto import freeze, qint4, quantize

    model = engine.model
    t0 = time.time()
    layers = list(model.model.language_model.layers)
    for layer in layers:
        layer.to("cuda:0")
        quantize(layer, weights=qint4)
        freeze(layer)
    log(f"int4：{len(layers)} 层 LLM 已量化，用时 {time.time() - t0:.1f}s")

    t0 = time.time()
    visual = model.model.visual
    visual.to("cuda:0")
    quantize(visual, weights=qint4)
    freeze(visual)
    moved = repoint_to_cuda(model)
    engine.mask_decoder.to(device="cuda:0", dtype=torch.bfloat16)
    engine.device = torch.device("cuda:0")
    free, total = torch.cuda.mem_get_info()
    log(
        f"int4：视觉塔 + {moved} 个残余张量已上卡，用时 {time.time() - t0:.1f}s | "
        f"显存 {(total - free) / 2**30:.2f}/{total / 2**30:.2f} GiB"
    )


def build_engine(
    model_dir: Path = DEFAULT_MODEL,
    quant: str = "int4",
    max_pixels: int = DEFAULT_MAX_PIXELS,
    device: str = "cuda",
    offload_gib: float | None = None,
):
    from wevisone_vl.engine import WeVisOneVL

    if offload_gib is not None:
        # 混合卸载：权重按显存预算分布，放不下的层留在内存（bf16，约 9 GiB）。
        # 只用于 bf16：quanto 的 qint4 内核要求整层在卡上，卸载后无法量化。
        if quant != "none":
            raise ValueError("混合卸载只支持 --quant none（int4 需要整层在 GPU 上量化）")
        import torch
        from accelerate import dispatch_model, infer_auto_device_map

        install_cpu_dtype_shim()
        t0 = time.time()
        engine = WeVisOneVL(
            str(model_dir),
            backend="transformers",
            device="cpu",
            dtype="bfloat16",
            max_pixels=max_pixels,
            attention_implementation="sdpa",
            decoder_batch_size=4,
        )
        log(f"模型已在 CPU 加载（bf16），用时 {time.time() - t0:.1f}s")

        t0 = time.time()
        model = engine.model
        device_map = infer_auto_device_map(
            model,
            max_memory={0: f"{offload_gib}GiB", "cpu": "48GiB"},
        )
        dispatch_model(model, device_map=device_map)
        engine.device = model.device
        engine.mask_decoder.to(device="cuda:0", dtype=torch.bfloat16)
        free, total = torch.cuda.mem_get_info()
        on_gpu = sum(1 for target in device_map.values() if target == 0)
        log(
            f"混合卸载完成，用时 {time.time() - t0:.1f}s | "
            f"GPU 层 {on_gpu}/{len(device_map)} | 显存 {(total - free) / 2**30:.2f}/{total / 2**30:.2f} GiB"
        )
        return engine

    if quant == "int4":
        # CPU 上 bf16 加载，再逐层搬上卡量化。
        install_cpu_dtype_shim()
        t0 = time.time()
        engine = WeVisOneVL(
            str(model_dir),
            backend="transformers",
            device="cpu",
            dtype="bfloat16",
            max_pixels=max_pixels,
            attention_implementation="sdpa",
            decoder_batch_size=4,
        )
        log(f"模型已在 CPU 加载，用时 {time.time() - t0:.1f}s")
        quantize_int4_streaming(engine)
        return engine

    if device == "cuda":
        t0 = time.time()
        engine = WeVisOneVL(
            str(model_dir),
            backend="transformers",
            device="cuda:0",
            dtype="bfloat16",
            max_pixels=max_pixels,
            attention_implementation="sdpa",
            decoder_batch_size=8,
        )
        log(f"模型已在 CUDA 加载，用时 {time.time() - t0:.1f}s")
        return engine

    install_cpu_dtype_shim()
    t0 = time.time()
    engine = WeVisOneVL(
        str(model_dir),
        backend="transformers",
        device="cpu",
        dtype="bfloat16",
        max_pixels=max_pixels,
        attention_implementation="sdpa",
        decoder_batch_size=4,
    )
    log(f"模型已在 CPU 加载，用时 {time.time() - t0:.1f}s")
    return engine


def encode_alpha(alpha, threshold: int = 127) -> dict[str, Any]:
    """把 0..1 的浮点 alpha 编成 PNG data URI，并给出面积与外接框。"""
    import numpy as np
    from PIL import Image

    arr = np.clip(np.asarray(alpha, dtype=np.float32), 0.0, 1.0)
    u8 = np.rint(arr * 255.0).astype(np.uint8)

    buf = io.BytesIO()
    Image.fromarray(u8, mode="L").save(buf, format="PNG", optimize=True)
    payload = base64.b64encode(buf.getvalue()).decode("ascii")

    solid = u8 > threshold
    area = int(solid.sum())
    ys, xs = np.nonzero(solid)
    bbox = (
        [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]
        if area
        else [0, 0, 0, 0]
    )
    return {
        "alphaPng": "data:image/png;base64," + payload,
        "alphaBytes": len(buf.getvalue()),
        "area": area,
        "bbox": bbox,
        "height": int(u8.shape[0]),
        "width": int(u8.shape[1]),
    }


def decode_image(source: str):
    """接受 data URI、纯 base64 或本地路径。"""
    from PIL import Image

    if source.startswith("data:"):
        header, _, payload = source.partition(",")
        if ";base64" not in header:
            raise ValueError("只支持 base64 data URI")
        raw = base64.b64decode(payload, validate=False)
        return Image.open(io.BytesIO(raw)).convert("RGB")
    if len(source) > 512 or "\n" in source:
        return Image.open(io.BytesIO(base64.b64decode(source, validate=False))).convert("RGB")
    return Image.open(source).convert("RGB")


class MatteEngine:
    """加载一次、反复推理；线程内串行使用（GPU 并发 1）。"""

    def __init__(
        self,
        model_dir: Path = DEFAULT_MODEL,
        quant: str = "int4",
        max_pixels: int = DEFAULT_MAX_PIXELS,
        device: str = "cuda",
        offload_gib: float | None = None,
    ) -> None:
        self.model_dir = Path(model_dir)
        self.quant = quant
        self.max_pixels = max_pixels
        self.device = device
        self.offload_gib = offload_gib
        self.engine = None
        self.ready_at: float | None = None
        self.load_seconds: float | None = None
        self.requests = 0
        self.failures = 0
        self.last_latency_s: float | None = None

    def load(self) -> None:
        if not self.model_dir.is_dir():
            raise FileNotFoundError(f"模型目录不存在：{self.model_dir}")
        t0 = time.time()
        self.engine = build_engine(
            self.model_dir, self.quant, self.max_pixels, self.device, self.offload_gib
        )
        self.load_seconds = time.time() - t0
        self.ready_at = time.time()
        mode = f"offload<={self.offload_gib}GiB" if self.offload_gib is not None else self.quant
        log(f"就绪：{self.model_dir.name} | mode={mode} | 总加载 {self.load_seconds:.1f}s")

    def matte(
        self,
        image,
        *,
        task: str = "matting",
        query: str = "",
        boxes: Sequence[Sequence[float]] | None = None,
        threshold: int = 127,
    ) -> dict[str, Any]:
        if self.engine is None:
            raise RuntimeError("引擎尚未加载")

        kwargs: dict[str, Any] = {"task": task, "query": query, "temperature": 0.0}
        if boxes:
            kwargs["reference_boxes"] = [list(map(float, b)) for b in boxes]

        t0 = time.time()
        result = self.engine.predict(image, **kwargs)
        elapsed = time.time() - t0

        instances = []
        width, height = int(image.width), int(image.height)
        for index, alpha in enumerate(result.masks):
            item = encode_alpha(alpha, threshold)
            item["index"] = index
            # 上游 boxes 是 0..1 归一化坐标（engine.py 里 /1000），这里同时给出像素框，
            # 便于前端直接和自己的候选框做 IoU 匹配。
            if index < len(result.boxes):
                bx = [float(v) for v in result.boxes[index]]
                item["box01"] = [round(v, 5) for v in bx]
                item["box"] = [
                    round(bx[0] * width, 1),
                    round(bx[1] * height, 1),
                    round(bx[2] * width, 1),
                    round(bx[3] * height, 1),
                ]
            instances.append(item)

        self.requests += 1
        self.last_latency_s = elapsed
        return {
            "ok": True,
            "prompt": result.prompt,
            "response": result.response,
            "width": int(image.width),
            "height": int(image.height),
            "task": task,
            "query": query,
            "instances": instances,
            "metrics": {
                "inference_s": round(elapsed, 3),
                "engine_latency_s": round(float(result.latency_s), 3),
                "instance_count": len(instances),
                "load_s": round(self.load_seconds or 0.0, 1),
            },
        }


def parse_boxes(text: str | None) -> list[list[float]] | None:
    if not text:
        return None
    boxes: list[list[float]] = []
    for chunk in text.replace(";", "|").split("|"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = [p for p in chunk.replace(" ", ",").split(",") if p.strip()]
        if len(parts) != 4:
            raise SystemExit(f"box 需要 4 个数字，收到：{chunk}")
        boxes.append([float(p) for p in parts])
    return boxes or None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--query", default="指甲")
    ap.add_argument("--task", default="matting")
    ap.add_argument("--boxes", default=None, help="x1,y1,x2,y2|x1,y1,x2,y2（visual_prompt 用）")
    ap.add_argument("--model", default=str(DEFAULT_MODEL))
    ap.add_argument("--out", default=str(ROOT / "out"))
    ap.add_argument("--quant", default="int4", choices=["int4", "none"])
    ap.add_argument("--device", default="cuda", choices=["cuda", "cpu"])
    ap.add_argument("--max-pixels", type=int, default=1024 * 1024)
    args = ap.parse_args()

    vram_report()
    image_path = Path(args.image)
    if not image_path.is_file():
        log(f"找不到图片：{image_path}")
        return 2

    model = MatteEngine(Path(args.model), args.quant, args.max_pixels, args.device)
    model.load()

    image = decode_image(str(image_path))
    log(f"{image_path.name} {image.width}x{image.height} | task={args.task} query={args.query!r}")

    payload = model.matte(image, task=args.task, query=args.query, boxes=parse_boxes(args.boxes))
    out_dir = Path(args.out) / image_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)

    for item in payload["instances"]:
        raw = base64.b64decode(item["alphaPng"].split(",", 1)[1])
        (out_dir / f"alpha-{item['index']}.png").write_bytes(raw)
        log(f"alpha-{item['index']}.png  area={item['area']} bbox={item['bbox']}")

    (out_dir / "result.json").write_text(
        json.dumps({k: v for k, v in payload.items() if k != "instances"} | {
            "instances": [{k: v for k, v in i.items() if k != "alphaPng"} for i in payload["instances"]]
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(payload["response"])
    log(f"输出目录：{out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
