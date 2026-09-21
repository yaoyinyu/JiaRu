#!/usr/bin/env python3
"""审计循环016第五轮DINOv2高分辨率边界解码器的零训练可达性。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import onnx
import onnxruntime as ort
import torch
import torch.nn.functional as F
from torch import nn
from transformers import AutoModel


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_atomic(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise ValueError(f"报告已存在，禁止覆盖：{path}")
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


class ConvBlock(nn.Module):
    def __init__(self, input_channels: int, output_channels: int, *, stride: int = 1) -> None:
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv2d(input_channels, output_channels, 3, stride=stride, padding=1, bias=False),
            nn.GroupNorm(8, output_channels),
            nn.GELU(),
            nn.Conv2d(output_channels, output_channels, 3, padding=1, bias=False),
            nn.GroupNorm(8, output_channels),
            nn.GELU(),
        )

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        return self.block(value)


class Dinov2HighResBoundarySegmenter(nn.Module):
    def __init__(self, backbone: nn.Module) -> None:
        super().__init__()
        self.backbone = backbone
        self.spatial384 = ConvBlock(3, 32)
        self.spatial192 = ConvBlock(32, 48, stride=2)
        self.spatial96 = ConvBlock(48, 64, stride=2)
        self.semantic96 = ConvBlock(384, 128)
        self.decode96 = ConvBlock(128 + 64, 96)
        self.decode192 = ConvBlock(96 + 48, 64)
        self.decode384 = ConvBlock(64 + 32, 32)
        self.output = nn.Conv2d(32, 1, 1)

    def forward(self, pixel_values: torch.Tensor) -> torch.Tensor:
        spatial384 = self.spatial384(pixel_values)
        spatial192 = self.spatial192(spatial384)
        spatial96 = self.spatial96(spatial192)
        padded = F.pad(pixel_values, (4, 4, 4, 4), mode="replicate")
        tokens = self.backbone(
            pixel_values=padded,
            interpolate_pos_encoding=True,
            return_dict=False,
        )[0][:, 1:, :]
        semantic = tokens.transpose(1, 2).reshape(pixel_values.shape[0], 384, 28, 28)
        semantic96 = F.interpolate(self.semantic96(semantic), size=(96, 96), mode="bilinear", align_corners=False)
        decoded96 = self.decode96(torch.cat((semantic96, spatial96), dim=1))
        decoded192 = F.interpolate(decoded96, size=(192, 192), mode="bilinear", align_corners=False)
        decoded192 = self.decode192(torch.cat((decoded192, spatial192), dim=1))
        decoded384 = F.interpolate(decoded192, size=(384, 384), mode="bilinear", align_corners=False)
        return self.output(self.decode384(torch.cat((decoded384, spatial384), dim=1)))


def load_model(plan: dict[str, Any]) -> Dinov2HighResBoundarySegmenter:
    prerequisite = plan["prerequisites"]
    weight_path = Path(prerequisite["pretrainedWeight"])
    if sha256_file(weight_path) != prerequisite["pretrainedWeightSha256"]:
        raise ValueError("DINOv2冻结权重哈希不一致")
    torch.manual_seed(1605)
    backbone = AutoModel.from_pretrained(
        prerequisite["huggingFaceModelId"],
        revision=prerequisite["huggingFaceRevision"],
        cache_dir=str(weight_path.parents[2]),
        local_files_only=True,
    )
    return Dinov2HighResBoundarySegmenter(backbone)


def validate_plan_inputs(plan: dict[str, Any]) -> None:
    prerequisite = plan["prerequisites"]
    for label, path_key, hash_key in (
        ("第四轮训练报告", "fourthPilotReport", "fourthPilotReportSha256"),
        ("许可快照manifest", "licenseSnapshotManifest", "licenseSnapshotManifestSha256"),
        ("DINOv2权重", "pretrainedWeight", "pretrainedWeightSha256"),
    ):
        path = Path(prerequisite[path_key])
        if not path.is_file() or sha256_file(path) != prerequisite[hash_key]:
            raise ValueError(f"{label}哈希不一致")
    fourth = json.loads(Path(prerequisite["fourthPilotReport"]).read_text(encoding="utf-8"))
    if fourth.get("decision") != "roi_dinov2_small_internal_pilot_fail":
        raise ValueError("第四轮失败结论未冻结")


def inspect_onnx(model_path: Path, expected_output: list[int]) -> dict[str, Any]:
    model = onnx.load(str(model_path))
    onnx.checker.check_model(model, full_check=True)
    session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    input_meta = session.get_inputs()[0]
    output_meta = session.get_outputs()[0]
    sample = np.linspace(-1.0, 1.0, 3 * 384 * 384, dtype=np.float32).reshape(1, 3, 384, 384)
    output = session.run([output_meta.name], {input_meta.name: sample})[0]
    if list(output.shape) != expected_output or not np.isfinite(output).all():
        raise ValueError("ONNX静态输出合同失败")
    return {
        "input": {"name": input_meta.name, "shape": input_meta.shape, "type": input_meta.type},
        "output": {"name": output_meta.name, "shape": list(output.shape), "type": output_meta.type},
        "operators": sorted({node.op_type for node in model.graph.node}),
        "operatorCount": len(model.graph.node),
        "runtimeProviders": session.get_providers(),
        "sampleOutput": {
            "minimum": float(output.min()),
            "maximum": float(output.max()),
            "mean": float(output.mean()),
            "finite": True,
        },
    }


def measure_cuda_training_memory(model: nn.Module, maximum: int) -> dict[str, Any]:
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA不可用，无法验证第五轮显存门")
    model.backbone.gradient_checkpointing_enable()
    device = torch.device("cuda")
    model = model.to(device).train()
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    sample = torch.linspace(-1.0, 1.0, 2 * 3 * 384 * 384, device=device, dtype=torch.float32).reshape(2, 3, 384, 384)
    truth = torch.zeros((2, 1, 384, 384), device=device, dtype=torch.float32)
    with torch.amp.autocast(device_type="cuda"):
        logits = model(sample)
        loss = F.binary_cross_entropy_with_logits(logits, truth) + (torch.sigmoid(logits) - truth).abs().mean()
    loss.backward()
    torch.cuda.synchronize()
    peak = int(torch.cuda.max_memory_allocated())
    if peak > maximum:
        raise ValueError(f"batch2显存峰值超过预注册上限：{peak}>{maximum}")
    return {
        "device": torch.cuda.get_device_name(0),
        "physicalBatchSize": 2,
        "inputShape": [2, 3, 384, 384],
        "forwardBackwardFinite": bool(torch.isfinite(loss).item()),
        "peakAllocatedBytes": peak,
        "maximumBytes": maximum,
        "withinCap": True,
        "gradientCheckpointing": True,
        "mixedPrecision": True,
    }


def export_and_report(plan_path: Path, model_path: Path, report_path: Path) -> dict[str, Any]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    validate_plan_inputs(plan)
    if model_path.exists():
        raise ValueError(f"ONNX输出已存在，禁止覆盖：{model_path}")
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model = load_model(plan).eval()
    architecture = plan["architecture"]
    parameter_count = sum(parameter.numel() for parameter in model.parameters())
    if parameter_count > int(architecture["maximumParameters"]):
        raise ValueError("参数量超过预注册上限")
    sample = torch.zeros(tuple(architecture["inputShape"]), dtype=torch.float32)
    with torch.inference_mode():
        eager = model(sample)
        if list(eager.shape) != architecture["outputShape"] or not torch.isfinite(eager).all():
            raise ValueError("PyTorch静态输入输出合同失败")
        torch.onnx.export(
            model,
            (sample,),
            str(model_path),
            input_names=["pixel_values"],
            output_names=["logits"],
            opset_version=int(architecture["opset"]),
            do_constant_folding=True,
            dynamo=False,
        )
    runtime = inspect_onnx(model_path, architecture["outputShape"])
    bytes_count = model_path.stat().st_size
    if bytes_count > int(architecture["maximumFp32OnnxBytes"]):
        raise ValueError("FP32 ONNX超过预注册体积上限")
    cuda_memory = measure_cuda_training_memory(model, int(architecture["maximumCudaPeakAllocatedBytesBatch2"]))
    report = {
        "schemaVersion": 1,
        "ok": True,
        "decision": "dinov2_highres_decoder_static_feasible_pending_browser_runtime",
        "scope": plan["scope"],
        "inputs": {
            "plan": {"path": str(plan_path), "sha256": sha256_file(plan_path)},
            "fourthPilotReport": {"path": plan["prerequisites"]["fourthPilotReport"], "sha256": plan["prerequisites"]["fourthPilotReportSha256"]},
            "licenseSnapshotManifest": {"path": plan["prerequisites"]["licenseSnapshotManifest"], "sha256": plan["prerequisites"]["licenseSnapshotManifestSha256"]},
            "pretrainedWeight": {"path": plan["prerequisites"]["pretrainedWeight"], "sha256": plan["prerequisites"]["pretrainedWeightSha256"]},
        },
        "reachability": plan["reachability"],
        "singleChangedVariable": plan["singleChangedVariable"],
        "architecture": {**architecture, "parameterCount": parameter_count},
        "model": {"path": str(model_path), "sha256": sha256_file(model_path), "bytes": bytes_count, "withinCap": True},
        "runtime": runtime,
        "cudaTrainingMemory": cuda_memory,
        "browserRuntime": {"status": "pending", "requiredBackends": architecture["requiredBackends"]},
        "environment": {"python": os.sys.version.split()[0], "torch": torch.__version__, "transformers": __import__("transformers").__version__, "onnx": onnx.__version__, "onnxruntime": ort.__version__},
        "errors": [],
    }
    write_atomic(report_path, report)
    return report


def verify(report_path: Path) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    for label, binding in report["inputs"].items():
        if sha256_file(Path(binding["path"])) != binding["sha256"]:
            raise ValueError(f"输入哈希漂移：{label}")
    if sha256_file(Path(report["model"]["path"])) != report["model"]["sha256"]:
        raise ValueError("ONNX模型哈希漂移")
    runtime = inspect_onnx(Path(report["model"]["path"]), report["architecture"]["outputShape"])
    if runtime != report["runtime"]:
        raise ValueError("ONNX运行时重放结果不一致")
    if report.get("ok") is not True or report.get("decision") != "dinov2_highres_decoder_static_feasible_pending_browser_runtime":
        raise ValueError("可行性结论不符合合同")
    return {"ok": True, "decision": "verified_dinov2_highres_decoder_static_feasible_pending_browser", "model": report["model"], "cudaTrainingMemory": report["cudaTrainingMemory"]}


def verify_browser(report_path: Path) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("ok") is not True or report.get("decision") != "dinov2_highres_decoder_browser_feasible_for_fifth_pilot":
        raise ValueError("浏览器报告结论不符合合同")
    for label, binding in report["inputs"].items():
        path = Path(binding["path"])
        if not path.is_file() or sha256_file(path) != binding["sha256"]:
            raise ValueError(f"浏览器证据哈希漂移：{label}")
    feasibility = json.loads(Path(report["inputs"]["feasibilityReport"]["path"]).read_text(encoding="utf-8"))
    if feasibility.get("decision") != "dinov2_highres_decoder_static_feasible_pending_browser_runtime":
        raise ValueError("上游静态可行性报告未通过")
    if feasibility["model"]["sha256"] != report["model"]["sha256"]:
        raise ValueError("浏览器报告与上游ONNX身份不一致")
    runtime = report["browserRuntime"]
    if runtime.get("webgpuExposed") is not True or "HeadlessChrome/153" not in runtime.get("userAgent", ""):
        raise ValueError("浏览器或WebGPU环境合同未满足")
    results = runtime.get("results", [])
    if {row.get("backend") for row in results} != {"wasm", "webgpu"}:
        raise ValueError("浏览器后端集合不完整")
    for row in results:
        if not (
            row.get("ok") is True
            and row.get("finite") is True
            and row.get("inputNames") == ["pixel_values"]
            and row.get("outputNames") == ["logits"]
            and row.get("outputDims") == [1, 1, 384, 384]
            and float(row.get("initMs", -1)) >= 0
            and float(row.get("inferMs", -1)) >= 0
        ):
            raise ValueError(f"浏览器后端结果失败：{row.get('backend')}")
    snapshot = Path(report["inputs"]["playwrightSnapshot"]["path"]).read_text(encoding="utf-8").replace('\\"', '"')
    evaluation = Path(report["inputs"]["playwrightEval"]["path"]).read_text(encoding="utf-8").replace('\\"', '"')
    for token in ('"webgpuExposed": true', '"backend": "wasm"', '"backend": "webgpu"', '"finite": true'):
        if token not in snapshot or token not in evaluation:
            raise ValueError(f"Playwright证据缺少字段：{token}")
    console_lines = [line for line in Path(report["inputs"]["consoleLog"]["path"]).read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(console_lines) != 1 or "favicon.ico" not in console_lines[0] or "404" not in console_lines[0]:
        raise ValueError("浏览器控制台出现未登记错误")
    return {"ok": True, "decision": "verified_dinov2_highres_decoder_browser_feasible_for_fifth_pilot", "model": report["model"], "backends": sorted(row["backend"] for row in results)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--verify-report", type=Path)
    parser.add_argument("--verify-browser-report", type=Path)
    args = parser.parse_args()
    if args.verify_browser_report:
        print(json.dumps(verify_browser(args.verify_browser_report), ensure_ascii=False, indent=2))
    elif args.verify_report:
        print(json.dumps(verify(args.verify_report), ensure_ascii=False, indent=2))
    else:
        if not args.plan or not args.model or not args.report:
            parser.error("构建需要--plan、--model与--report")
        print(json.dumps(export_and_report(args.plan, args.model, args.report), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
