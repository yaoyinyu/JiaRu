#!/usr/bin/env python3
"""审计循环016低对比边界提示分支的信号、资源与静态浏览器可达性。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import onnx
import onnxruntime as ort
import torch
import torch.nn.functional as F
from torch import nn
from torch.utils.data import DataLoader
from transformers import AutoModel


IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_module(file_name: str, module_name: str) -> Any:
    path = Path(__file__).resolve().with_name(file_name)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载模块：{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


class DeterministicBoundaryCues(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.register_buffer("mean", torch.tensor(IMAGENET_MEAN, dtype=torch.float32).reshape(1, 3, 1, 1))
        self.register_buffer("std", torch.tensor(IMAGENET_STD, dtype=torch.float32).reshape(1, 3, 1, 1))
        self.register_buffer("luminance_weights", torch.tensor((0.299, 0.587, 0.114), dtype=torch.float32).reshape(1, 3, 1, 1))
        self.register_buffer(
            "scharr_x",
            torch.tensor(((-3.0, 0.0, 3.0), (-10.0, 0.0, 10.0), (-3.0, 0.0, 3.0)), dtype=torch.float32).reshape(1, 1, 3, 3) / 16.0,
        )
        self.register_buffer(
            "scharr_y",
            torch.tensor(((-3.0, -10.0, -3.0), (0.0, 0.0, 0.0), (3.0, 10.0, 3.0)), dtype=torch.float32).reshape(1, 1, 3, 3) / 16.0,
        )

    def forward(self, pixel_values: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        rgb = torch.clamp(pixel_values * self.std + self.mean, 0.0, 1.0)
        luminance = (rgb * self.luminance_weights).sum(dim=1, keepdim=True)
        local_mean = F.avg_pool2d(luminance, kernel_size=15, stride=1, padding=7)
        local_second = F.avg_pool2d(luminance.square(), kernel_size=15, stride=1, padding=7)
        local_variance = torch.clamp(local_second - local_mean.square(), min=0.0)
        local_contrast = torch.clamp((luminance - local_mean) / torch.sqrt(local_variance + 1.0e-4), -3.0, 3.0) / 3.0
        gradient_x = F.conv2d(luminance, self.scharr_x, padding=1)
        gradient_y = F.conv2d(luminance, self.scharr_y, padding=1)
        gradient = torch.clamp(torch.sqrt(gradient_x.square() + gradient_y.square() + 1.0e-12), 0.0, 1.0)
        return local_contrast, gradient


class Dinov2BoundaryCueSegmenter(nn.Module):
    def __init__(self, backbone: nn.Module) -> None:
        super().__init__()
        self.backbone = backbone
        self.cues = DeterministicBoundaryCues()
        self.spatial384 = ConvBlock(5, 32)
        self.spatial192 = ConvBlock(32, 48, stride=2)
        self.spatial96 = ConvBlock(48, 64, stride=2)
        self.semantic96 = ConvBlock(384, 128)
        self.decode96 = ConvBlock(128 + 64, 96)
        self.decode192 = ConvBlock(96 + 48, 64)
        self.decode384 = ConvBlock(64 + 32, 32)
        self.output = nn.Conv2d(32, 1, 1)

    def forward(self, pixel_values: torch.Tensor) -> torch.Tensor:
        local_contrast, gradient = self.cues(pixel_values)
        spatial_input = torch.cat((pixel_values, local_contrast, gradient), dim=1)
        spatial384 = self.spatial384(spatial_input)
        spatial192 = self.spatial192(spatial384)
        spatial96 = self.spatial96(spatial192)
        padded = F.pad(pixel_values, (4, 4, 4, 4), mode="replicate")
        tokens = self.backbone(pixel_values=padded, interpolate_pos_encoding=True, return_dict=False)[0][:, 1:, :]
        semantic = tokens.transpose(1, 2).reshape(pixel_values.shape[0], 384, 28, 28)
        semantic96 = F.interpolate(self.semantic96(semantic), size=(96, 96), mode="bilinear", align_corners=False)
        decoded96 = self.decode96(torch.cat((semantic96, spatial96), dim=1))
        decoded192 = F.interpolate(decoded96, size=(192, 192), mode="bilinear", align_corners=False)
        decoded192 = self.decode192(torch.cat((decoded192, spatial192), dim=1))
        decoded384 = F.interpolate(decoded192, size=(384, 384), mode="bilinear", align_corners=False)
        return self.output(self.decode384(torch.cat((decoded384, spatial384), dim=1)))


def validate_plan(plan: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], Path]:
    for label, binding in plan["inputs"].items():
        path = Path(binding["path"])
        if not path.is_file() or sha256_file(path) != binding["sha256"]:
            raise ValueError(f"输入哈希不一致：{label}")
    bottleneck = json.loads(Path(plan["inputs"]["bottleneckReport"]["path"]).read_text(encoding="utf-8"))
    if bottleneck.get("decision") != "boundary_contrast_bottleneck" or not bottleneck.get("ok"):
        raise ValueError("上游边界对比度瓶颈结论未冻结")
    fifth = json.loads(Path(plan["inputs"]["fifthPilotReport"]["path"]).read_text(encoding="utf-8"))
    if fifth.get("decision") != "roi_dinov2_highres_decoder_internal_pilot_fail" or fifth.get("completedEpochs") != 30:
        raise ValueError("第五轮完整失败报告不一致")
    dataset_report = json.loads(Path(plan["inputs"]["datasetMaterializationReport"]["path"]).read_text(encoding="utf-8"))
    if dataset_report.get("datasetFilesSha256") != plan["datasetContract"]["requiredDatasetFilesSha256"]:
        raise ValueError("ROI v2文件树哈希不一致")
    review = json.loads(Path(plan["inputs"]["finalReview"]["path"]).read_text(encoding="utf-8"))
    if review.get("decision") != plan["datasetContract"]["requiredFinalReviewDecision"]:
        raise ValueError("ROI v2原分辨率全量审核未通过")
    return bottleneck, dataset_report, Path(dataset_report["outputDir"])


def load_model(plan: dict[str, Any]) -> Dinov2BoundaryCueSegmenter:
    weight_path = Path(plan["inputs"]["pretrainedWeight"]["path"])
    torch.manual_seed(1605)
    backbone = AutoModel.from_pretrained(
        plan["backbone"]["huggingFaceModelId"],
        revision=plan["backbone"]["huggingFaceRevision"],
        cache_dir=str(weight_path.parents[2]),
        local_files_only=True,
    )
    return Dinov2BoundaryCueSegmenter(backbone)


def boundary_signal(gradient: np.ndarray, truth: np.ndarray) -> dict[str, float]:
    mask = truth.astype(np.uint8)
    kernel = np.ones((3, 3), dtype=np.uint8)
    eroded3 = cv2.erode(mask, kernel, iterations=3).astype(bool)
    eroded7 = cv2.erode(mask, kernel, iterations=7).astype(bool)
    dilated3 = cv2.dilate(mask, kernel, iterations=3).astype(bool)
    dilated7 = cv2.dilate(mask, kernel, iterations=7).astype(bool)
    truth_bool = mask.astype(bool)
    boundary = np.logical_or(np.logical_and(truth_bool, ~eroded3), np.logical_and(dilated3, ~truth_bool))
    context = np.logical_or(np.logical_and(eroded3, ~eroded7), np.logical_and(dilated7, ~dilated3))
    if not boundary.any() or not context.any():
        raise ValueError("边界或上下文带为空")
    boundary_mean = float(gradient[boundary].mean())
    context_mean = float(gradient[context].mean())
    return {
        "boundaryMeanScharrMagnitude": boundary_mean,
        "contextMeanScharrMagnitude": context_mean,
        "boundaryToContextRatio": boundary_mean / (context_mean + 1.0e-6),
    }


@torch.inference_mode()
def compute_signal(plan: dict[str, Any]) -> dict[str, Any]:
    bottleneck, dataset_report, dataset_root = validate_plan(plan)
    base = load_module("train-development-cycle-016-roi-segformer-pilot.py", "cycle016_boundary_cue_base")
    guards = load_module("train-yolo-seg.py", "cycle016_boundary_cue_guard")
    materializer = load_module("materialize-development-cycle-016-roi-dataset-v2.py", "cycle016_boundary_cue_materializer")
    guards.install_read_only_ultralytics_image_check()
    removed_before = guards.remove_ultralytics_label_caches(dataset_root)
    manifest = json.loads((dataset_root / "manifest.json").read_text(encoding="utf-8"))
    val_records = [row for row in manifest["records"] if row["split"] == "val"]
    required_count = int(plan["datasetContract"]["requiredValidationInstances"])
    if len(val_records) != required_count:
        raise ValueError(f"验证实例数不一致：{len(val_records)}!={required_count}")
    upstream_rows = bottleneck["analysis"]["perInstance"]
    upstream_ids = [row["id"] for row in upstream_rows]
    expected_ids = [str(row["id"]) for row in val_records]
    if upstream_ids != expected_ids:
        raise ValueError("瓶颈报告与ROI v2验证身份顺序不一致")
    stable_order = np.argsort(np.asarray([row["localBoundaryContrast"] for row in upstream_rows]), kind="stable")
    low_count = int(plan["datasetContract"]["requiredLowContrastQuartileInstances"])
    low_ids = {upstream_ids[int(index)] for index in stable_order[:low_count]}
    dataset = base.RoiDataset(dataset_root, val_records, training=False, seed=1605)
    loader = DataLoader(dataset, batch_size=8, shuffle=False, num_workers=0)
    cues = DeterministicBoundaryCues().eval()
    rows: list[dict[str, Any]] = []
    try:
        for images, truths, identities in loader:
            local_contrast, gradients = cues(images)
            if not torch.isfinite(local_contrast).all() or not torch.isfinite(gradients).all():
                raise ValueError("确定性提示含非有限值")
            gradient_arrays = gradients.numpy()[:, 0]
            truth_arrays = truths.numpy()[:, 0] >= 0.5
            for identity, gradient, truth in zip(identities, gradient_arrays, truth_arrays, strict=True):
                identity_string = str(identity)
                rows.append({"id": identity_string, "lowContrastQuartile": identity_string in low_ids, **boundary_signal(gradient, truth)})
    finally:
        removed_after = guards.remove_ultralytics_label_caches(dataset_root)
    reconstructed_ids = [row["id"] for row in rows]
    if reconstructed_ids != expected_ids:
        raise ValueError("信号审计身份顺序重建失败")
    low_rows = [row for row in rows if row["lowContrastQuartile"]]
    all_ratios = np.asarray([row["boundaryToContextRatio"] for row in rows], dtype=np.float64)
    low_ratios = np.asarray([row["boundaryToContextRatio"] for row in low_rows], dtype=np.float64)
    low_median = float(np.median(low_ratios))
    all_median = float(np.median(all_ratios))
    improved_fraction = float((low_ratios > 1.0).mean())
    low_to_all = low_median / (all_median + 1.0e-12)
    gate = plan["signalGate"]
    checks = {
        "lowContrastMedianBoundaryToContextRatio": low_median >= float(gate["minimumLowContrastMedianBoundaryToContextRatio"]),
        "lowContrastImprovedFraction": improved_fraction >= float(gate["minimumLowContrastImprovedFraction"]),
        "lowContrastToAllMedianRatio": low_to_all >= float(gate["minimumLowContrastToAllMedianRatio"]),
    }
    integrity = materializer.verify(Path(plan["inputs"]["datasetMaterializationReport"]["path"]))
    return {
        "recordCount": len(rows),
        "lowContrastQuartileCount": len(low_rows),
        "identityOrderMatches": True,
        "lowContrastQuartileIdsSha256": canonical_sha256([row["id"] for row in low_rows]),
        "allMedianBoundaryToContextRatio": all_median,
        "lowContrastMedianBoundaryToContextRatio": low_median,
        "lowContrastImprovedCount": int((low_ratios > 1.0).sum()),
        "lowContrastImprovedFraction": improved_fraction,
        "lowContrastToAllMedianRatio": low_to_all,
        "checks": checks,
        "passed": all(checks.values()),
        "datasetIntegrity": {
            "removedCachesBefore": removed_before,
            "removedCachesAfter": removed_after,
            "datasetFilesSha256After": integrity["datasetFilesSha256"],
            "verified": integrity["ok"],
        },
        "perInstance": rows,
    }


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
        "sampleOutput": {"minimum": float(output.min()), "maximum": float(output.max()), "mean": float(output.mean()), "finite": True},
    }


def measure_cuda_training_memory(model: nn.Module, maximum: int) -> dict[str, Any]:
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA不可用，无法验证第七轮显存门")
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
    gradients_finite = all(parameter.grad is None or torch.isfinite(parameter.grad).all().item() for parameter in model.parameters())
    if not bool(torch.isfinite(loss).item()) or not gradients_finite:
        raise ValueError("前反向或梯度含非有限值")
    if peak > maximum:
        raise ValueError(f"batch2显存峰值超过预注册上限：{peak}>{maximum}")
    return {
        "device": torch.cuda.get_device_name(0),
        "physicalBatchSize": 2,
        "inputShape": [2, 3, 384, 384],
        "forwardBackwardFinite": True,
        "gradientsFinite": True,
        "peakAllocatedBytes": peak,
        "maximumBytes": maximum,
        "withinCap": True,
        "gradientCheckpointing": True,
        "mixedPrecision": True,
    }


def export_and_report(plan_path: Path, model_path: Path, report_path: Path) -> dict[str, Any]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    validate_plan(plan)
    signal = compute_signal(plan)
    if not signal["passed"]:
        report = {
            "schemaVersion": 1,
            "ok": False,
            "decision": "low_contrast_boundary_cue_signal_gate_fail_no_training",
            "scope": plan["scope"],
            "inputs": {"plan": {"path": str(plan_path), "sha256": sha256_file(plan_path)}, **plan["inputs"]},
            "signalGate": plan["signalGate"],
            "signalAnalysis": signal,
            "signalAnalysisSha256": canonical_sha256(signal),
            "errors": [],
        }
        write_atomic(report_path, report)
        return report
    if model_path.exists():
        raise ValueError(f"ONNX输出已存在，禁止覆盖：{model_path}")
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model = load_model(plan).eval()
    architecture = plan["architecture"]
    parameter_count = sum(parameter.numel() for parameter in model.parameters())
    if parameter_count != int(architecture["expectedParameterCount"]) or parameter_count > int(architecture["maximumParameters"]):
        raise ValueError(f"参数量不符合预注册值：{parameter_count}")
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
        "decision": "low_contrast_boundary_cue_static_feasible_pending_browser_runtime",
        "scope": plan["scope"],
        "inputs": {"plan": {"path": str(plan_path), "sha256": sha256_file(plan_path)}, **plan["inputs"]},
        "reachability": plan["reachability"],
        "singleChangedVariable": plan["singleChangedVariable"],
        "cueDefinition": plan["cueDefinition"],
        "signalGate": plan["signalGate"],
        "signalAnalysis": signal,
        "signalAnalysisSha256": canonical_sha256(signal),
        "architecture": {**architecture, "parameterCount": parameter_count},
        "model": {"path": str(model_path), "sha256": sha256_file(model_path), "bytes": bytes_count, "withinCap": True},
        "runtime": runtime,
        "cudaTrainingMemory": cuda_memory,
        "browserRuntime": {"status": "pending", "requiredBackends": architecture["requiredBackends"]},
        "environment": {
            "python": os.sys.version.split()[0],
            "torch": torch.__version__,
            "transformers": __import__("transformers").__version__,
            "onnx": onnx.__version__,
            "onnxruntime": ort.__version__,
        },
        "errors": [],
    }
    write_atomic(report_path, report)
    return report


def verify(report_path: Path) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    for label, binding in report["inputs"].items():
        path = Path(binding["path"])
        if not path.is_file() or sha256_file(path) != binding["sha256"]:
            raise ValueError(f"输入哈希漂移：{label}")
    plan = json.loads(Path(report["inputs"]["plan"]["path"]).read_text(encoding="utf-8"))
    signal = compute_signal(plan)
    if signal != report["signalAnalysis"] or canonical_sha256(signal) != report["signalAnalysisSha256"]:
        raise ValueError("边界信号审计重放不一致")
    if report.get("decision") == "low_contrast_boundary_cue_signal_gate_fail_no_training":
        if report.get("ok") is not False or signal["passed"]:
            raise ValueError("信号失败结论不一致")
        return {"ok": True, "decision": "verified_low_contrast_boundary_cue_signal_gate_fail_no_training", "signalAnalysis": {k: v for k, v in signal.items() if k != "perInstance"}}
    if report.get("ok") is not True or report.get("decision") != "low_contrast_boundary_cue_static_feasible_pending_browser_runtime":
        raise ValueError("静态可行性结论不符合合同")
    if sha256_file(Path(report["model"]["path"])) != report["model"]["sha256"]:
        raise ValueError("ONNX模型哈希漂移")
    runtime = inspect_onnx(Path(report["model"]["path"]), report["architecture"]["outputShape"])
    if runtime != report["runtime"]:
        raise ValueError("ONNX运行时重放结果不一致")
    return {
        "ok": True,
        "decision": "verified_low_contrast_boundary_cue_static_feasible_pending_browser",
        "signalAnalysis": {k: v for k, v in signal.items() if k != "perInstance"},
        "model": report["model"],
        "cudaTrainingMemory": report["cudaTrainingMemory"],
    }


def verify_browser(report_path: Path) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("ok") is not True or report.get("decision") != "low_contrast_boundary_cue_browser_feasible_for_seventh_pilot":
        raise ValueError("浏览器报告结论不符合合同")
    for label, binding in report["inputs"].items():
        path = Path(binding["path"])
        if not path.is_file() or sha256_file(path) != binding["sha256"]:
            raise ValueError(f"浏览器证据哈希漂移：{label}")
    feasibility = json.loads(Path(report["inputs"]["feasibilityReport"]["path"]).read_text(encoding="utf-8"))
    if feasibility.get("decision") != "low_contrast_boundary_cue_static_feasible_pending_browser_runtime":
        raise ValueError("上游静态可行性报告未通过")
    if feasibility["model"]["sha256"] != report["model"]["sha256"]:
        raise ValueError("浏览器报告与上游ONNX身份不一致")
    runtime = report["browserRuntime"]
    if runtime.get("webgpuExposed") is not True or "HeadlessChrome/" not in runtime.get("userAgent", ""):
        raise ValueError("真实Chromium或WebGPU环境合同未满足")
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
    return {"ok": True, "decision": "verified_low_contrast_boundary_cue_browser_feasible_for_seventh_pilot", "model": report["model"], "backends": sorted(row["backend"] for row in results)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--verify-report", type=Path)
    parser.add_argument("--verify-browser-report", type=Path)
    args = parser.parse_args()
    if args.verify_browser_report:
        print(json.dumps(verify_browser(args.verify_browser_report.resolve()), ensure_ascii=False, indent=2))
    elif args.verify_report:
        print(json.dumps(verify(args.verify_report.resolve()), ensure_ascii=False, indent=2))
    else:
        if not args.plan or not args.model or not args.report:
            parser.error("构建需要--plan、--model与--report")
        result = export_and_report(args.plan.resolve(), args.model.resolve(), args.report.resolve())
        print(json.dumps({key: value for key, value in result.items() if key != "signalAnalysis"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
