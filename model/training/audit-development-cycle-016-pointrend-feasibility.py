#!/usr/bin/env python3
"""审计循环016 PointRend式静态密集精细化头的训练与浏览器可达性。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import onnx
import onnxruntime as ort
import torch
import torch.nn.functional as F
from torch import nn
from torch.utils.data import DataLoader
from transformers import AutoModel


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


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


class Dinov2DensePointRendSegmenter(nn.Module):
    """训练可采样点、部署仅密集1x1卷积的静态PointRend式模型。"""

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
        self.coarse_output = nn.Conv2d(96, 1, 1)
        self.point_head = nn.Sequential(
            nn.Conv2d(65, 64, 1),
            nn.GELU(),
            nn.Conv2d(64, 64, 1),
            nn.GELU(),
            nn.Conv2d(64, 1, 1),
        )

    def forward_with_aux(self, pixel_values: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        spatial384 = self.spatial384(pixel_values)
        spatial192 = self.spatial192(spatial384)
        spatial96 = self.spatial96(spatial192)
        padded = F.pad(pixel_values, (4, 4, 4, 4), mode="replicate")
        tokens = self.backbone(pixel_values=padded, interpolate_pos_encoding=True, return_dict=False)[0][:, 1:, :]
        semantic = tokens.transpose(1, 2).reshape(pixel_values.shape[0], 384, 28, 28)
        semantic96 = F.interpolate(self.semantic96(semantic), size=(96, 96), mode="bilinear", align_corners=False)
        decoded96 = self.decode96(torch.cat((semantic96, spatial96), dim=1))
        coarse96 = self.coarse_output(decoded96)
        decoded192 = F.interpolate(decoded96, size=(192, 192), mode="bilinear", align_corners=False)
        decoded192 = self.decode192(torch.cat((decoded192, spatial192), dim=1))
        decoded384 = F.interpolate(decoded192, size=(384, 384), mode="bilinear", align_corners=False)
        fine384 = self.decode384(torch.cat((decoded384, spatial384), dim=1))
        coarse384 = F.interpolate(coarse96, size=(384, 384), mode="bilinear", align_corners=False)
        point_input = torch.cat((fine384, spatial384, coarse384), dim=1)
        final_logits = coarse384 + self.point_head(point_input)
        return final_logits, coarse384

    def forward(self, pixel_values: torch.Tensor) -> torch.Tensor:
        final_logits, _ = self.forward_with_aux(pixel_values)
        return final_logits


def soft_erode(value: torch.Tensor) -> torch.Tensor:
    return -F.max_pool2d(-value, kernel_size=3, stride=1, padding=1)


def truth_boundary_band(truth: torch.Tensor) -> torch.Tensor:
    inner = torch.clamp(truth.float() - soft_erode(truth.float()), min=0.0)
    return F.max_pool2d(inner, kernel_size=5, stride=1, padding=2)


def sample_point_indices(coarse_logits: torch.Tensor, truth: torch.Tensor, config: dict[str, Any]) -> torch.Tensor:
    coarse_flat = coarse_logits.float().flatten(1)
    truth_flat = truth_boundary_band(truth).flatten(1)
    uncertain_count = int(config["uncertainPointsPerInstance"])
    boundary_count = int(config["boundaryPointsPerInstance"])
    uncertain = torch.topk(-coarse_flat.abs(), k=uncertain_count, dim=1, largest=True, sorted=True).indices
    boundary = torch.topk(truth_flat, k=boundary_count, dim=1, largest=True, sorted=True).indices
    return torch.cat((uncertain, boundary), dim=1)


def gather_points(value: torch.Tensor, indices: torch.Tensor) -> torch.Tensor:
    return torch.gather(value.flatten(1), 1, indices)


def pointrend_loss(
    final_logits: torch.Tensor,
    coarse_logits: torch.Tensor,
    truth: torch.Tensor,
    plan: dict[str, Any],
    soft_loss_module: Any,
) -> tuple[torch.Tensor, dict[str, float], torch.Tensor]:
    base_loss, base_parts = soft_loss_module.soft_boundary_f1_loss(final_logits, truth, plan["loss"])
    indices = sample_point_indices(coarse_logits, truth, plan["pointSampling"])
    point_logits = gather_points(final_logits.float(), indices)
    point_truth = gather_points(truth.float(), indices)
    point_bce = F.binary_cross_entropy_with_logits(point_logits, point_truth)
    total = base_loss + float(plan["loss"]["pointWeight"]) * point_bce
    return total, {**base_parts, "pointBce": float(point_bce.detach())}, indices


def validate_plan(plan: dict[str, Any]) -> tuple[dict[str, Any], Path]:
    for label, binding in plan["inputs"].items():
        path = Path(binding["path"])
        if not path.is_file() or sha256_file(path) != binding["sha256"]:
            raise ValueError(f"输入哈希不一致：{label}")
    seventh = json.loads(Path(plan["inputs"]["seventhPilotReport"]["path"]).read_text(encoding="utf-8"))
    gain = json.loads(Path(plan["inputs"]["seventhGainAudit"]["path"]).read_text(encoding="utf-8"))
    baseline = json.loads(Path(plan["inputs"]["baselineStaticFeasibilityReport"]["path"]).read_text(encoding="utf-8"))
    if seventh.get("decision") != "roi_dinov2_soft_boundary_f1_internal_pilot_fail" or seventh.get("completedEpochs") != 30:
        raise ValueError("第七轮冻结失败报告不一致")
    if gain.get("decision") != "objective_effective_but_fine_boundary_architecture_limited" or not gain.get("ok"):
        raise ValueError("精细边界架构受限判决未冻结")
    if baseline.get("decision") != "dinov2_highres_decoder_static_feasible_pending_browser_runtime":
        raise ValueError("第五轮静态浏览器基线不一致")
    dataset_report = json.loads(Path(plan["inputs"]["datasetMaterializationReport"]["path"]).read_text(encoding="utf-8"))
    if dataset_report.get("datasetFilesSha256") != plan["datasetContract"]["requiredDatasetFilesSha256"]:
        raise ValueError("ROI v2文件树哈希不一致")
    review = json.loads(Path(plan["inputs"]["finalReview"]["path"]).read_text(encoding="utf-8"))
    if review.get("decision") != plan["datasetContract"]["requiredFinalReviewDecision"]:
        raise ValueError("ROI v2原分辨率全量审核未通过")
    return dataset_report, Path(dataset_report["outputDir"])


def load_model(plan: dict[str, Any]) -> Dinov2DensePointRendSegmenter:
    weight_path = Path(plan["inputs"]["pretrainedWeight"]["path"])
    torch.manual_seed(1605)
    backbone = AutoModel.from_pretrained(
        plan["backbone"]["huggingFaceModelId"],
        revision=plan["backbone"]["huggingFaceRevision"],
        cache_dir=str(weight_path.parents[2]),
        local_files_only=True,
    )
    return Dinov2DensePointRendSegmenter(backbone)


@torch.inference_mode()
def target_and_sampling_audit(plan: dict[str, Any]) -> dict[str, Any]:
    dataset_report, dataset_root = validate_plan(plan)
    base = load_module("train-development-cycle-016-roi-segformer-pilot.py", "cycle016_pointrend_target_base")
    soft_loss_module = load_module("audit-development-cycle-016-soft-boundary-f1-feasibility.py", "cycle016_pointrend_target_loss")
    guards = load_module("train-yolo-seg.py", "cycle016_pointrend_target_guard")
    materializer = load_module("materialize-development-cycle-016-roi-dataset-v2.py", "cycle016_pointrend_target_materializer")
    guards.install_read_only_ultralytics_image_check()
    removed_before = guards.remove_ultralytics_label_caches(dataset_root)
    manifest = json.loads((dataset_root / "manifest.json").read_text(encoding="utf-8"))
    records = manifest["records"]
    if len(records) != int(plan["datasetContract"]["requiredInstances"]):
        raise ValueError("ROI v2实例数不一致")
    dataset = base.RoiDataset(dataset_root, records, training=False, seed=1605)
    loader = DataLoader(dataset, batch_size=16, shuffle=False, num_workers=0)
    perfect_losses: list[float] = []
    boundary_fractions: list[float] = []
    selected_counts: list[int] = []
    identities: list[str] = []
    digest = hashlib.sha256()
    try:
        for _, truth, batch_identities in loader:
            coarse96 = F.avg_pool2d(truth, kernel_size=4, stride=4)
            coarse384 = F.interpolate((coarse96 * 2.0 - 1.0) * 4.0, size=(384, 384), mode="bilinear", align_corners=False)
            indices = sample_point_indices(coarse384, truth, plan["pointSampling"])
            band = truth_boundary_band(truth)
            fractions = gather_points(band, indices).mean(dim=1)
            perfect = 1.0 - soft_loss_module.soft_boundary_f1_per_instance(truth, truth, plan["loss"])
            perfect_losses.extend(float(value) for value in perfect)
            boundary_fractions.extend(float(value) for value in fractions)
            selected_counts.extend(int(indices.shape[1]) for _ in range(indices.shape[0]))
            identities.extend(str(value) for value in batch_identities)
            digest.update(np.ascontiguousarray(indices.numpy(), dtype=np.int64).tobytes())
    finally:
        removed_after = guards.remove_ultralytics_label_caches(dataset_root)
    integrity = materializer.verify(Path(plan["inputs"]["datasetMaterializationReport"]["path"]))
    gate = plan["reachabilityGate"]
    required_points = int(gate["requiredSampledPointCountPerInstance"])
    minimum_fraction = float(gate["minimumBoundaryBandPointFractionEveryInstance"])
    return {
        "instanceCount": len(identities),
        "identityOrderSha256": canonical_sha256(identities),
        "perfectMaskBoundaryLossMaximum": float(max(perfect_losses)),
        "perfectMaskBoundaryLossMean": float(np.mean(perfect_losses)),
        "perfectMaskCountWithinGate": int(sum(value <= float(gate["maximumPerfectMaskBoundaryLoss"]) for value in perfect_losses)),
        "selectedPointCountMinimum": int(min(selected_counts)),
        "selectedPointCountMaximum": int(max(selected_counts)),
        "boundaryBandPointFractionMinimum": float(min(boundary_fractions)),
        "boundaryBandPointFractionMedian": float(np.median(boundary_fractions)),
        "instancesMeetingBoundaryFraction": int(sum(value >= minimum_fraction for value in boundary_fractions)),
        "pointIndicesAggregateSha256": digest.hexdigest(),
        "checks": {
            "perfectMasks": len(perfect_losses) == int(gate["requiredPerfectMaskCount"]) and max(perfect_losses) <= float(gate["maximumPerfectMaskBoundaryLoss"]),
            "fixedPointCount": min(selected_counts) == required_points and max(selected_counts) == required_points,
            "boundaryCoverageEveryInstance": min(boundary_fractions) >= minimum_fraction,
            "datasetIntegrity": integrity["ok"] and integrity["datasetFilesSha256"] == plan["datasetContract"]["requiredDatasetFilesSha256"],
        },
        "datasetIntegrity": {"removedCachesBefore": removed_before, "removedCachesAfter": removed_after, "datasetFilesSha256After": integrity["datasetFilesSha256"], "verified": integrity["ok"]},
    }


def point_gradient_probe(truth: torch.Tensor, plan: dict[str, Any]) -> dict[str, Any]:
    truth = truth[:2].float()
    coarse96 = F.avg_pool2d(truth, kernel_size=4, stride=4)
    coarse = F.interpolate((coarse96 * 2.0 - 1.0) * 2.0, size=(384, 384), mode="bilinear", align_corners=False)
    final = (coarse + torch.linspace(-0.1, 0.1, coarse.numel()).reshape_as(coarse)).requires_grad_(True)
    indices = sample_point_indices(coarse, truth, plan["pointSampling"])
    loss = F.binary_cross_entropy_with_logits(gather_points(final, indices), gather_points(truth, indices))
    loss.backward()
    gradient = final.grad
    if gradient is None:
        raise ValueError("点损失探针梯度缺失")
    band = truth_boundary_band(truth) > 0
    absolute = gradient.abs()
    total = float(absolute.sum())
    boundary = float(absolute[band].sum())
    return {
        "loss": float(loss.detach()),
        "lossFinite": bool(torch.isfinite(loss).item()),
        "gradientFinite": bool(torch.isfinite(gradient).all().item()),
        "nonzeroGradientElements": int(torch.count_nonzero(gradient).item()),
        "boundaryBandGradientFraction": boundary / (total + 1.0e-12),
    }


def full_model_audit(model: Dinov2DensePointRendSegmenter, plan: dict[str, Any], images: torch.Tensor, truth: torch.Tensor) -> dict[str, Any]:
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA不可用，无法验证第八轮显存门")
    soft_loss_module = load_module("audit-development-cycle-016-soft-boundary-f1-feasibility.py", "cycle016_pointrend_full_loss")
    model.backbone.gradient_checkpointing_enable()
    device = torch.device("cuda")
    model = model.to(device).train()
    images = images[:2].to(device)
    truth = truth[:2].to(device)
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    scaler = torch.amp.GradScaler("cuda")
    with torch.amp.autocast(device_type="cuda"):
        final_logits, coarse_logits = model.forward_with_aux(images)
    loss, parts, indices = pointrend_loss(final_logits, coarse_logits, truth, plan, soft_loss_module)
    scaler.scale(loss).backward()
    torch.cuda.synchronize()
    named = [(name, parameter.grad) for name, parameter in model.named_parameters() if parameter.grad is not None]
    nonfinite = [name for name, value in named if not torch.isfinite(value).all().item()]
    point_names = [name for name, value in named if name.startswith("point_head.") and torch.count_nonzero(value).item() > 0]
    peak = int(torch.cuda.max_memory_allocated())
    return {
        "loss": float(loss.detach()),
        "lossParts": parts,
        "lossFinite": bool(torch.isfinite(loss).item()),
        "allGradientsFinite": not nonfinite and bool(named),
        "gradientTensorCount": len(named),
        "nonzeroGradientTensorCount": sum(int(torch.count_nonzero(value).item() > 0) for _, value in named),
        "pointHeadNonzeroGradientTensorCount": len(point_names),
        "pointHeadNonzeroGradientNames": point_names,
        "nonfiniteGradientNames": nonfinite,
        "sampledPointShape": list(indices.shape),
        "peakAllocatedBytes": peak,
        "maximumBytes": int(plan["architecture"]["maximumCudaPeakAllocatedBytesBatch2"]),
        "withinMemoryCap": peak <= int(plan["architecture"]["maximumCudaPeakAllocatedBytesBatch2"]),
        "device": torch.cuda.get_device_name(0),
        "physicalBatchSize": 2,
        "mixedPrecisionForward": True,
        "fp32Loss": True,
        "gradientCheckpointing": True,
    }


def inspect_onnx(model_path: Path, plan: dict[str, Any]) -> dict[str, Any]:
    model = onnx.load(str(model_path))
    onnx.checker.check_model(model, full_check=True)
    operator_counts = Counter(node.op_type for node in model.graph.node)
    operators = sorted(operator_counts)
    forbidden = sorted(set(operators).intersection(plan["architecture"]["forbiddenDeploymentOperators"]))
    if forbidden:
        raise ValueError(f"部署ONNX包含禁止动态点算子：{forbidden}")
    operator_ceiling_failures = {
        name: {"actual": int(operator_counts.get(name, 0)), "maximum": int(maximum)}
        for name, maximum in plan["architecture"].get("baselineOperatorCeilings", {}).items()
        if int(operator_counts.get(name, 0)) > int(maximum)
    }
    if operator_ceiling_failures:
        raise ValueError(f"部署ONNX相对静态基线新增受限算子：{operator_ceiling_failures}")
    session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    input_meta = session.get_inputs()[0]
    output_meta = session.get_outputs()[0]
    sample = np.linspace(-1.0, 1.0, 3 * 384 * 384, dtype=np.float32).reshape(1, 3, 384, 384)
    output = session.run([output_meta.name], {input_meta.name: sample})[0]
    if list(output.shape) != plan["architecture"]["outputShape"] or not np.isfinite(output).all():
        raise ValueError("ONNX静态输出合同失败")
    return {
        "input": {"name": input_meta.name, "shape": input_meta.shape, "type": input_meta.type},
        "output": {"name": output_meta.name, "shape": list(output.shape), "type": output_meta.type},
        "operators": operators,
        "operatorCounts": dict(sorted(operator_counts.items())),
        "baselineOperatorCeilings": plan["architecture"].get("baselineOperatorCeilings", {}),
        "operatorCeilingFailures": operator_ceiling_failures,
        "operatorCount": len(model.graph.node),
        "forbiddenDeploymentOperatorsPresent": forbidden,
        "runtimeProviders": session.get_providers(),
        "sampleOutput": {"minimum": float(output.min()), "maximum": float(output.max()), "mean": float(output.mean()), "finite": True},
    }


def export_and_report(plan_path: Path, model_path: Path, report_path: Path) -> dict[str, Any]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    dataset_report, dataset_root = validate_plan(plan)
    target_audit = target_and_sampling_audit(plan)
    if not all(target_audit["checks"].values()):
        report = {"schemaVersion": 1, "ok": False, "decision": "pointrend_sampling_or_expression_unreachable_no_training", "inputs": {"plan": {"path": str(plan_path), "sha256": sha256_file(plan_path)}, **plan["inputs"]}, "targetAndSamplingAudit": target_audit, "targetAndSamplingAuditSha256": canonical_sha256(target_audit), "errors": []}
        write_atomic(report_path, report)
        return report
    base = load_module("train-development-cycle-016-roi-segformer-pilot.py", "cycle016_pointrend_runtime_base")
    manifest = json.loads((dataset_root / "manifest.json").read_text(encoding="utf-8"))
    val_records = [row for row in manifest["records"] if row["split"] == "val"]
    dataset = base.RoiDataset(dataset_root, val_records, training=False, seed=1605)
    images, truth, _ = next(iter(DataLoader(dataset, batch_size=2, shuffle=False, num_workers=0)))
    probe = point_gradient_probe(truth, plan)
    model = load_model(plan).eval()
    parameter_count = sum(parameter.numel() for parameter in model.parameters())
    architecture = plan["architecture"]
    if parameter_count != int(architecture["expectedParameterCount"]) or parameter_count > int(architecture["maximumParameters"]):
        raise ValueError(f"参数量不符合预注册值：{parameter_count}")
    runtime_audit = full_model_audit(model, plan, images, truth)
    gates = {
        "pointProbeFinite": probe["lossFinite"] and probe["gradientFinite"] and probe["nonzeroGradientElements"] > 0,
        "pointProbeBoundaryConcentrated": probe["boundaryBandGradientFraction"] >= float(plan["reachabilityGate"]["minimumPointGradientBoundaryBandFraction"]),
        "fullModelFinite": runtime_audit["lossFinite"] and runtime_audit["allGradientsFinite"],
        "pointHeadGradient": runtime_audit["pointHeadNonzeroGradientTensorCount"] > 0,
        "memoryWithinCap": runtime_audit["withinMemoryCap"],
    }
    if not all(gates.values()):
        report = {"schemaVersion": 1, "ok": False, "decision": "pointrend_gradient_or_resource_unreachable_no_training", "inputs": {"plan": {"path": str(plan_path), "sha256": sha256_file(plan_path)}, **plan["inputs"]}, "targetAndSamplingAudit": target_audit, "targetAndSamplingAuditSha256": canonical_sha256(target_audit), "pointGradientProbe": probe, "fullModelAudit": runtime_audit, "gates": gates, "errors": []}
        write_atomic(report_path, report)
        return report
    if model_path.exists():
        raise ValueError(f"ONNX输出已存在，禁止覆盖：{model_path}")
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model = model.cpu().eval()
    sample = torch.zeros(tuple(architecture["inputShape"]), dtype=torch.float32)
    with torch.inference_mode():
        eager = model(sample)
        if list(eager.shape) != architecture["outputShape"] or not torch.isfinite(eager).all():
            raise ValueError("PyTorch静态输入输出合同失败")
        torch.onnx.export(model, (sample,), str(model_path), input_names=["pixel_values"], output_names=["logits"], opset_version=int(architecture["opset"]), do_constant_folding=True, dynamo=False)
    onnx_runtime = inspect_onnx(model_path, plan)
    bytes_count = model_path.stat().st_size
    if bytes_count > int(architecture["maximumFp32OnnxBytes"]):
        raise ValueError("FP32 ONNX超过预注册体积上限")
    report = {
        "schemaVersion": 1,
        "ok": True,
        "decision": "pointrend_dense_static_feasible_pending_browser_runtime",
        "scope": plan["scope"],
        "inputs": {"plan": {"path": str(plan_path), "sha256": sha256_file(plan_path)}, **plan["inputs"]},
        "singleChangedVariable": plan["singleChangedVariable"],
        "architecture": {**architecture, "parameterCount": parameter_count},
        "pointSampling": plan["pointSampling"],
        "loss": plan["loss"],
        "reachabilityGate": plan["reachabilityGate"],
        "targetAndSamplingAudit": target_audit,
        "targetAndSamplingAuditSha256": canonical_sha256(target_audit),
        "pointGradientProbe": probe,
        "fullModelAudit": runtime_audit,
        "gates": gates,
        "model": {"path": str(model_path), "sha256": sha256_file(model_path), "bytes": bytes_count, "withinCap": True},
        "runtime": onnx_runtime,
        "browserRuntime": {"status": "pending", "requiredBackends": architecture["requiredBackends"]},
        "environment": {"python": os.sys.version.split()[0], "torch": torch.__version__, "transformers": __import__("transformers").__version__, "onnx": onnx.__version__, "onnxruntime": ort.__version__},
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
    replay = target_and_sampling_audit(plan)
    if replay != report["targetAndSamplingAudit"] or canonical_sha256(replay) != report["targetAndSamplingAuditSha256"]:
        raise ValueError("目标与点采样审计重放不一致")
    if report.get("decision") != "pointrend_dense_static_feasible_pending_browser_runtime" or not report.get("ok"):
        raise ValueError("PointRend静态可行性门未通过")
    if sha256_file(Path(report["model"]["path"])) != report["model"]["sha256"]:
        raise ValueError("ONNX模型哈希漂移")
    runtime = inspect_onnx(Path(report["model"]["path"]), plan)
    if runtime != report["runtime"]:
        raise ValueError("ONNX运行时重放不一致")
    return {"ok": True, "decision": "verified_pointrend_dense_static_feasible_pending_browser", "model": report["model"], "targetAndSamplingAudit": replay, "fullModelAudit": report["fullModelAudit"]}


def verify_browser(report_path: Path) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("ok") is not True or report.get("decision") != "pointrend_dense_browser_feasible_for_eighth_pilot":
        raise ValueError("浏览器报告结论不符合合同")
    for label, binding in report["inputs"].items():
        path = Path(binding["path"])
        if not path.is_file() or sha256_file(path) != binding["sha256"]:
            raise ValueError(f"浏览器证据哈希漂移：{label}")
    feasibility = json.loads(Path(report["inputs"]["feasibilityReport"]["path"]).read_text(encoding="utf-8"))
    if feasibility.get("decision") != "pointrend_dense_static_feasible_pending_browser_runtime" or feasibility["model"]["sha256"] != report["model"]["sha256"]:
        raise ValueError("浏览器报告与上游静态模型身份不一致")
    runtime = report["browserRuntime"]
    if runtime.get("webgpuExposed") is not True or "HeadlessChrome/" not in runtime.get("userAgent", ""):
        raise ValueError("真实Chromium或WebGPU环境合同未满足")
    results = runtime.get("results", [])
    if {row.get("backend") for row in results} != {"wasm", "webgpu"}:
        raise ValueError("浏览器后端集合不完整")
    for row in results:
        if not (row.get("ok") is True and row.get("finite") is True and row.get("inputNames") == ["pixel_values"] and row.get("outputNames") == ["logits"] and row.get("outputDims") == [1, 1, 384, 384] and float(row.get("initMs", -1)) >= 0 and float(row.get("inferMs", -1)) >= 0):
            raise ValueError(f"浏览器后端结果失败：{row.get('backend')}")
    snapshot = Path(report["inputs"]["playwrightSnapshot"]["path"]).read_text(encoding="utf-8").replace('\\"', '"')
    evaluation = Path(report["inputs"]["playwrightEval"]["path"]).read_text(encoding="utf-8").replace('\\"', '"')
    for token in ('"webgpuExposed": true', '"backend": "wasm"', '"backend": "webgpu"', '"finite": true'):
        if token not in snapshot or token not in evaluation:
            raise ValueError(f"Playwright证据缺少字段：{token}")
    console_lines = [line for line in Path(report["inputs"]["consoleLog"]["path"]).read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(console_lines) != 1 or "favicon.ico" not in console_lines[0] or "404" not in console_lines[0]:
        raise ValueError("浏览器控制台出现未登记错误")
    return {"ok": True, "decision": "verified_pointrend_dense_browser_feasible_for_eighth_pilot", "model": report["model"], "backends": sorted(row["backend"] for row in results)}


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
        print(json.dumps({key: value for key, value in result.items() if key != "targetAndSamplingAudit"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
