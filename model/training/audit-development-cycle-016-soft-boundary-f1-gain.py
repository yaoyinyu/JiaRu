#!/usr/bin/env python3
"""重建第五/第七轮逐实例预测并审计软Boundary F1监督增益与剩余瓶颈。"""

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
    seventh = json.loads(Path(plan["inputs"]["seventhReport"]["path"]).read_text(encoding="utf-8"))
    prior = json.loads(Path(plan["inputs"]["priorBottleneckReport"]["path"]).read_text(encoding="utf-8"))
    if fifth.get("decision") != "roi_dinov2_highres_decoder_internal_pilot_fail" or fifth.get("completedEpochs") != 30:
        raise ValueError("第五轮冻结失败报告不一致")
    if seventh.get("decision") != "roi_dinov2_soft_boundary_f1_internal_pilot_fail" or seventh.get("completedEpochs") != 30:
        raise ValueError("第七轮冻结失败报告不一致")
    if prior.get("decision") != "boundary_contrast_bottleneck" or not prior.get("ok"):
        raise ValueError("先前边界对比度瓶颈报告不一致")
    dataset_report = json.loads(Path(plan["inputs"]["datasetMaterializationReport"]["path"]).read_text(encoding="utf-8"))
    if dataset_report.get("datasetFilesSha256") != plan["reconstructionGate"]["requiredDatasetFilesSha256"]:
        raise ValueError("ROI v2数据集文件树哈希不一致")
    review = json.loads(Path(plan["inputs"]["finalReview"]["path"]).read_text(encoding="utf-8"))
    if review.get("decision") != "roi_validation_truth_v2_full_review_pass":
        raise ValueError("ROI v2原分辨率全量审核未通过")
    return fifth, seventh, prior, Path(dataset_report["outputDir"])


def load_frozen_model(report: dict[str, Any], weights_path: Path, architecture: Any, trainer: Any, device: torch.device) -> torch.nn.Module:
    plan_binding = report["inputs"]["plan"]
    plan_path = Path(plan_binding["path"])
    if sha256_file(plan_path) != plan_binding["sha256"]:
        raise ValueError("训练计划哈希漂移")
    training_plan = json.loads(plan_path.read_text(encoding="utf-8"))
    model = trainer.build_model(training_plan, architecture)
    checkpoint = torch.load(weights_path, map_location="cpu", weights_only=True)
    model.load_state_dict(checkpoint["model"], strict=True)
    return model.to(device).eval()


def metrics(truth: np.ndarray, prediction: np.ndarray, base: Any) -> dict[str, float]:
    union = np.logical_or(truth, prediction).sum()
    iou = float(np.logical_and(truth, prediction).sum() / union) if union else 1.0
    boundary_iou, boundary_f1 = base.boundary_metrics(truth, prediction, 2)
    return {"iou": iou, "boundaryIou": boundary_iou, "boundaryF1": boundary_f1}


def aggregate(rows: list[dict[str, Any]], key: str, thresholds: dict[str, float]) -> dict[str, Any]:
    values = [row[key] for row in rows]
    iou_pass = [value["iou"] >= float(thresholds["iou"]) for value in values]
    boundary_iou_pass = [value["boundaryIou"] >= float(thresholds["boundaryIou"]) for value in values]
    boundary_f1_pass = [value["boundaryF1"] >= float(thresholds["boundaryF1"]) for value in values]
    joint = [a and b and c for a, b, c in zip(iou_pass, boundary_iou_pass, boundary_f1_pass, strict=True)]
    count = len(values)
    return {
        "meanIou": round(float(np.mean([value["iou"] for value in values])), 8),
        "meanBoundaryIou": round(float(np.mean([value["boundaryIou"] for value in values])), 8),
        "meanBoundaryF1": round(float(np.mean([value["boundaryF1"] for value in values])), 8),
        "jointInstancePassRate": round(sum(joint) / count, 8),
        "jointScore": round(float(np.mean([(value["iou"] + value["boundaryF1"]) / 2 for value in values])), 8),
        "instanceGateCounts": {"iou": int(sum(iou_pass)), "boundaryIou": int(sum(boundary_iou_pass)), "boundaryF1": int(sum(boundary_f1_pass)), "joint": int(sum(joint)), "denominator": count},
    }


def fidelity(actual: dict[str, Any], expected: dict[str, float], tolerance: float) -> dict[str, Any]:
    keys = ("meanIou", "meanBoundaryIou", "meanBoundaryF1", "jointInstancePassRate", "jointScore")
    deltas = {key: abs(float(actual[key]) - float(expected[key])) for key in keys}
    return {"ok": all(value <= tolerance for value in deltas.values()), "deltas": deltas}


@torch.inference_mode()
def compute(plan: dict[str, Any]) -> dict[str, Any]:
    fifth_report, seventh_report, prior_report, dataset_root = validate_plan(plan)
    manifest = json.loads((dataset_root / "manifest.json").read_text(encoding="utf-8"))
    val_records = [row for row in manifest["records"] if row["split"] == "val"]
    required = int(plan["reconstructionGate"]["requiredRecordCount"])
    if len(val_records) != required:
        raise ValueError("ROI v2验证实例数不一致")
    prior_rows = prior_report["analysis"]["perInstance"]
    expected_ids = [str(row["id"]) for row in val_records]
    if [row["id"] for row in prior_rows] != expected_ids:
        raise ValueError("先前瓶颈报告身份顺序不一致")
    contrast_by_id = {row["id"]: float(row["localBoundaryContrast"]) for row in prior_rows}
    contrast_order = np.argsort(np.asarray([contrast_by_id[value] for value in expected_ids]), kind="stable")
    low_ids = {expected_ids[int(index)] for index in contrast_order[:70]}
    base = load_module("train-development-cycle-016-roi-segformer-pilot.py", "cycle016_gain_base")
    architecture = load_module("audit-development-cycle-016-dinov2-highres-decoder-feasibility.py", "cycle016_gain_architecture")
    trainer = load_module("train-development-cycle-016-dinov2-highres-decoder-pilot.py", "cycle016_gain_trainer")
    guards = load_module("train-yolo-seg.py", "cycle016_gain_guard")
    materializer = load_module("materialize-development-cycle-016-roi-dataset-v2.py", "cycle016_gain_materializer")
    guards.install_read_only_ultralytics_image_check()
    removed_before = guards.remove_ultralytics_label_caches(dataset_root)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type != "cuda":
        raise RuntimeError("逐实例冻结权重重建预注册为CUDA推理")
    fifth_model = load_frozen_model(fifth_report, Path(plan["inputs"]["fifthWeights"]["path"]), architecture, trainer, device)
    seventh_model = load_frozen_model(seventh_report, Path(plan["inputs"]["seventhWeights"]["path"]), architecture, trainer, device)
    dataset = base.RoiDataset(dataset_root, val_records, training=False, seed=1605)
    loader = DataLoader(dataset, batch_size=2, shuffle=False, num_workers=0, pin_memory=True)
    rows: list[dict[str, Any]] = []
    try:
        for images, truth, identities in loader:
            images_device = images.to(device, non_blocking=True)
            with torch.amp.autocast(device_type="cuda"):
                fifth_logits = fifth_model(pixel_values=images_device)
                seventh_logits = seventh_model(pixel_values=images_device)
            fifth_predictions = (torch.sigmoid(fifth_logits) >= 0.5).cpu().numpy()[:, 0]
            seventh_predictions = (torch.sigmoid(seventh_logits) >= 0.5).cpu().numpy()[:, 0]
            truths = truth.numpy()[:, 0] >= 0.5
            for identity, target, fifth_prediction, seventh_prediction in zip(identities, truths, fifth_predictions, seventh_predictions, strict=True):
                key = str(identity)
                fifth_value = metrics(target, fifth_prediction, base)
                seventh_value = metrics(target, seventh_prediction, base)
                rows.append({"id": key, "localBoundaryContrast": contrast_by_id[key], "lowContrastQuartile": key in low_ids, "fifth": fifth_value, "seventh": seventh_value, "delta": {name: seventh_value[name] - fifth_value[name] for name in fifth_value}})
    finally:
        del fifth_model, seventh_model
        torch.cuda.empty_cache()
        removed_after = guards.remove_ultralytics_label_caches(dataset_root)
    thresholds = plan["analysisContract"]["instancePassThresholds"]
    fifth_aggregate = aggregate(rows, "fifth", thresholds)
    seventh_aggregate = aggregate(rows, "seventh", thresholds)
    tolerance = float(plan["reconstructionGate"]["aggregateTolerance"])
    fifth_fidelity = fidelity(fifth_aggregate, fifth_report["best"]["validation"], tolerance)
    seventh_fidelity = fidelity(seventh_aggregate, seventh_report["best"]["validation"], tolerance)
    if [row["id"] for row in rows] != expected_ids or not fifth_fidelity["ok"] or not seventh_fidelity["ok"]:
        return {"decision": "reconstruction_mismatch", "idOrderMatches": [row["id"] for row in rows] == expected_ids, "fifthAggregate": fifth_aggregate, "seventhAggregate": seventh_aggregate, "fifthFidelity": fifth_fidelity, "seventhFidelity": seventh_fidelity}
    deltas = np.asarray([row["delta"]["boundaryF1"] for row in rows], dtype=np.float64)
    low_deltas = np.asarray([row["delta"]["boundaryF1"] for row in rows if row["lowContrastQuartile"]], dtype=np.float64)
    mean_gain = float(seventh_aggregate["meanBoundaryF1"] - fifth_aggregate["meanBoundaryF1"])
    iou_delta = float(seventh_aggregate["meanIou"] - fifth_aggregate["meanIou"])
    improved_fraction = float((deltas > 0).mean())
    low_gain = float(low_deltas.mean())
    contract = plan["analysisContract"]
    gain_checks = {
        "meanBoundaryF1Gain": mean_gain >= float(contract["meaningfulMeanBoundaryF1Gain"]),
        "meanIouRegressionWithinCap": iou_delta >= -float(contract["maximumAllowedMeanIouRegression"]),
        "improvedInstanceFraction": improved_fraction >= float(contract["minimumImprovedInstanceFraction"]),
        "lowContrastQuartileGain": low_gain >= float(contract["minimumLowContrastQuartileMeanBoundaryF1Gain"]),
    }
    meaningful = all(gain_checks.values())
    boundary_iou_pass_fraction = seventh_aggregate["instanceGateCounts"]["boundaryIou"] / required
    architecture_limited = seventh_aggregate["meanBoundaryF1"] < float(contract["architectureLimitedMeanBoundaryF1Ceiling"]) or boundary_iou_pass_fraction < float(contract["architectureLimitedMaximumBoundaryIouPassFraction"])
    if meaningful and architecture_limited:
        decision = "objective_effective_but_fine_boundary_architecture_limited"
    elif meaningful:
        decision = "objective_effective_consider_one_strength_confirmation"
    else:
        decision = "objective_not_broadly_effective_close_branch"
    integrity = materializer.verify(Path(plan["inputs"]["datasetMaterializationReport"]["path"]))
    return {
        "decision": decision,
        "idOrderMatches": True,
        "fifthAggregate": fifth_aggregate,
        "seventhAggregate": seventh_aggregate,
        "fifthFidelity": fifth_fidelity,
        "seventhFidelity": seventh_fidelity,
        "pairedBoundaryF1": {"meanGain": mean_gain, "medianGain": float(np.median(deltas)), "improvedCount": int((deltas > 0).sum()), "unchangedCount": int((deltas == 0).sum()), "worsenedCount": int((deltas < 0).sum()), "improvedFraction": improved_fraction, "lowContrastQuartileMeanGain": low_gain, "lowContrastQuartileMedianGain": float(np.median(low_deltas))},
        "meanIouDelta": iou_delta,
        "boundaryIouPassFraction": boundary_iou_pass_fraction,
        "gainChecks": gain_checks,
        "meaningfulGain": meaningful,
        "architectureLimited": architecture_limited,
        "remainingGap": {"meanBoundaryF1ToGate": float(0.9 - seventh_aggregate["meanBoundaryF1"]), "jointInstancePassRateToGate": float(0.8 - seventh_aggregate["jointInstancePassRate"])},
        "datasetIntegrity": {"removedCachesBefore": removed_before, "removedCachesAfter": removed_after, "datasetFilesSha256After": integrity["datasetFilesSha256"], "verified": integrity["ok"]},
        "perInstance": rows,
    }


def run(plan_path: Path, report_path: Path) -> dict[str, Any]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    analysis = compute(plan)
    report = {"schemaVersion": 1, "ok": analysis["decision"] != "reconstruction_mismatch", "decision": analysis["decision"], "inputs": {"plan": {"path": str(plan_path), "sha256": sha256_file(plan_path)}, **plan["inputs"]}, "analysisContract": plan["analysisContract"], "analysis": analysis, "analysisSha256": canonical_sha256(analysis), "errors": []}
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
        raise ValueError("软Boundary F1增益审计重放不一致")
    if not report.get("ok") or report.get("decision") == "reconstruction_mismatch":
        raise ValueError("软Boundary F1增益审计保真门未通过")
    return {"ok": True, "decision": f"verified_{report['decision']}", "analysis": {key: value for key, value in replay.items() if key != "perInstance"}}


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
