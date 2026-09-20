#!/usr/bin/env python3
"""导出并重放逐甲ROI SegFormer-B0静态ONNX可行性证据。

本脚本只构造确定性随机权重网络，用于验证架构、ONNX导出、算子和静态
输入输出合同；它不产生质量结论，也不得作为候选权重或生产模型使用。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import onnx
import onnxruntime as ort
import torch
from transformers import SegformerConfig, SegformerForSemanticSegmentation


SCHEMA_VERSION = 1
DECISION = "roi_segformer_b0_static_onnx_runtime_feasible_not_quality_evidence"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def write_atomic(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise ValueError(f"报告输出已存在，禁止覆盖：{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.tmp-", dir=path.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def build_model() -> SegformerForSemanticSegmentation:
    torch.manual_seed(20260920)
    config = SegformerConfig(
        num_channels=3,
        num_labels=1,
        depths=[2, 2, 2, 2],
        hidden_sizes=[32, 64, 160, 256],
        decoder_hidden_size=256,
        num_attention_heads=[1, 2, 5, 8],
        sr_ratios=[8, 4, 2, 1],
        patch_sizes=[7, 3, 3, 3],
        strides=[4, 2, 2, 2],
        mlp_ratios=[4, 4, 4, 4],
        semantic_loss_ignore_index=255,
    )
    model = SegformerForSemanticSegmentation(config)
    model.eval()
    return model


class LogitsOnly(torch.nn.Module):
    def __init__(self, model: SegformerForSemanticSegmentation) -> None:
        super().__init__()
        self.model = model

    def forward(self, pixel_values: torch.Tensor) -> torch.Tensor:
        return self.model(pixel_values=pixel_values, return_dict=False)[0]


def inspect_onnx(model_path: Path, input_size: int) -> dict[str, Any]:
    model = onnx.load(str(model_path))
    onnx.checker.check_model(model, full_check=True)
    session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    input_meta = session.get_inputs()[0]
    output_meta = session.get_outputs()[0]
    sample = np.linspace(0.0, 1.0, 3 * input_size * input_size, dtype=np.float32).reshape(
        1, 3, input_size, input_size
    )
    output = session.run([output_meta.name], {input_meta.name: sample})[0]
    if tuple(output.shape) != (1, 1, input_size // 4, input_size // 4):
        raise ValueError(f"ONNX输出尺寸不符合SegFormer 1/4分辨率合同：{output.shape}")
    if not np.isfinite(output).all():
        raise ValueError("ONNX输出包含非有限值")
    ops = sorted({node.op_type for node in model.graph.node})
    return {
        "input": {"name": input_meta.name, "shape": input_meta.shape, "type": input_meta.type},
        "output": {"name": output_meta.name, "shape": list(output.shape), "type": output_meta.type},
        "operators": ops,
        "operatorCount": len(model.graph.node),
        "runtimeProviders": session.get_providers(),
        "sampleOutput": {
            "minimum": float(output.min()),
            "maximum": float(output.max()),
            "mean": float(output.mean()),
            "finite": True,
        },
    }


def export_model(model_path: Path, input_size: int) -> dict[str, Any]:
    if model_path.exists():
        raise ValueError(f"模型输出已存在，禁止覆盖：{model_path}")
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model = build_model()
    wrapped = LogitsOnly(model).eval()
    sample = torch.linspace(0.0, 1.0, 3 * input_size * input_size, dtype=torch.float32).reshape(
        1, 3, input_size, input_size
    )
    with torch.inference_mode():
        torch.onnx.export(
            wrapped,
            (sample,),
            str(model_path),
            input_names=["pixel_values"],
            output_names=["logits"],
            opset_version=17,
            do_constant_folding=True,
            dynamo=False,
        )
    parameters = sum(parameter.numel() for parameter in model.parameters())
    return {
        "architecture": "SegFormer-B0-compatible binary ROI segmenter",
        "parameters": parameters,
        "inputSize": input_size,
        "outputStride": 4,
        "weights": "deterministic-random-feasibility-only",
    }


def build_report(model_path: Path, input_size: int, *, export: bool) -> dict[str, Any]:
    architecture = export_model(model_path, input_size) if export else {
        "architecture": "SegFormer-B0-compatible binary ROI segmenter",
        "parameters": sum(parameter.numel() for parameter in build_model().parameters()),
        "inputSize": input_size,
        "outputStride": 4,
        "weights": "deterministic-random-feasibility-only",
    }
    if not model_path.is_file():
        raise ValueError(f"ONNX模型不存在：{model_path}")
    runtime = inspect_onnx(model_path, input_size)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "ok": True,
        "decision": DECISION,
        "scope": {
            "proves": [
                "SegFormer-B0-compatible ROI architecture exports as a static ONNX graph",
                "ONNX checker accepts the graph",
                "ONNX Runtime CPU executes the graph with the frozen input/output contract",
            ],
            "doesNotProve": [
                "nail boundary quality",
                "candidate recall",
                "WebGPU or WASM browser latency",
                "release eligibility",
            ],
            "trainingUse": "prohibited",
            "candidateUse": "prohibited",
        },
        "architecture": architecture,
        "model": {
            "path": str(model_path.resolve()),
            "sha256": sha256_file(model_path),
            "bytes": model_path.stat().st_size,
            "opset": 17,
        },
        "runtime": runtime,
        "environment": {
            "python": os.sys.version.split()[0],
            "torch": torch.__version__,
            "transformers": __import__("transformers").__version__,
            "onnx": onnx.__version__,
            "onnxruntime": ort.__version__,
        },
        "contractSha256": canonical_sha256({"inputSize": input_size, "outputStride": 4, "opset": 17}),
        "errors": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model")
    parser.add_argument("--report")
    parser.add_argument("--input-size", type=int, default=384)
    parser.add_argument("--verify-report")
    args = parser.parse_args()

    if args.verify_report:
        report_path = Path(args.verify_report).resolve()
        existing = json.loads(report_path.read_text(encoding="utf-8"))
        model_path = Path(existing["model"]["path"]).resolve()
        replay = build_report(model_path, int(existing["architecture"]["inputSize"]), export=False)
        if replay != existing:
            raise ValueError("可行性报告与当前ONNX或运行环境重放结果不一致")
        print(json.dumps({"ok": True, "decision": "verified", "report": str(report_path)}, ensure_ascii=False))
        return 0

    if not args.model or not args.report:
        raise ValueError("构建模式必须提供--model与--report")
    if args.input_size <= 0 or args.input_size % 32 != 0:
        raise ValueError("input-size必须为正数且可被32整除")
    report = build_report(Path(args.model).resolve(), args.input_size, export=True)
    write_atomic(Path(args.report).resolve(), report)
    print(json.dumps({"ok": True, "decision": report["decision"], "model": report["model"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
