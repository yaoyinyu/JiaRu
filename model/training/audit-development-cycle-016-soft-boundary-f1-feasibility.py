#!/usr/bin/env python3
"""审计循环016可微软Boundary F1监督的目标、梯度、显存与推理合同。"""

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
import torch
import torch.nn.functional as F
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


def soft_erode(value: torch.Tensor) -> torch.Tensor:
    return -F.max_pool2d(-value, kernel_size=3, stride=1, padding=1)


def soft_boundary_f1_per_instance(probability: torch.Tensor, truth: torch.Tensor, config: dict[str, Any]) -> torch.Tensor:
    probability = probability.float()
    truth = truth.float()
    probability_boundary = torch.clamp(probability - soft_erode(probability), min=0.0)
    truth_boundary = torch.clamp(truth - soft_erode(truth), min=0.0)
    kernel = int(config["nearBoundaryKernel"])
    padding = kernel // 2
    truth_near = F.max_pool2d(truth_boundary, kernel_size=kernel, stride=1, padding=padding)
    probability_near = F.max_pool2d(probability_boundary, kernel_size=kernel, stride=1, padding=padding)
    epsilon = float(config["epsilon"])
    dimensions = (1, 2, 3)
    precision = ((probability_boundary * truth_near).sum(dim=dimensions) + epsilon) / (probability_boundary.sum(dim=dimensions) + epsilon)
    recall = ((truth_boundary * probability_near).sum(dim=dimensions) + epsilon) / (truth_boundary.sum(dim=dimensions) + epsilon)
    return 2.0 * precision * recall / (precision + recall + epsilon)


def soft_boundary_f1_loss(logits: torch.Tensor, truth: torch.Tensor, config: dict[str, Any]) -> tuple[torch.Tensor, dict[str, float]]:
    logits_fp32 = logits.float()
    truth_fp32 = truth.float()
    bce = F.binary_cross_entropy_with_logits(logits_fp32, truth_fp32)
    probability = torch.sigmoid(logits_fp32)
    dimensions = (1, 2, 3)
    intersection = (probability * truth_fp32).sum(dim=dimensions)
    dice = 1.0 - ((2.0 * intersection + 1.0) / (probability.sum(dim=dimensions) + truth_fp32.sum(dim=dimensions) + 1.0)).mean()
    boundary = 1.0 - soft_boundary_f1_per_instance(probability, truth_fp32, config).mean()
    total = bce + dice + float(config["boundaryWeight"]) * boundary
    return total, {"bce": float(bce.detach()), "dice": float(dice.detach()), "softBoundaryF1Loss": float(boundary.detach())}


def validate_inputs(plan: dict[str, Any]) -> tuple[dict[str, Any], Path]:
    prerequisite = plan["prerequisites"]
    for label, path_key, hash_key in (
        ("低对比提示失败报告", "failedBoundaryCueReport", "failedBoundaryCueReportSha256"),
        ("第五轮报告", "fifthPilotReport", "fifthPilotReportSha256"),
        ("静态可行性报告", "staticFeasibilityReport", "staticFeasibilityReportSha256"),
        ("浏览器运行报告", "browserRuntimeReport", "browserRuntimeReportSha256"),
        ("DINOv2权重", "pretrainedWeight", "pretrainedWeightSha256"),
    ):
        path = Path(prerequisite[path_key])
        if not path.is_file() or sha256_file(path) != prerequisite[hash_key]:
            raise ValueError(f"{label}哈希不一致")
    failed = json.loads(Path(prerequisite["failedBoundaryCueReport"]).read_text(encoding="utf-8"))
    if failed.get("decision") != "low_contrast_boundary_cue_signal_gate_fail_no_training" or failed.get("ok") is not False:
        raise ValueError("低对比提示失败结论未冻结")
    fifth = json.loads(Path(prerequisite["fifthPilotReport"]).read_text(encoding="utf-8"))
    if fifth.get("decision") != "roi_dinov2_highres_decoder_internal_pilot_fail" or fifth.get("completedEpochs") != 30:
        raise ValueError("第五轮完整失败报告不一致")
    static = json.loads(Path(prerequisite["staticFeasibilityReport"]).read_text(encoding="utf-8"))
    browser = json.loads(Path(prerequisite["browserRuntimeReport"]).read_text(encoding="utf-8"))
    if static.get("decision") != "dinov2_highres_decoder_static_feasible_pending_browser_runtime" or browser.get("decision") != "dinov2_highres_decoder_browser_feasible_for_fifth_pilot":
        raise ValueError("复用的精确推理合同未通过")
    dataset = plan["dataset"]
    report_path = Path(dataset["materializationReport"])
    review_path = Path(dataset["finalReview"])
    if sha256_file(report_path) != dataset["materializationReportSha256"] or sha256_file(review_path) != dataset["finalReviewSha256"]:
        raise ValueError("ROI v2证据哈希不一致")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("datasetFilesSha256") != dataset["datasetFilesSha256"]:
        raise ValueError("ROI v2文件树哈希不一致")
    if json.loads(review_path.read_text(encoding="utf-8")).get("decision") != "roi_validation_truth_v2_full_review_pass":
        raise ValueError("ROI v2原分辨率审核未通过")
    return report, Path(report["outputDir"])


@torch.inference_mode()
def target_audit(dataset_root: Path, records: list[dict[str, Any]], plan: dict[str, Any], base: Any) -> dict[str, Any]:
    dataset = base.RoiDataset(dataset_root, records, training=False, seed=int(plan["trainingContract"]["seed"]))
    loader = DataLoader(dataset, batch_size=16, shuffle=False, num_workers=0)
    losses: list[float] = []
    identities: list[str] = []
    digest = hashlib.sha256()
    for _, truth, batch_identities in loader:
        values = 1.0 - soft_boundary_f1_per_instance(truth, truth, plan["loss"])
        losses.extend(float(value) for value in values)
        identities.extend(str(value) for value in batch_identities)
        digest.update(np.ascontiguousarray(values.numpy(), dtype=np.float32).tobytes())
    required = int(plan["dataset"]["requiredInstances"])
    if len(losses) != required:
        raise ValueError(f"目标审计实例数不一致：{len(losses)}!={required}")
    return {
        "instanceCount": len(losses),
        "identityOrderSha256": canonical_sha256(identities),
        "perfectMaskBoundaryLossMaximum": float(max(losses)),
        "perfectMaskBoundaryLossMean": float(np.mean(losses)),
        "perfectMaskCountWithinGate": int(sum(value <= float(plan["reachabilityGate"]["maximumPerfectMaskBoundaryLoss"]) for value in losses)),
        "lossAggregateSha256": digest.hexdigest(),
    }


def probe_gradient(truth: torch.Tensor, plan: dict[str, Any]) -> dict[str, Any]:
    truth = truth[:2].float()
    logits = ((truth * 2.0) - 1.0).mul(2.0).requires_grad_(True)
    boundary_loss = 1.0 - soft_boundary_f1_per_instance(torch.sigmoid(logits), truth, plan["loss"]).mean()
    boundary_loss.backward()
    gradient = logits.grad
    if gradient is None:
        raise ValueError("探针梯度缺失")
    truth_boundary = torch.clamp(truth - soft_erode(truth), min=0.0)
    near = F.max_pool2d(truth_boundary, kernel_size=5, stride=1, padding=2) > 0
    absolute = gradient.abs()
    total = float(absolute.sum())
    near_sum = float(absolute[near].sum())
    return {
        "loss": float(boundary_loss.detach()),
        "lossFinite": bool(torch.isfinite(boundary_loss).item()),
        "gradientFinite": bool(torch.isfinite(gradient).all().item()),
        "nonzeroGradientElements": int(torch.count_nonzero(gradient).item()),
        "boundaryBandGradientFraction": near_sum / (total + 1.0e-12),
    }


def load_model(plan: dict[str, Any], architecture: Any) -> torch.nn.Module:
    prerequisite = plan["prerequisites"]
    weight_path = Path(prerequisite["pretrainedWeight"])
    torch.manual_seed(int(plan["trainingContract"]["seed"]))
    backbone = AutoModel.from_pretrained(
        prerequisite["huggingFaceModelId"],
        revision=prerequisite["huggingFaceRevision"],
        cache_dir=str(weight_path.parents[2]),
        local_files_only=True,
    )
    backbone.gradient_checkpointing_enable()
    return architecture.Dinov2HighResBoundarySegmenter(backbone)


def full_model_audit(images: torch.Tensor, truth: torch.Tensor, plan: dict[str, Any], architecture: Any) -> dict[str, Any]:
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA不可用，无法审计第七轮训练可达性")
    device = torch.device("cuda")
    model = load_model(plan, architecture).to(device).train()
    images = images[:2].to(device)
    truth = truth[:2].to(device)
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    scaler = torch.amp.GradScaler("cuda")
    with torch.amp.autocast(device_type="cuda"):
        logits = model(pixel_values=images)
    loss, parts = soft_boundary_f1_loss(logits, truth, plan["loss"])
    scaler.scale(loss).backward()
    torch.cuda.synchronize()
    named_gradients = [(name, parameter.grad) for name, parameter in model.named_parameters() if parameter.grad is not None]
    nonfinite = [name for name, value in named_gradients if not torch.isfinite(value).all().item()]
    peak = int(torch.cuda.max_memory_allocated())
    result = {
        "loss": float(loss.detach()),
        "lossParts": parts,
        "lossFinite": bool(torch.isfinite(loss).item()),
        "allGradientsFinite": not nonfinite and bool(named_gradients),
        "gradientTensorCount": len(named_gradients),
        "nonzeroGradientTensorCount": sum(int(torch.count_nonzero(value).item() > 0) for _, value in named_gradients),
        "nonfiniteGradientNames": nonfinite,
        "peakAllocatedBytes": peak,
        "maximumBytes": int(plan["reachabilityGate"]["maximumCudaPeakAllocatedBytesBatch2"]),
        "withinMemoryCap": peak <= int(plan["reachabilityGate"]["maximumCudaPeakAllocatedBytesBatch2"]),
        "device": torch.cuda.get_device_name(0),
        "physicalBatchSize": 2,
        "mixedPrecisionForward": True,
        "fp32Loss": True,
        "gradientCheckpointing": True,
    }
    del model, images, truth, logits, loss
    torch.cuda.empty_cache()
    return result


def compute(plan: dict[str, Any]) -> dict[str, Any]:
    dataset_report, dataset_root = validate_inputs(plan)
    manifest = json.loads((dataset_root / "manifest.json").read_text(encoding="utf-8"))
    records = manifest["records"]
    base = load_module("train-development-cycle-016-roi-segformer-pilot.py", "cycle016_soft_boundary_base")
    architecture = load_module("audit-development-cycle-016-dinov2-highres-decoder-feasibility.py", "cycle016_soft_boundary_architecture")
    guards = load_module("train-yolo-seg.py", "cycle016_soft_boundary_guard")
    materializer = load_module("materialize-development-cycle-016-roi-dataset-v2.py", "cycle016_soft_boundary_materializer")
    guards.install_read_only_ultralytics_image_check()
    removed_before = guards.remove_ultralytics_label_caches(dataset_root)
    try:
        targets_first = target_audit(dataset_root, records, plan, base)
        targets_second = target_audit(dataset_root, records, plan, base)
        validation_records = [row for row in records if row["split"] == "val"]
        validation_dataset = base.RoiDataset(dataset_root, validation_records, training=False, seed=int(plan["trainingContract"]["seed"]))
        images, truth, _ = next(iter(DataLoader(validation_dataset, batch_size=2, shuffle=False, num_workers=0)))
        probe = probe_gradient(truth, plan)
        full_model = full_model_audit(images, truth, plan, architecture)
    finally:
        removed_after = guards.remove_ultralytics_label_caches(dataset_root)
    integrity = materializer.verify(Path(plan["dataset"]["materializationReport"]))
    gate = plan["reachabilityGate"]
    checks = {
        "targetDeterministic": targets_first == targets_second,
        "perfectMaskCount": targets_first["perfectMaskCountWithinGate"] == int(gate["requiredPerfectMaskCount"]),
        "perfectMaskMaximum": targets_first["perfectMaskBoundaryLossMaximum"] <= float(gate["maximumPerfectMaskBoundaryLoss"]),
        "probeFinite": probe["lossFinite"] and probe["gradientFinite"],
        "probeNonzero": probe["nonzeroGradientElements"] >= int(gate["minimumProbeNonzeroGradientElements"]),
        "probeBoundaryConcentrated": probe["boundaryBandGradientFraction"] >= float(gate["minimumProbeBoundaryBandGradientFraction"]),
        "fullModelFinite": full_model["lossFinite"] and full_model["allGradientsFinite"] and full_model["nonzeroGradientTensorCount"] > 0,
        "memoryWithinCap": full_model["withinMemoryCap"],
        "datasetIntegrity": integrity["ok"] and integrity["datasetFilesSha256"] == plan["dataset"]["datasetFilesSha256"],
    }
    return {
        "targetAudit": targets_first,
        "repeatTargetAuditSha256": canonical_sha256(targets_second),
        "probeGradient": probe,
        "fullModel": full_model,
        "checks": checks,
        "passed": all(checks.values()),
        "datasetIntegrity": {
            "removedCachesBefore": removed_before,
            "removedCachesAfter": removed_after,
            "datasetFilesSha256After": integrity["datasetFilesSha256"],
            "verified": integrity["ok"],
            "instances": dataset_report["counts"]["instances"],
        },
    }


def run(plan_path: Path, report_path: Path) -> dict[str, Any]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    analysis = compute(plan)
    report = {
        "schemaVersion": 1,
        "ok": analysis["passed"],
        "decision": "soft_boundary_f1_supervision_reachable_for_seventh_pilot" if analysis["passed"] else "soft_boundary_f1_supervision_unreachable_no_training",
        "scope": plan["scope"],
        "inputs": {
            "plan": {"path": str(plan_path), "sha256": sha256_file(plan_path)},
            **{key: {"path": plan["prerequisites"][key], "sha256": plan["prerequisites"][f"{key}Sha256"]} for key in ("failedBoundaryCueReport", "fifthPilotReport", "staticFeasibilityReport", "browserRuntimeReport", "pretrainedWeight")},
            "datasetMaterializationReport": {"path": plan["dataset"]["materializationReport"], "sha256": plan["dataset"]["materializationReportSha256"]},
            "finalReview": {"path": plan["dataset"]["finalReview"], "sha256": plan["dataset"]["finalReviewSha256"]},
        },
        "singleChangedVariable": plan["singleChangedVariable"],
        "loss": plan["loss"],
        "reachabilityGate": plan["reachabilityGate"],
        "analysis": analysis,
        "analysisSha256": canonical_sha256(analysis),
        "inferenceReuse": {
            "architectureChanged": False,
            "staticOnnxReport": plan["prerequisites"]["staticFeasibilityReport"],
            "browserRuntimeReport": plan["prerequisites"]["browserRuntimeReport"],
            "requiredBackends": ["wasm", "webgpu"],
        },
        "environment": {"python": os.sys.version.split()[0], "torch": torch.__version__, "transformers": __import__("transformers").__version__},
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
    replay = compute(plan)
    if replay != report["analysis"] or canonical_sha256(replay) != report["analysisSha256"]:
        raise ValueError("软边界F1可达性审计重放不一致")
    if not report.get("ok") or report.get("decision") != "soft_boundary_f1_supervision_reachable_for_seventh_pilot":
        raise ValueError("软边界F1监督未通过可达性门")
    return {"ok": True, "decision": "verified_soft_boundary_f1_supervision_reachable_for_seventh_pilot", "analysis": replay}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        print(json.dumps(verify(args.verify_report.resolve()), ensure_ascii=False, indent=2))
    else:
        if not args.plan or not args.report:
            parser.error("审计需要--plan与--report")
        result = run(args.plan.resolve(), args.report.resolve())
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
