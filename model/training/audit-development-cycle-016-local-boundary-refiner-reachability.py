#!/usr/bin/env python3
"""审计冻结第七轮粗分割的固定局部边界修正带理论上限。"""

from __future__ import annotations

import argparse
import atexit
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


def validate_plan(plan: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], Path]:
    for label, binding in plan["inputs"].items():
        path = Path(binding["path"])
        if not path.is_file() or sha256_file(path) != binding["sha256"]:
            raise ValueError(f"输入哈希不一致：{label}")
    seventh = json.loads(Path(plan["inputs"]["seventhReport"]["path"]).read_text(encoding="utf-8"))
    eighth = json.loads(Path(plan["inputs"]["eighthReport"]["path"]).read_text(encoding="utf-8"))
    gain = json.loads(Path(plan["inputs"]["pointRendGainAudit"]["path"]).read_text(encoding="utf-8"))
    if seventh.get("decision") != "roi_dinov2_soft_boundary_f1_internal_pilot_fail" or seventh.get("completedEpochs") != 30:
        raise ValueError("第七轮冻结报告不一致")
    if eighth.get("decision") != "roi_dinov2_pointrend_internal_pilot_fail" or eighth.get("completedEpochs") != 30:
        raise ValueError("第八轮冻结报告不一致")
    if gain.get("decision") != "pointrend_not_broadly_effective_close_branch" or not gain.get("ok"):
        raise ValueError("PointRend关闭判决不一致")
    dataset_report = json.loads(Path(plan["inputs"]["datasetMaterializationReport"]["path"]).read_text(encoding="utf-8"))
    if dataset_report.get("datasetFilesSha256") != plan["reconstructionGate"]["requiredDatasetFilesSha256"]:
        raise ValueError("ROI v2文件树哈希不一致")
    review = json.loads(Path(plan["inputs"]["finalReview"]["path"]).read_text(encoding="utf-8"))
    if review.get("decision") != "roi_validation_truth_v2_full_review_pass":
        raise ValueError("ROI v2原分辨率全量审核未通过")
    return seventh, dataset_report, Path(dataset_report["outputDir"])


def metrics(truth: np.ndarray, prediction: np.ndarray, base: Any) -> dict[str, float]:
    union = np.logical_or(truth, prediction).sum()
    iou = float(np.logical_and(truth, prediction).sum() / union) if union else 1.0
    boundary_iou, boundary_f1 = base.boundary_metrics(truth, prediction, 2)
    return {"iou": iou, "boundaryIou": boundary_iou, "boundaryF1": boundary_f1}


def aggregate(rows: list[dict[str, Any]], key: str, thresholds: dict[str, float]) -> dict[str, Any]:
    values = [row[key] for row in rows]
    joint = [
        value["iou"] >= float(thresholds["iou"])
        and value["boundaryIou"] >= float(thresholds["boundaryIou"])
        and value["boundaryF1"] >= float(thresholds["boundaryF1"])
        for value in values
    ]
    return {
        "meanIou": round(float(np.mean([value["iou"] for value in values])), 8),
        "meanBoundaryIou": round(float(np.mean([value["boundaryIou"] for value in values])), 8),
        "meanBoundaryF1": round(float(np.mean([value["boundaryF1"] for value in values])), 8),
        "jointInstancePassRate": round(float(np.mean(joint)), 8),
        "jointScore": round(float(np.mean([(value["iou"] + value["boundaryF1"]) / 2 for value in values])), 8),
        "jointPassCount": int(sum(joint)),
        "denominator": len(values),
    }


def fidelity(actual: dict[str, Any], expected: dict[str, float], tolerance: float) -> dict[str, Any]:
    keys = ("meanIou", "meanBoundaryIou", "meanBoundaryF1", "jointInstancePassRate", "jointScore")
    deltas = {key: abs(float(actual[key]) - float(expected[key])) for key in keys}
    return {"ok": all(value <= tolerance for value in deltas.values()), "deltas": deltas}


def editable_band(prediction: torch.Tensor, radius: int) -> torch.Tensor:
    value = prediction.float()
    dilated = F.max_pool2d(value, kernel_size=3, stride=1, padding=1)
    eroded = -F.max_pool2d(-value, kernel_size=3, stride=1, padding=1)
    edge = (dilated - eroded) > 0
    return F.max_pool2d(edge.float(), kernel_size=radius * 2 + 1, stride=1, padding=radius) > 0


@torch.inference_mode()
def compute(plan: dict[str, Any]) -> dict[str, Any]:
    seventh_report, dataset_report, dataset_root = validate_plan(plan)
    manifest = json.loads((dataset_root / "manifest.json").read_text(encoding="utf-8"))
    records = [row for row in manifest["records"] if row["split"] == "val"]
    if len(records) != int(plan["reconstructionGate"]["requiredRecordCount"]):
        raise ValueError("ROI v2验证实例数不一致")
    prior = json.loads(Path(plan["inputs"]["priorBottleneckReport"]["path"]).read_text(encoding="utf-8"))
    prior_rows = prior["analysis"]["perInstance"]
    expected_ids = [str(row["id"]) for row in records]
    if [row["id"] for row in prior_rows] != expected_ids:
        raise ValueError("先前瓶颈报告身份顺序不一致")
    contrast_order = np.argsort(np.asarray([float(row["localBoundaryContrast"]) for row in prior_rows]), kind="stable")
    low_ids = {expected_ids[int(index)] for index in contrast_order[:70]}
    base = load_module("train-development-cycle-016-roi-segformer-pilot.py", "cycle016_local_refiner_base")
    architecture = load_module("audit-development-cycle-016-dinov2-highres-decoder-feasibility.py", "cycle016_local_refiner_architecture")
    trainer = load_module("train-development-cycle-016-soft-boundary-f1-pilot.py", "cycle016_local_refiner_trainer")
    guards = load_module("train-yolo-seg.py", "cycle016_local_refiner_guard")
    materializer = load_module("materialize-development-cycle-016-roi-dataset-v2.py", "cycle016_local_refiner_materializer")
    guards.install_read_only_ultralytics_image_check()
    removed_before = guards.remove_ultralytics_label_caches(dataset_root)
    cleanup = lambda: guards.remove_ultralytics_label_caches(dataset_root)
    atexit.register(cleanup)
    training_plan_path = Path(seventh_report["inputs"]["plan"]["path"])
    if sha256_file(training_plan_path) != seventh_report["inputs"]["plan"]["sha256"]:
        raise ValueError("第七轮训练计划哈希漂移")
    training_plan = json.loads(training_plan_path.read_text(encoding="utf-8"))
    model = trainer.build_model(training_plan, architecture)
    checkpoint = torch.load(Path(plan["inputs"]["seventhWeights"]["path"]), map_location="cpu", weights_only=True)
    model.load_state_dict(checkpoint["model"], strict=True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type != "cuda":
        raise RuntimeError("可达性重建预注册为CUDA推理")
    model = model.to(device).eval()
    dataset = base.RoiDataset(dataset_root, records, training=False, seed=1605)
    loader = DataLoader(dataset, batch_size=2, shuffle=False, num_workers=0, pin_memory=True)
    threshold = float(plan["reconstructionGate"]["scoreThreshold"])
    radius = int(plan["refinerHypothesis"]["maximumEditableBandRadiusPixels"])
    rows: list[dict[str, Any]] = []
    covered_errors = 0
    total_errors = 0
    try:
        for images, truth, identities in loader:
            images = images.to(device, non_blocking=True)
            with torch.amp.autocast(device_type="cuda"):
                logits = model(pixel_values=images)
            prediction = torch.sigmoid(logits).ge(threshold).cpu()
            truth_bool = truth.ge(0.5)
            band = editable_band(prediction, radius)
            oracle = torch.where(band, truth_bool, prediction)
            disagreement = prediction.ne(truth_bool)
            covered = disagreement.logical_and(band)
            covered_errors += int(covered.sum())
            total_errors += int(disagreement.sum())
            predictions = prediction.numpy()[:, 0]
            oracles = oracle.numpy()[:, 0]
            truths = truth_bool.numpy()[:, 0]
            bands = band.numpy()[:, 0]
            disagreements = disagreement.numpy()[:, 0]
            for identity, target, coarse, refined, local_band, local_error in zip(identities, truths, predictions, oracles, bands, disagreements, strict=True):
                error_count = int(local_error.sum())
                local_covered = int(np.logical_and(local_error, local_band).sum())
                rows.append({
                    "id": str(identity),
                    "lowContrastQuartile": str(identity) in low_ids,
                    "coarse": metrics(target, coarse, base),
                    "oracle": metrics(target, refined, base),
                    "disagreementPixels": error_count,
                    "coveredDisagreementPixels": local_covered,
                    "coverage": 1.0 if error_count == 0 else local_covered / error_count,
                    "editablePixelFraction": float(local_band.mean()),
                })
    finally:
        del model
        torch.cuda.empty_cache()
        removed_after = guards.remove_ultralytics_label_caches(dataset_root)
    thresholds = plan["reachabilityGate"]["instancePassThresholds"]
    coarse = aggregate(rows, "coarse", thresholds)
    oracle = aggregate(rows, "oracle", thresholds)
    fidelity_result = fidelity(coarse, seventh_report["best"]["validation"], float(plan["reconstructionGate"]["aggregateTolerance"]))
    identity_match = [row["id"] for row in rows] == expected_ids
    if not identity_match or not fidelity_result["ok"]:
        return {"decision": "reconstruction_mismatch", "identityOrderMatches": identity_match, "coarseAggregate": coarse, "coarseFidelity": fidelity_result}
    coverage = covered_errors / total_errors if total_errors else 1.0
    gate = plan["reachabilityGate"]
    checks = {
        "meanIou": oracle["meanIou"] >= float(gate["minimumMeanIou"]),
        "meanBoundaryF1": oracle["meanBoundaryF1"] >= float(gate["minimumMeanBoundaryF1At2Pixels"]),
        "jointInstancePassRate": oracle["jointInstancePassRate"] >= float(gate["minimumJointInstancePassRate"]),
        "disagreementCoverage": coverage >= float(gate["minimumDisagreementPixelsCovered"]),
    }
    decision = "local_boundary_refiner_band_reachable" if all(checks.values()) else "local_boundary_refiner_band_unreachable_no_training"
    low_rows = [row for row in rows if row["lowContrastQuartile"]]
    integrity = materializer.verify(Path(plan["inputs"]["datasetMaterializationReport"]["path"]))
    atexit.unregister(cleanup)
    return {
        "decision": decision,
        "identityOrderMatches": True,
        "coarseAggregate": coarse,
        "oracleAggregate": oracle,
        "lowContrastOracleAggregate": aggregate(low_rows, "oracle", thresholds),
        "coarseFidelity": fidelity_result,
        "band": {
            "radiusPixels": radius,
            "totalDisagreementPixels": total_errors,
            "coveredDisagreementPixels": covered_errors,
            "disagreementCoverage": coverage,
            "editablePixelFractionMean": float(np.mean([row["editablePixelFraction"] for row in rows])),
            "perInstanceCoverageMinimum": float(min(row["coverage"] for row in rows)),
            "perInstanceCoverageMedian": float(np.median([row["coverage"] for row in rows])),
        },
        "checks": checks,
        "datasetIntegrity": {"removedCachesBefore": removed_before, "removedCachesAfter": removed_after, "datasetFilesSha256After": integrity["datasetFilesSha256"], "verified": integrity["ok"]},
        "perInstance": rows,
    }


def run(plan_path: Path, report_path: Path) -> dict[str, Any]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    analysis = compute(plan)
    report = {"schemaVersion": 1, "ok": analysis["decision"] == "local_boundary_refiner_band_reachable", "decision": analysis["decision"], "inputs": {"plan": {"path": str(plan_path), "sha256": sha256_file(plan_path)}, **plan["inputs"]}, "refinerHypothesis": plan["refinerHypothesis"], "reachabilityGate": plan["reachabilityGate"], "analysis": analysis, "analysisSha256": canonical_sha256(analysis), "errors": []}
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
        raise ValueError("局部边界修正器可达性重放不一致")
    if report.get("decision") != "local_boundary_refiner_band_reachable" or not report.get("ok"):
        raise ValueError("局部边界修正器理论上限未通过")
    return {"ok": True, "decision": "verified_local_boundary_refiner_band_reachable", "analysis": {key: value for key, value in replay.items() if key != "perInstance"}}


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
        print(json.dumps({"ok": result["ok"], "decision": result["decision"], "analysis": {key: value for key, value in result["analysis"].items() if key != "perInstance"}}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
