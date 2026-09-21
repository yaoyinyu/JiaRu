#!/usr/bin/env python3
"""重建循环016第五/第六轮逐实例预测并审计ROI尺寸与边界对比度瓶颈。"""

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
import torch
from scipy.stats import spearmanr
from torch.utils.data import DataLoader


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


def validate_plan(plan: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], Path]:
    for label, binding in plan["inputs"].items():
        path = Path(binding["path"])
        if not path.is_file() or sha256_file(path) != binding["sha256"]:
            raise ValueError(f"输入哈希不一致：{label}")
    fifth = json.loads(Path(plan["inputs"]["fifthReport"]["path"]).read_text(encoding="utf-8"))
    sixth = json.loads(Path(plan["inputs"]["sixthReport"]["path"]).read_text(encoding="utf-8"))
    if fifth.get("decision") != "roi_dinov2_highres_decoder_internal_pilot_fail" or fifth.get("completedEpochs") != 30:
        raise ValueError("第五轮冻结失败报告不一致")
    if sixth.get("decision") != "roi_dinov2_signed_distance_boundary_internal_pilot_fail" or sixth.get("completedEpochs") != 30:
        raise ValueError("第六轮冻结失败报告不一致")
    dataset_report = json.loads(Path(plan["inputs"]["datasetMaterializationReport"]["path"]).read_text(encoding="utf-8"))
    if dataset_report.get("datasetFilesSha256") != plan["reconstructionGate"]["requireDatasetFilesSha256"]:
        raise ValueError("ROI v2数据集文件树哈希不一致")
    review = json.loads(Path(plan["inputs"]["finalReview"]["path"]).read_text(encoding="utf-8"))
    if review.get("decision") != "roi_validation_truth_v2_full_review_pass":
        raise ValueError("ROI v2原分辨率全量审核未通过")
    return fifth, sixth, dataset_report, Path(dataset_report["outputDir"])


def load_frozen_model(report: dict[str, Any], weights_path: Path, architecture: Any, trainer: Any, device: torch.device) -> torch.nn.Module:
    plan_binding = report["inputs"]["plan"]
    plan_path = Path(plan_binding["path"])
    if sha256_file(plan_path) != plan_binding["sha256"]:
        raise ValueError("训练计划哈希漂移")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    model = trainer.build_model(plan, architecture)
    checkpoint = torch.load(weights_path, map_location="cpu", weights_only=True)
    model.load_state_dict(checkpoint["model"], strict=True)
    return model.to(device).eval()


def mask_features(image: np.ndarray, truth: np.ndarray) -> dict[str, float]:
    truth_u8 = truth.astype(np.uint8)
    ys, xs = np.where(truth)
    if not len(xs):
        raise ValueError("ROI真值为空")
    bbox_width = int(xs.max() - xs.min() + 1)
    bbox_height = int(ys.max() - ys.min() + 1)
    kernel = np.ones((3, 3), dtype=np.uint8)
    inner = np.logical_and(truth, cv2.erode(truth_u8, kernel, iterations=3) == 0)
    outer = np.logical_and(cv2.dilate(truth_u8, kernel, iterations=3).astype(bool), ~truth)
    if not inner.any() or not outer.any():
        contrast = 0.0
    else:
        difference = image[inner].astype(np.float64).mean(axis=0) - image[outer].astype(np.float64).mean(axis=0)
        contrast = float(np.linalg.norm(difference) / (np.sqrt(3.0) * 255.0))
    return {
        "truthAreaFraction": float(truth.mean()),
        "truthBboxWidthPixels": float(bbox_width),
        "truthBboxHeightPixels": float(bbox_height),
        "truthBboxMinimumDimensionPixels": float(min(bbox_width, bbox_height)),
        "localBoundaryContrast": contrast,
    }


def prediction_metrics(truth: np.ndarray, prediction: np.ndarray, base: Any) -> dict[str, float]:
    union = np.logical_or(truth, prediction).sum()
    iou = float(np.logical_and(truth, prediction).sum() / union) if union else 1.0
    boundary_iou, boundary_f1 = base.boundary_metrics(truth, prediction, 2)
    truth_area = max(1, int(truth.sum()))
    over = int(np.logical_and(prediction, ~truth).sum())
    under = int(np.logical_and(truth, ~prediction).sum())
    return {
        "iou": iou,
        "boundaryIou": boundary_iou,
        "boundaryF1": boundary_f1,
        "areaRatio": float(prediction.sum() / truth_area),
        "oversegmentationFractionOfTruth": float(over / truth_area),
        "undersegmentationFractionOfTruth": float(under / truth_area),
    }


def aggregate_model(rows: list[dict[str, Any]], key: str) -> dict[str, float]:
    metrics = [row[key] for row in rows]
    joint = sum(value["iou"] >= 0.75 and value["boundaryIou"] >= 0.75 and value["boundaryF1"] >= 0.9 for value in metrics)
    return {
        "meanIou": round(float(np.mean([value["iou"] for value in metrics])), 8),
        "meanBoundaryIou": round(float(np.mean([value["boundaryIou"] for value in metrics])), 8),
        "meanBoundaryF1": round(float(np.mean([value["boundaryF1"] for value in metrics])), 8),
        "jointInstancePassRate": round(joint / len(metrics), 8),
        "jointScore": round(float(np.mean([(value["iou"] + value["boundaryF1"]) / 2 for value in metrics])), 8),
    }


def fidelity(actual: dict[str, float], expected: dict[str, float], tolerance: float) -> dict[str, Any]:
    keys = ("meanIou", "meanBoundaryIou", "meanBoundaryF1", "jointInstancePassRate", "jointScore")
    deltas = {key: abs(float(actual[key]) - float(expected[key])) for key in keys}
    return {"ok": all(value <= tolerance for value in deltas.values()), "deltas": deltas}


def relationship(rows: list[dict[str, Any]], feature: str) -> dict[str, Any]:
    values = np.asarray([row[feature] for row in rows], dtype=np.float64)
    outcomes = np.asarray([row["fifth"]["boundaryF1"] for row in rows], dtype=np.float64)
    correlation = spearmanr(values, outcomes)
    order = np.argsort(values, kind="stable")
    groups = np.array_split(order, 4)
    quartiles = [
        {
            "count": int(len(group)),
            "featureMinimum": float(values[group].min()),
            "featureMaximum": float(values[group].max()),
            "meanBoundaryF1": float(outcomes[group].mean()),
        }
        for group in groups
    ]
    return {
        "spearmanRho": float(correlation.statistic),
        "spearmanPValue": float(correlation.pvalue),
        "quartiles": quartiles,
        "topMinusBottomQuartileBoundaryF1": float(quartiles[-1]["meanBoundaryF1"] - quartiles[0]["meanBoundaryF1"]),
    }


@torch.inference_mode()
def compute(plan: dict[str, Any]) -> dict[str, Any]:
    fifth_report, sixth_report, dataset_report, dataset_root = validate_plan(plan)
    manifest = json.loads((dataset_root / "manifest.json").read_text(encoding="utf-8"))
    val_records = [row for row in manifest["records"] if row["split"] == "val"]
    if len(val_records) != int(plan["reconstructionGate"]["requiredRecordCount"]):
        raise ValueError("ROI v2验证实例数不一致")
    base = load_module("train-development-cycle-016-roi-segformer-pilot.py", "cycle016_resolution_base")
    architecture = load_module("audit-development-cycle-016-dinov2-highres-decoder-feasibility.py", "cycle016_resolution_architecture")
    trainer = load_module("train-development-cycle-016-dinov2-highres-decoder-pilot.py", "cycle016_resolution_trainer")
    guards = load_module("train-yolo-seg.py", "cycle016_resolution_guard")
    materializer = load_module("materialize-development-cycle-016-roi-dataset-v2.py", "cycle016_resolution_materializer")
    guards.install_read_only_ultralytics_image_check()
    removed_before = guards.remove_ultralytics_label_caches(dataset_root)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type != "cuda":
        raise RuntimeError("冻结权重重建预注册为CUDA推理")
    fifth_model = load_frozen_model(fifth_report, Path(plan["inputs"]["fifthWeights"]["path"]), architecture, trainer, device)
    sixth_model = load_frozen_model(sixth_report, Path(plan["inputs"]["sixthWeights"]["path"]), architecture, trainer, device)
    dataset = base.RoiDataset(dataset_root, val_records, training=False, seed=1605)
    loader = DataLoader(dataset, batch_size=2, shuffle=False, num_workers=0, pin_memory=True)
    rows: list[dict[str, Any]] = []
    mean = np.asarray([0.485, 0.456, 0.406], dtype=np.float32)[None, None, :]
    std = np.asarray([0.229, 0.224, 0.225], dtype=np.float32)[None, None, :]
    try:
        for images, truth, identities in loader:
            images_device = images.to(device, non_blocking=True)
            with torch.amp.autocast(device_type="cuda"):
                fifth_logits = fifth_model(pixel_values=images_device)
                sixth_logits = sixth_model(pixel_values=images_device)
            fifth_predictions = (torch.sigmoid(fifth_logits) >= 0.5).cpu().numpy()[:, 0]
            sixth_predictions = (torch.sigmoid(sixth_logits) >= 0.5).cpu().numpy()[:, 0]
            truths = truth.numpy()[:, 0] >= 0.5
            image_arrays = images.numpy().transpose(0, 2, 3, 1)
            image_arrays = np.clip((image_arrays * std + mean) * 255.0, 0, 255).astype(np.uint8)
            for identity, image, target, fifth_prediction, sixth_prediction in zip(identities, image_arrays, truths, fifth_predictions, sixth_predictions, strict=True):
                row = {"id": str(identity), **mask_features(image, target)}
                row["fifth"] = prediction_metrics(target, fifth_prediction, base)
                row["sixth"] = prediction_metrics(target, sixth_prediction, base)
                rows.append(row)
    finally:
        del fifth_model, sixth_model
        torch.cuda.empty_cache()
        removed_after = guards.remove_ultralytics_label_caches(dataset_root)
    expected_ids = [str(row["id"]) for row in val_records]
    reconstructed_ids = [row["id"] for row in rows]
    fifth_aggregate = aggregate_model(rows, "fifth")
    sixth_aggregate = aggregate_model(rows, "sixth")
    tolerance = float(plan["reconstructionGate"]["aggregateTolerance"])
    fifth_fidelity = fidelity(fifth_aggregate, fifth_report["best"]["validation"], tolerance)
    sixth_fidelity = fidelity(sixth_aggregate, sixth_report["best"]["validation"], tolerance)
    if reconstructed_ids != expected_ids or not fifth_fidelity["ok"] or not sixth_fidelity["ok"]:
        return {
            "decision": "reconstruction_mismatch",
            "idOrderMatches": reconstructed_ids == expected_ids,
            "fifthAggregate": fifth_aggregate,
            "sixthAggregate": sixth_aggregate,
            "fifthFidelity": fifth_fidelity,
            "sixthFidelity": sixth_fidelity,
        }
    size = relationship(rows, "truthBboxMinimumDimensionPixels")
    area = relationship(rows, "truthAreaFraction")
    contrast = relationship(rows, "localBoundaryContrast")
    threshold_rho = float(plan["analysisContract"]["minimumAbsoluteSpearmanRho"])
    threshold_gap = float(plan["analysisContract"]["minimumTopBottomQuartileBoundaryF1Gap"])
    size_hit = abs(size["spearmanRho"]) >= threshold_rho and size["topMinusBottomQuartileBoundaryF1"] >= threshold_gap
    contrast_hit = abs(contrast["spearmanRho"]) >= threshold_rho and contrast["topMinusBottomQuartileBoundaryF1"] >= threshold_gap
    if size_hit and contrast_hit:
        decision = "mixed_size_and_contrast_bottleneck"
    elif size_hit:
        decision = "roi_resolution_bottleneck"
    elif contrast_hit:
        decision = "boundary_contrast_bottleneck"
    else:
        decision = "neither_dominant_requires_error_topology_audit"
    integrity = materializer.verify(Path(plan["inputs"]["datasetMaterializationReport"]["path"]))
    paired_delta = np.asarray([row["sixth"]["boundaryF1"] - row["fifth"]["boundaryF1"] for row in rows])
    return {
        "decision": decision,
        "idOrderMatches": True,
        "fifthAggregate": fifth_aggregate,
        "sixthAggregate": sixth_aggregate,
        "fifthFidelity": fifth_fidelity,
        "sixthFidelity": sixth_fidelity,
        "relationships": {"bboxMinimumDimension": size, "areaFraction": area, "localBoundaryContrast": contrast},
        "decisionSignals": {"sizeMeetsBothThresholds": size_hit, "contrastMeetsBothThresholds": contrast_hit},
        "pairedSixthMinusFifthBoundaryF1": {
            "mean": float(paired_delta.mean()),
            "median": float(np.median(paired_delta)),
            "improvedCount": int((paired_delta > 0).sum()),
            "unchangedCount": int((paired_delta == 0).sum()),
            "worsenedCount": int((paired_delta < 0).sum()),
        },
        "datasetIntegrity": {
            "removedCachesBefore": removed_before,
            "removedCachesAfter": removed_after,
            "datasetFilesSha256After": integrity["datasetFilesSha256"],
            "verified": integrity["ok"],
        },
        "perInstance": rows,
    }


def run(plan_path: Path, report_path: Path) -> dict[str, Any]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    analysis = compute(plan)
    if analysis["decision"] == "reconstruction_mismatch":
        ok = False
    else:
        ok = True
    report = {
        "schemaVersion": 1,
        "ok": ok,
        "decision": analysis["decision"],
        "inputs": {"plan": {"path": str(plan_path), "sha256": sha256_file(plan_path)}, **plan["inputs"]},
        "analysisContract": plan["analysisContract"],
        "analysis": analysis,
        "analysisSha256": canonical_sha256(analysis),
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
    if canonical_sha256(replay) != report["analysisSha256"] or replay != report["analysis"]:
        raise ValueError("ROI瓶颈审计重放不一致")
    if not report.get("ok") or report.get("decision") == "reconstruction_mismatch":
        raise ValueError("ROI瓶颈审计保真门未通过")
    return {
        "ok": True,
        "decision": f"verified_{report['decision']}",
        "fifthAggregate": replay["fifthAggregate"],
        "sixthAggregate": replay["sixthAggregate"],
        "relationships": replay["relationships"],
        "decisionSignals": replay["decisionSignals"],
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
    print(json.dumps({"ok": result["ok"], "decision": result["decision"], "analysis": {key: value for key, value in result["analysis"].items() if key != "perInstance"}}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
