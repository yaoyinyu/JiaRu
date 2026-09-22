#!/usr/bin/env python3
"""重建第七轮在无增强train/val上的拟合差并诊断瓶颈。"""

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
    ninth_gain = json.loads(Path(plan["inputs"]["ninthGainAudit"]["path"]).read_text(encoding="utf-8"))
    correction = json.loads(Path(plan["inputs"]["correctionLossFeasibility"]["path"]).read_text(encoding="utf-8"))
    if seventh.get("decision") != "roi_dinov2_soft_boundary_f1_internal_pilot_fail" or seventh.get("completedEpochs") != 30:
        raise ValueError("第七轮冻结报告不一致")
    if ninth_gain.get("decision") != "local_boundary_refiner_not_broadly_effective_close_branch" or not ninth_gain.get("ok"):
        raise ValueError("第九轮关闭判决不一致")
    if correction.get("decision") != "correction_balanced_loss_not_reachable_no_training" or correction.get("ok"):
        raise ValueError("修正平衡损失止损报告不一致")
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


def aggregate(rows: list[dict[str, Any]], thresholds: dict[str, float]) -> dict[str, Any]:
    iou_pass = [row["metrics"]["iou"] >= float(thresholds["iou"]) for row in rows]
    boundary_iou_pass = [row["metrics"]["boundaryIou"] >= float(thresholds["boundaryIou"]) for row in rows]
    boundary_f1_pass = [row["metrics"]["boundaryF1"] >= float(thresholds["boundaryF1"]) for row in rows]
    joint = [a and b and c for a, b, c in zip(iou_pass, boundary_iou_pass, boundary_f1_pass, strict=True)]
    return {
        "meanIou": round(float(np.mean([row["metrics"]["iou"] for row in rows])), 8),
        "meanBoundaryIou": round(float(np.mean([row["metrics"]["boundaryIou"] for row in rows])), 8),
        "meanBoundaryF1": round(float(np.mean([row["metrics"]["boundaryF1"] for row in rows])), 8),
        "jointInstancePassRate": round(float(np.mean(joint)), 8),
        "jointScore": round(float(np.mean([(row["metrics"]["iou"] + row["metrics"]["boundaryF1"]) / 2 for row in rows])), 8),
        "instanceGateCounts": {"iou": int(sum(iou_pass)), "boundaryIou": int(sum(boundary_iou_pass)), "boundaryF1": int(sum(boundary_f1_pass)), "joint": int(sum(joint)), "denominator": len(rows)},
    }


def fidelity(actual: dict[str, Any], expected: dict[str, float], tolerance: float) -> dict[str, Any]:
    keys = ("meanIou", "meanBoundaryIou", "meanBoundaryF1", "jointInstancePassRate", "jointScore")
    deltas = {key: abs(float(actual[key]) - float(expected[key])) for key in keys}
    return {"ok": all(value <= tolerance for value in deltas.values()), "deltas": deltas}


@torch.inference_mode()
def infer_split(model: torch.nn.Module, dataset_root: Path, records: list[dict[str, Any]], base: Any, device: torch.device, threshold: float) -> list[dict[str, Any]]:
    dataset = base.RoiDataset(dataset_root, records, training=False, seed=1605)
    loader = DataLoader(dataset, batch_size=2, shuffle=False, num_workers=0, pin_memory=True)
    rows: list[dict[str, Any]] = []
    for images, truth, identities in loader:
        images = images.to(device, non_blocking=True)
        with torch.amp.autocast(device_type="cuda"):
            logits = model(pixel_values=images)
        predictions = (torch.sigmoid(logits) >= threshold).cpu().numpy()[:, 0]
        truths = truth.numpy()[:, 0] >= 0.5
        for identity, target, prediction in zip(identities, truths, predictions, strict=True):
            rows.append({"id": str(identity), "metrics": metrics(target, prediction, base)})
    return rows


@torch.inference_mode()
def compute(plan: dict[str, Any]) -> dict[str, Any]:
    seventh, _, dataset_root = validate_plan(plan)
    manifest = json.loads((dataset_root / "manifest.json").read_text(encoding="utf-8"))
    train_records = [row for row in manifest["records"] if row["split"] == "train"]
    val_records = [row for row in manifest["records"] if row["split"] == "val"]
    if len(train_records) != int(plan["reconstructionGate"]["requiredTrainInstances"]) or len(val_records) != int(plan["reconstructionGate"]["requiredValidationInstances"]):
        raise ValueError("ROI v2 train/val实例数不一致")
    guards = load_module("train-yolo-seg.py", "cycle016_fit_gap_guard")
    materializer = load_module("materialize-development-cycle-016-roi-dataset-v2.py", "cycle016_fit_gap_materializer")
    base = load_module("train-development-cycle-016-roi-segformer-pilot.py", "cycle016_fit_gap_dataset")
    architecture = load_module("audit-development-cycle-016-dinov2-highres-decoder-feasibility.py", "cycle016_fit_gap_architecture")
    trainer = load_module("train-development-cycle-016-soft-boundary-f1-pilot.py", "cycle016_fit_gap_trainer")
    guards.install_read_only_ultralytics_image_check()
    removed_before = guards.remove_ultralytics_label_caches(dataset_root)
    cleanup = lambda: guards.remove_ultralytics_label_caches(dataset_root)
    atexit.register(cleanup)
    training_plan_path = Path(seventh["inputs"]["plan"]["path"])
    if sha256_file(training_plan_path) != seventh["inputs"]["plan"]["sha256"]:
        raise ValueError("第七轮训练计划哈希漂移")
    training_plan = json.loads(training_plan_path.read_text(encoding="utf-8"))
    model = trainer.build_model(training_plan, architecture)
    checkpoint = torch.load(Path(plan["inputs"]["seventhWeights"]["path"]), map_location="cpu", weights_only=True)
    model.load_state_dict(checkpoint["model"], strict=True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type != "cuda":
        raise RuntimeError("拟合差重建预注册为CUDA推理")
    model = model.to(device).eval()
    threshold = float(plan["reconstructionGate"]["scoreThreshold"])
    try:
        train_rows = infer_split(model, dataset_root, train_records, base, device, threshold)
        val_rows = infer_split(model, dataset_root, val_records, base, device, threshold)
    finally:
        del model
        torch.cuda.empty_cache()
        removed_after = guards.remove_ultralytics_label_caches(dataset_root)
    thresholds = plan["reconstructionGate"]["instancePassThresholds"]
    train_aggregate = aggregate(train_rows, thresholds)
    val_aggregate = aggregate(val_rows, thresholds)
    val_fidelity = fidelity(val_aggregate, seventh["best"]["validation"], float(plan["reconstructionGate"]["aggregateTolerance"]))
    train_ids_match = [row["id"] for row in train_rows] == [str(row["id"]) for row in train_records]
    val_ids_match = [row["id"] for row in val_rows] == [str(row["id"]) for row in val_records]
    if not train_ids_match or not val_ids_match or not val_fidelity["ok"]:
        return {"decision": "reconstruction_mismatch", "trainIdentityOrderMatches": train_ids_match, "validationIdentityOrderMatches": val_ids_match, "validationAggregate": val_aggregate, "validationFidelity": val_fidelity}
    formal = plan["diagnosisContract"]["formalFitThresholds"]
    underfit = plan["diagnosisContract"]["underfitThresholds"]
    train_formal_pass = train_aggregate["meanIou"] >= float(formal["minimumTrainMeanIou"]) and train_aggregate["meanBoundaryF1"] >= float(formal["minimumTrainMeanBoundaryF1"]) and train_aggregate["jointInstancePassRate"] >= float(formal["minimumTrainJointInstancePassRate"])
    train_underfit = train_aggregate["meanBoundaryF1"] < float(underfit["maximumTrainMeanBoundaryF1"]) or train_aggregate["jointInstancePassRate"] < float(underfit["maximumTrainJointInstancePassRate"])
    validation_formal_pass = val_aggregate["meanIou"] >= float(formal["minimumTrainMeanIou"]) and val_aggregate["meanBoundaryF1"] >= float(formal["minimumTrainMeanBoundaryF1"]) and val_aggregate["jointInstancePassRate"] >= float(formal["minimumTrainJointInstancePassRate"])
    if train_underfit:
        decision = "representation_or_optimization_underfit"
    elif train_formal_pass and not validation_formal_pass:
        decision = "source_group_generalization_bottleneck"
    else:
        decision = "mixed_fit_and_generalization_bottleneck"
    integrity = materializer.verify(Path(plan["inputs"]["datasetMaterializationReport"]["path"]))
    atexit.unregister(cleanup)
    return {
        "decision": decision,
        "trainIdentityOrderMatches": True,
        "validationIdentityOrderMatches": True,
        "trainAggregate": train_aggregate,
        "validationAggregate": val_aggregate,
        "validationFidelity": val_fidelity,
        "fitGap": {key: float(train_aggregate[key] - val_aggregate[key]) for key in ("meanIou", "meanBoundaryIou", "meanBoundaryF1", "jointInstancePassRate", "jointScore")},
        "trainFormalPass": train_formal_pass,
        "validationFormalPass": validation_formal_pass,
        "trainUnderfit": train_underfit,
        "datasetIntegrity": {"removedCachesBefore": removed_before, "removedCachesAfter": removed_after, "datasetFilesSha256After": integrity["datasetFilesSha256"], "verified": integrity["ok"]},
        "perInstance": {"train": train_rows, "validation": val_rows},
    }


def run(plan_path: Path, report_path: Path) -> dict[str, Any]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    analysis = compute(plan)
    report = {"schemaVersion": 1, "ok": analysis["decision"] != "reconstruction_mismatch", "decision": analysis["decision"], "inputs": {"plan": {"path": str(plan_path), "sha256": sha256_file(plan_path)}, **plan["inputs"]}, "diagnosisContract": plan["diagnosisContract"], "analysis": analysis, "analysisSha256": canonical_sha256(analysis), "errors": []}
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
        raise ValueError("train/val拟合差审计重放不一致")
    if not report.get("ok") or report.get("decision") == "reconstruction_mismatch":
        raise ValueError("train/val拟合差保真门未通过")
    return {"ok": True, "decision": f"verified_{report['decision']}", "analysis": {key: value for key, value in replay.items() if key != "perInstance"}}


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
