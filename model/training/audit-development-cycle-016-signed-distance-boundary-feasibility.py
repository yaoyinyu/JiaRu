#!/usr/bin/env python3
"""审计循环016第六轮有符号距离场边界监督的零训练可达性。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from scipy.ndimage import distance_transform_edt
from transformers import AutoModel


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def signed_distance(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    binary = np.asarray(mask, dtype=bool)
    pixels = distance_transform_edt(~binary) - distance_transform_edt(binary)
    return pixels.astype(np.float32), binary


def distance_targets(mask: np.ndarray, config: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    pixels, binary = signed_distance(mask)
    maximum = float(config["maxDistancePixels"])
    target = np.clip(pixels, -maximum, maximum).astype(np.float32) / maximum
    return pixels, target


def signed_distance_loss(
    logits: torch.Tensor,
    truth: torch.Tensor,
    distance_pixels: torch.Tensor,
    distance_target: torch.Tensor,
    config: dict[str, Any],
) -> tuple[torch.Tensor, dict[str, torch.Tensor]]:
    if logits.shape[-2:] != truth.shape[-2:]:
        logits = F.interpolate(logits, size=truth.shape[-2:], mode="bilinear", align_corners=False)
    # 模型卷积/注意力仍由外层autocast控制，区域与距离损失显式用FP32计算。
    logits = logits.float()
    truth = truth.float()
    distance_pixels = distance_pixels.float()
    distance_target = distance_target.float()
    bce = F.binary_cross_entropy_with_logits(logits, truth)
    probability = torch.sigmoid(logits)
    intersection = (probability * truth).sum(dim=(1, 2, 3))
    dice = 1 - ((2 * intersection + 1) / (probability.sum(dim=(1, 2, 3)) + truth.sum(dim=(1, 2, 3)) + 1)).mean()
    prediction_proxy = -torch.tanh(logits / 4.0)
    weight = 1.0 + 4.0 * torch.exp(-distance_pixels.abs() / 2.0)
    elementwise = F.smooth_l1_loss(prediction_proxy, distance_target, reduction="none", beta=0.1)
    distance = (elementwise * weight).sum() / weight.sum().clamp_min(1.0)
    total = bce + dice + float(config["coefficient"]) * distance
    return total, {"bce": bce, "dice": dice, "signedDistance": distance}


def validate_inputs(plan: dict[str, Any]) -> tuple[dict[str, Any], Path, dict[str, Any], Path]:
    prerequisite = plan["prerequisites"]
    for label, path_key, hash_key in (
        ("第五轮训练报告", "fifthPilotReport", "fifthPilotReportSha256"),
        ("第五轮最佳权重", "fifthBestWeights", "fifthBestWeightsSha256"),
        ("静态可行性报告", "staticFeasibilityReport", "staticFeasibilityReportSha256"),
        ("DINOv2预训练权重", "pretrainedWeight", "pretrainedWeightSha256"),
    ):
        path = Path(prerequisite[path_key])
        if not path.is_file() or sha256_file(path) != prerequisite[hash_key]:
            raise ValueError(f"{label}哈希不一致")
    for suffix in ("V1", "V2"):
        path_key = f"rejectedFeasibilityReport{suffix}"
        hash_key = f"rejectedFeasibilityReport{suffix}Sha256"
        if path_key in prerequisite:
            path = Path(prerequisite[path_key])
            if not path.is_file() or sha256_file(path) != prerequisite[hash_key]:
                raise ValueError(f"已拒绝可行性报告{suffix}哈希不一致")
            rejected = json.loads(path.read_text(encoding="utf-8"))
            if rejected.get("decision") != "signed_distance_boundary_supervision_unreachable":
                raise ValueError(f"已拒绝可行性报告{suffix}结论不一致")
    fifth = json.loads(Path(prerequisite["fifthPilotReport"]).read_text(encoding="utf-8"))
    if (
        fifth.get("decision") != "roi_dinov2_highres_decoder_internal_pilot_fail"
        or fifth.get("completedEpochs") != 30
        or fifth.get("fullRunSatisfied") is not True
        or fifth.get("best", {}).get("epoch") != 27
    ):
        raise ValueError("第五轮完整30轮失败结论或epoch27冻结对照不一致")
    dataset = plan["dataset"]
    report_path = Path(dataset["materializationReport"])
    review_path = Path(dataset["finalReview"])
    if sha256_file(report_path) != dataset["materializationReportSha256"] or sha256_file(review_path) != dataset["finalReviewSha256"]:
        raise ValueError("ROI v2证据哈希不一致")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("datasetFilesSha256") != dataset["datasetFilesSha256"]:
        raise ValueError("ROI v2文件聚合哈希不一致")
    review = json.loads(review_path.read_text(encoding="utf-8"))
    if review.get("decision") != "roi_validation_truth_v2_full_review_pass":
        raise ValueError("ROI v2全量视觉审核未通过")
    return report, report_path, review, review_path


def target_audit(
    dataset_root: Path,
    records: list[dict[str, Any]],
    config: dict[str, Any],
    base: Any,
) -> dict[str, Any]:
    digest = hashlib.sha256()
    ious: list[float] = []
    boundary_ious: list[float] = []
    boundary_f1s: list[float] = []
    exact = 0
    for row in records:
        mask_path = dataset_root / row["mask"]
        if sha256_file(mask_path) != row["maskSha256"]:
            raise ValueError(f"mask哈希漂移：{row['id']}")
        with Image.open(mask_path) as source:
            mask = np.asarray(source.convert("L"), dtype=np.uint8) >= 128
        pixels, target = distance_targets(mask, config)
        reconstruction = pixels < 0
        if np.array_equal(reconstruction, mask):
            exact += 1
        union = np.logical_or(reconstruction, mask).sum()
        iou = float(np.logical_and(reconstruction, mask).sum() / union) if union else 1.0
        boundary_iou, boundary_f1 = base.boundary_metrics(mask, reconstruction, 2)
        ious.append(iou)
        boundary_ious.append(boundary_iou)
        boundary_f1s.append(boundary_f1)
        digest.update(str(row["id"]).encode("utf-8"))
        digest.update(b"\0")
        digest.update(np.ascontiguousarray(target, dtype=np.float32).tobytes())
    joint = sum(
        iou >= 0.75 and boundary_iou >= 0.75 and boundary_f1 >= 0.9
        for iou, boundary_iou, boundary_f1 in zip(ious, boundary_ious, boundary_f1s, strict=True)
    )
    return {
        "recordCount": len(records),
        "exactZeroLevelReconstructionCount": exact,
        "targetAggregateSha256": digest.hexdigest(),
        "theoreticalMeanIou": float(np.mean(ious)),
        "theoreticalMeanBoundaryIou": float(np.mean(boundary_ious)),
        "theoreticalMeanBoundaryF1At2Pixels": float(np.mean(boundary_f1s)),
        "theoreticalJointInstancePassRate": joint / len(records),
    }


def load_model(plan: dict[str, Any], architecture: Any) -> torch.nn.Module:
    prerequisite = plan["prerequisites"]
    weight_path = Path(prerequisite["pretrainedWeight"])
    seed = int(plan["trainingContract"]["seed"])
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    backbone = AutoModel.from_pretrained(
        prerequisite["huggingFaceModelId"],
        revision=prerequisite["huggingFaceRevision"],
        cache_dir=str(weight_path.parents[2]),
        local_files_only=True,
    )
    if plan["trainingContract"]["gradientCheckpointing"]:
        backbone.gradient_checkpointing_enable()
    return architecture.Dinov2HighResBoundarySegmenter(backbone)


def runtime_audit(
    plan: dict[str, Any],
    dataset_root: Path,
    train_records: list[dict[str, Any]],
    architecture: Any,
    base: Any,
) -> dict[str, Any]:
    if not torch.cuda.is_available():
        raise RuntimeError("可达性审计预注册为CUDA前反向验证，当前CUDA不可用")
    config = plan["signedDistanceSupervision"]
    contract = plan["trainingContract"]
    gate = plan["reachabilityGate"]
    masks: list[np.ndarray] = []
    pixels_list: list[np.ndarray] = []
    targets: list[np.ndarray] = []
    for row in train_records[: int(contract["physicalBatchSize"])]:
        with Image.open(dataset_root / row["mask"]) as source:
            mask = np.asarray(source.convert("L"), dtype=np.uint8) >= 128
        pixels, target = distance_targets(mask, config)
        masks.append(mask.astype(np.float32))
        pixels_list.append(pixels)
        targets.append(target)
    device = torch.device("cuda")
    truth = torch.from_numpy(np.stack(masks)[:, None]).to(device)
    distance_pixels = torch.from_numpy(np.stack(pixels_list)[:, None]).to(device)
    distance_target = torch.from_numpy(np.stack(targets)[:, None]).to(device)
    probe_logits = torch.zeros_like(truth, requires_grad=True)
    probe_loss, probe_parts = signed_distance_loss(probe_logits, truth, distance_pixels, distance_target, config)
    probe_loss.backward()
    probe_gradient = probe_logits.grad
    probe = {
        "loss": float(probe_loss.detach()),
        "components": {name: float(value.detach()) for name, value in probe_parts.items()},
        "lossFinite": bool(torch.isfinite(probe_loss).item()),
        "gradientFinite": bool(torch.isfinite(probe_gradient).all().item()),
        "gradientNonzeroElements": int(torch.count_nonzero(probe_gradient).item()),
        "gradientAbsoluteMean": float(probe_gradient.abs().mean()),
    }
    model = load_model(plan, architecture).to(device)
    model.train()
    parameter_count = sum(parameter.numel() for parameter in model.parameters())
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    image_dataset = base.RoiDataset(
        dataset_root,
        train_records[: int(contract["physicalBatchSize"])],
        training=False,
        seed=int(contract["seed"]),
    )
    images = torch.stack([image_dataset[index][0] for index in range(len(image_dataset))]).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=float(contract["decoderLearningRate"]))
    scaler = torch.amp.GradScaler("cuda")
    gradient_attempts: list[dict[str, Any]] = []
    logits: torch.Tensor | None = None
    loss: torch.Tensor | None = None
    parts: dict[str, torch.Tensor] | None = None
    gradients: list[torch.Tensor] = []
    gradients_finite = False
    for attempt in range(1, 17):
        optimizer.zero_grad(set_to_none=True)
        with torch.amp.autocast(device_type="cuda", enabled=bool(contract["mixedPrecision"])):
            logits = model(pixel_values=images)
            loss, parts = signed_distance_loss(logits, truth, distance_pixels, distance_target, config)
        scale_before = float(scaler.get_scale())
        scaler.scale(loss).backward()
        scaler.unscale_(optimizer)
        named_gradients = [(name, parameter.grad) for name, parameter in model.named_parameters() if parameter.grad is not None]
        gradients = [value for _, value in named_gradients]
        nonfinite_names = [name for name, value in named_gradients if not torch.isfinite(value).all().item()]
        gradients_finite = bool(gradients) and not nonfinite_names
        gradient_attempts.append(
            {
                "attempt": attempt,
                "scale": scale_before,
                "gradientTensorCount": len(gradients),
                "nonfiniteGradientTensorCount": len(nonfinite_names),
                "nonfiniteGradientNames": nonfinite_names,
            }
        )
        if gradients_finite:
            break
        # 与正式训练一致：本次含溢出梯度的step被GradScaler跳过，降低scale后重放。
        scaler.step(optimizer)
        scaler.update()
    if logits is None or loss is None or parts is None:
        raise RuntimeError("混合精度前反向未执行")
    result = {
        "device": torch.cuda.get_device_name(0),
        "parameterCount": parameter_count,
        "outputShape": list(logits.shape),
        "loss": float(loss.detach()),
        "components": {name: float(value.detach()) for name, value in parts.items()},
        "lossFinite": bool(torch.isfinite(loss).item()),
        "allGradientsFinite": gradients_finite,
        "gradientTensorCount": len(gradients),
        "nonzeroGradientTensorCount": sum(int(torch.count_nonzero(value).item() > 0) for value in gradients),
        "gradientScaleAttempts": gradient_attempts,
        "finalGradientScale": float(scaler.get_scale()),
        "peakAllocatedBytes": int(torch.cuda.max_memory_allocated()),
        "maximumBytes": int(gate["maximumCudaPeakAllocatedBytes"]),
    }
    del model, images, logits, loss, truth, distance_pixels, distance_target
    torch.cuda.empty_cache()
    return {"lossProbe": probe, "fullModel": result}


def run(plan_path: Path, report_path: Path) -> dict[str, Any]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    dataset_report, dataset_report_path, _, review_path = validate_inputs(plan)
    dataset_root = Path(dataset_report["outputDir"])
    manifest_path = dataset_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = manifest["records"]
    train_records = [row for row in records if row["split"] == "train"]
    base = load_module("train-development-cycle-016-roi-segformer-pilot.py", "cycle016_sdf_base")
    architecture = load_module("audit-development-cycle-016-dinov2-highres-decoder-feasibility.py", "cycle016_sdf_architecture")
    guards = load_module("train-yolo-seg.py", "cycle016_sdf_guard")
    materializer = load_module("materialize-development-cycle-016-roi-dataset-v2.py", "cycle016_sdf_materializer")
    guards.install_read_only_ultralytics_image_check()
    removed_before = guards.remove_ultralytics_label_caches(dataset_root)
    try:
        first = target_audit(dataset_root, records, plan["signedDistanceSupervision"], base)
        second = target_audit(dataset_root, records, plan["signedDistanceSupervision"], base)
        runtime = runtime_audit(plan, dataset_root, train_records, architecture, base)
    finally:
        removed_after = guards.remove_ultralytics_label_caches(dataset_root)
    integrity = materializer.verify(dataset_report_path)
    gate = plan["reachabilityGate"]
    full_model = runtime["fullModel"]
    loss_probe = runtime["lossProbe"]
    deterministic = first["targetAggregateSha256"] == second["targetAggregateSha256"]
    exact = first["exactZeroLevelReconstructionCount"] == first["recordCount"]
    reachable_margin = first["theoreticalJointInstancePassRate"] / float(plan["pilotGate"]["minimumJointInstancePassRate"])
    passed = all(
        (
            exact,
            deterministic,
            first["theoreticalMeanIou"] >= float(gate["minimumTheoreticalMeanIou"]),
            first["theoreticalMeanBoundaryF1At2Pixels"] >= float(gate["minimumTheoreticalBoundaryF1At2Pixels"]),
            first["theoreticalJointInstancePassRate"] >= float(gate["minimumTheoreticalJointInstancePassRate"]),
            reachable_margin >= float(gate["minimumReachableMarginRatio"]),
            loss_probe["lossFinite"],
            loss_probe["gradientFinite"],
            loss_probe["gradientNonzeroElements"] > 0,
            full_model["lossFinite"],
            full_model["allGradientsFinite"],
            full_model["nonzeroGradientTensorCount"] > 0,
            full_model["peakAllocatedBytes"] <= int(gate["maximumCudaPeakAllocatedBytes"]),
            full_model["parameterCount"] == int(gate["expectedParameterCount"]),
            full_model["outputShape"] == gate["expectedOutputShape"],
            integrity["datasetFilesSha256"] == plan["dataset"]["datasetFilesSha256"],
        )
    )
    result = {
        "schemaVersion": 1,
        "ok": passed,
        "decision": "signed_distance_boundary_supervision_reachable_for_sixth_pilot" if passed else "signed_distance_boundary_supervision_unreachable",
        "scope": plan["scope"],
        "inputs": {
            "plan": {"path": str(plan_path), "sha256": sha256_file(plan_path)},
            "fifthPilotReport": {"path": plan["prerequisites"]["fifthPilotReport"], "sha256": plan["prerequisites"]["fifthPilotReportSha256"]},
            "fifthBestWeights": {"path": plan["prerequisites"]["fifthBestWeights"], "sha256": plan["prerequisites"]["fifthBestWeightsSha256"]},
            "staticFeasibilityReport": {"path": plan["prerequisites"]["staticFeasibilityReport"], "sha256": plan["prerequisites"]["staticFeasibilityReportSha256"]},
            "pretrainedWeight": {"path": plan["prerequisites"]["pretrainedWeight"], "sha256": plan["prerequisites"]["pretrainedWeightSha256"]},
            "datasetMaterializationReport": {"path": str(dataset_report_path), "sha256": sha256_file(dataset_report_path)},
            "finalReview": {"path": str(review_path), "sha256": sha256_file(review_path)},
            "manifest": {"path": str(manifest_path), "sha256": sha256_file(manifest_path)},
            **(
                {
                    "rejectedFeasibilityReportV1": {"path": plan["prerequisites"]["rejectedFeasibilityReportV1"], "sha256": plan["prerequisites"]["rejectedFeasibilityReportV1Sha256"]},
                    "rejectedFeasibilityReportV2": {"path": plan["prerequisites"]["rejectedFeasibilityReportV2"], "sha256": plan["prerequisites"]["rejectedFeasibilityReportV2Sha256"]},
                }
                if "rejectedFeasibilityReportV1" in plan["prerequisites"]
                else {}
            ),
        },
        "singleChangedVariable": plan["singleChangedVariable"],
        "signedDistanceSupervision": plan["signedDistanceSupervision"],
        "auditMethod": {
            "mixedPrecisionBackward": "真实ROI输入；模型前向使用torch.amp.autocast，损失显式FP32，反向使用GradScaler；发生溢出时跳过step并降低scale，最多重放16次",
            "rejectedReports": [
                "v1直接FP16 loss.backward未使用正式训练GradScaler而拒绝",
                "v2加入GradScaler但损失仍在autocast上下文且使用零图输入，8次scale回退后早期空间分支仍有非有限梯度",
            ],
            "preservation": "v1/v2报告原样保留并由v2计划哈希绑定，不作为路线质量结论",
        },
        "initialization": {
            "seed": plan["trainingContract"]["seed"],
            "pretrainedWeightSha256": plan["prerequisites"]["pretrainedWeightSha256"],
            "fifthBestWeightsBoundAsComparator": True,
            "fifthBestWeightsLoaded": False,
        },
        "targetAudit": first,
        "repeatTargetAggregateSha256": second["targetAggregateSha256"],
        "deterministicTargetDigest": deterministic,
        "reachableMarginRatio": reachable_margin,
        "runtimeAudit": runtime,
        "inferenceContract": {
            "architectureChanged": False,
            "parameterCountChanged": False,
            "outputShapeChanged": False,
            "thresholdChanged": False,
            "trainingOnlyLossChange": True,
            "boundStaticOnnxSha256": json.loads(Path(plan["prerequisites"]["staticFeasibilityReport"]).read_text(encoding="utf-8"))["model"]["sha256"],
        },
        "datasetIntegrity": {
            "removedCachesBefore": removed_before,
            "removedCachesAfter": removed_after,
            "datasetFilesSha256After": integrity["datasetFilesSha256"],
            "verified": integrity["ok"],
        },
        "pilotGate": plan["pilotGate"],
        "errors": [],
    }
    write_atomic(report_path, result)
    return result


def verify(report_path: Path) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    for label, binding in report["inputs"].items():
        path = Path(binding["path"])
        if not path.is_file() or sha256_file(path) != binding["sha256"]:
            raise ValueError(f"输入哈希漂移：{label}")
    plan = json.loads(Path(report["inputs"]["plan"]["path"]).read_text(encoding="utf-8"))
    dataset_report, dataset_report_path, _, _ = validate_inputs(plan)
    dataset_root = Path(dataset_report["outputDir"])
    manifest = json.loads((dataset_root / "manifest.json").read_text(encoding="utf-8"))
    base = load_module("train-development-cycle-016-roi-segformer-pilot.py", "cycle016_sdf_verify_base")
    guards = load_module("train-yolo-seg.py", "cycle016_sdf_verify_guard")
    materializer = load_module("materialize-development-cycle-016-roi-dataset-v2.py", "cycle016_sdf_verify_materializer")
    guards.install_read_only_ultralytics_image_check()
    guards.remove_ultralytics_label_caches(dataset_root)
    try:
        replay = target_audit(dataset_root, manifest["records"], plan["signedDistanceSupervision"], base)
    finally:
        guards.remove_ultralytics_label_caches(dataset_root)
    integrity = materializer.verify(dataset_report_path)
    if replay != report["targetAudit"]:
        raise ValueError("距离场目标审计重放不一致")
    if integrity["datasetFilesSha256"] != report["datasetIntegrity"]["datasetFilesSha256After"]:
        raise ValueError("ROI v2数据集完整性重放不一致")
    if not report.get("ok") or report.get("decision") != "signed_distance_boundary_supervision_reachable_for_sixth_pilot":
        raise ValueError("可达性报告未通过")
    return {
        "ok": True,
        "decision": "verified_signed_distance_boundary_supervision_reachable_for_sixth_pilot",
        "targetAudit": replay,
        "runtimeAudit": report["runtimeAudit"],
        "datasetFilesSha256": integrity["datasetFilesSha256"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan")
    parser.add_argument("--report")
    parser.add_argument("--verify-report")
    args = parser.parse_args()
    if args.verify_report:
        print(json.dumps(verify(Path(args.verify_report).resolve()), ensure_ascii=False, indent=2))
        return 0
    if not args.plan or not args.report:
        raise ValueError("审计模式需要--plan与--report")
    result = run(Path(args.plan).resolve(), Path(args.report).resolve())
    print(json.dumps({"ok": result["ok"], "decision": result["decision"], "targetAudit": result["targetAudit"], "runtimeAudit": result["runtimeAudit"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
