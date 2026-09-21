#!/usr/bin/env python3
"""在冻结的ROI验证真值v2上只读复评cycle016既有pilot权重。"""

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
from transformers import SegformerConfig, SegformerForSemanticSegmentation


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
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


def verify_binding(path_text: str, expected: str, label: str) -> Path:
    path = Path(path_text)
    actual = sha256_file(path)
    if actual != expected:
        raise ValueError(f"{label}哈希不一致：expected={expected}, actual={actual}")
    return path


@torch.inference_mode()
def evaluate_model(model: torch.nn.Module, loader: DataLoader, device: torch.device, refined: bool, base: Any) -> dict[str, float]:
    model.eval()
    losses: list[float] = []
    ious: list[float] = []
    boundary_ious: list[float] = []
    boundary_f1s: list[float] = []
    for images, truth, _ in loader:
        images = images.to(device, non_blocking=True)
        truth = truth.to(device, non_blocking=True)
        with torch.amp.autocast(device_type="cuda", enabled=device.type == "cuda"):
            logits = model(pixel_values=images) if refined else model(pixel_values=images).logits
            loss, _ = base.segmentation_loss(logits, truth)
            logits = F.interpolate(logits, size=truth.shape[-2:], mode="bilinear", align_corners=False)
        losses.append(float(loss))
        predictions = (torch.sigmoid(logits) >= 0.5).cpu().numpy()[:, 0]
        truths = truth.cpu().numpy()[:, 0] >= 0.5
        for prediction, target in zip(predictions, truths, strict=True):
            union = np.logical_or(prediction, target).sum()
            ious.append(float(np.logical_and(prediction, target).sum() / union) if union else 1.0)
            boundary_iou, boundary_f1 = base.boundary_metrics(target, prediction, 2)
            boundary_ious.append(boundary_iou)
            boundary_f1s.append(boundary_f1)
    joint = sum(
        iou >= 0.75 and boundary_iou >= 0.75 and boundary_f1 >= 0.9
        for iou, boundary_iou, boundary_f1 in zip(ious, boundary_ious, boundary_f1s, strict=True)
    )
    return {
        "loss": round(float(np.mean(losses)), 8),
        "meanIou": round(float(np.mean(ious)), 8),
        "meanBoundaryIou": round(float(np.mean(boundary_ious)), 8),
        "meanBoundaryF1": round(float(np.mean(boundary_f1s)), 8),
        "jointInstancePassRate": round(joint / len(ious), 8),
        "jointScore": round((float(np.mean(ious)) + float(np.mean(boundary_f1s))) / 2, 8),
    }


def run(plan_path: Path, output_path: Path) -> dict[str, Any]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    dataset = plan["dataset"]
    dataset_report_path = verify_binding(dataset["materializationReport"], dataset["materializationReportSha256"], "v2物化报告")
    final_review_path = verify_binding(dataset["finalReview"], dataset["finalReviewSha256"], "v2全量审核报告")
    dataset_report = json.loads(dataset_report_path.read_text(encoding="utf-8"))
    final_review = json.loads(final_review_path.read_text(encoding="utf-8"))
    if dataset_report["datasetFilesSha256"] != dataset["datasetFilesSha256"]:
        raise ValueError("v2数据集聚合哈希与计划不一致")
    if final_review.get("decision") != "roi_validation_truth_v2_full_review_pass":
        raise ValueError("v2全量审核未通过")
    if dataset_report["counts"]["valInstances"] != dataset["expectedValInstances"]:
        raise ValueError("v2验证实例数与计划不一致")
    if dataset_report["counts"]["valSourceGroups"] != dataset["expectedValSourceGroups"]:
        raise ValueError("v2验证来源组数与计划不一致")

    script_root = Path(__file__).resolve().parent
    base = load_module(script_root / "train-development-cycle-016-roi-segformer-pilot.py", "cycle016_base")
    refined_module = load_module(script_root / "train-development-cycle-016-roi-refinement-pilot.py", "cycle016_refined")
    dataset_root = Path(dataset_report["outputDir"])
    manifest = json.loads((dataset_root / "manifest.json").read_text(encoding="utf-8"))
    val_records = [row for row in manifest["records"] if row["split"] == "val"]
    val_dataset = base.RoiDataset(dataset_root, val_records, training=False, seed=0)
    loader = DataLoader(val_dataset, batch_size=int(plan["evaluation"]["batchSize"]), shuffle=False, num_workers=0, pin_memory=True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    results: list[dict[str, Any]] = []
    for pilot in plan["pilots"]:
        weights_path = verify_binding(pilot["weights"], pilot["weightsSha256"], f"{pilot['id']}权重")
        train_report_path = verify_binding(pilot["originalTrainReport"], pilot["originalTrainReportSha256"], f"{pilot['id']}旧报告")
        train_report = json.loads(train_report_path.read_text(encoding="utf-8"))
        checkpoint = torch.load(weights_path, map_location="cpu", weights_only=False)
        config = SegformerConfig.from_dict(checkpoint["config"])
        if pilot["kind"] == "base":
            model = SegformerForSemanticSegmentation(config)
            refined = False
        elif pilot["kind"] == "refined":
            model = refined_module.RefinedSegformer(config)
            refined = True
        else:
            raise ValueError(f"未知pilot类型：{pilot['kind']}")
        model.load_state_dict(checkpoint["model"])
        model.to(device)
        current = evaluate_model(model, loader, device, refined, base)
        previous = train_report["best"]["validation"]
        results.append({
            "id": pilot["id"],
            "kind": pilot["kind"],
            "checkpointEpoch": checkpoint["epoch"],
            "weights": {"path": str(weights_path), "sha256": sha256_file(weights_path)},
            "originalV1": previous,
            "correctedV2": current,
            "deltaV2MinusV1": {
                key: round(float(current[key]) - float(previous[key]), 8)
                for key in ("loss", "meanIou", "meanBoundaryIou", "meanBoundaryF1", "jointInstancePassRate", "jointScore")
            },
        })
        del model
        if device.type == "cuda":
            torch.cuda.empty_cache()

    ranking = sorted(results, key=lambda row: row["correctedV2"]["jointScore"], reverse=True)
    winner = ranking[0]
    report = {
        "schemaVersion": 1,
        "ok": True,
        "decision": "frozen_pilots_evaluated_on_corrected_roi_validation_truth_v2",
        "scope": plan["scope"],
        "inputs": {
            "plan": {"path": str(plan_path), "sha256": sha256_file(plan_path)},
            "datasetMaterializationReport": {"path": str(dataset_report_path), "sha256": sha256_file(dataset_report_path)},
            "finalReview": {"path": str(final_review_path), "sha256": sha256_file(final_review_path)},
        },
        "environment": {"torch": torch.__version__, "device": torch.cuda.get_device_name(0) if device.type == "cuda" else "cpu"},
        "counts": {"valInstances": len(val_records), "valSourceGroups": dataset_report["counts"]["valSourceGroups"]},
        "evaluation": plan["evaluation"],
        "results": results,
        "ranking": [row["id"] for row in ranking],
        "selectedBaselineArchitecture": winner["id"],
        "selectedBaselineJointScore": winner["correctedV2"]["jointScore"],
        "interpretation": "复评仅选择第三轮开发基线；既有pilot仍为失败，当前结果不是正式候选或发布证据。",
        "errors": [],
    }
    write_atomic(output_path, report)
    return report


def verify(report_path: Path) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    for label, binding in report["inputs"].items():
        verify_binding(binding["path"], binding["sha256"], label)
    plan = json.loads(Path(report["inputs"]["plan"]["path"]).read_text(encoding="utf-8"))
    for pilot, result in zip(plan["pilots"], report["results"], strict=True):
        verify_binding(pilot["weights"], result["weights"]["sha256"], f"{pilot['id']}权重")
    return {"ok": True, "decision": "verified_frozen_pilots_roi_v2_evaluation", "selectedBaselineArchitecture": report["selectedBaselineArchitecture"], "results": report["results"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        print(json.dumps(verify(args.verify_report), ensure_ascii=False, indent=2))
        return
    if not args.plan or not args.output:
        parser.error("运行复评需要同时提供--plan与--output")
    print(json.dumps(run(args.plan, args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
