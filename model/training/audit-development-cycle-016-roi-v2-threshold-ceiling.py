#!/usr/bin/env python3
"""扫描冻结refinement权重的预注册阈值网格，判定校准路线可达性。"""

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
from transformers import SegformerConfig


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


def run(plan_path: Path, output_path: Path) -> dict[str, Any]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    evaluation_path = Path(plan["evaluationReport"])
    if sha256_file(evaluation_path) != plan["evaluationReportSha256"]:
        raise ValueError("冻结权重复评报告哈希与计划不一致")
    evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
    dataset_report_path = Path(evaluation["inputs"]["datasetMaterializationReport"]["path"])
    if sha256_file(dataset_report_path) != evaluation["inputs"]["datasetMaterializationReport"]["sha256"]:
        raise ValueError("v2物化报告哈希漂移")
    dataset_report = json.loads(dataset_report_path.read_text(encoding="utf-8"))
    selected = next(row for row in evaluation["results"] if row["id"] == evaluation["selectedBaselineArchitecture"])
    weights_path = Path(selected["weights"]["path"])
    if sha256_file(weights_path) != selected["weights"]["sha256"]:
        raise ValueError("冻结refinement权重哈希漂移")

    root = Path(__file__).resolve().parent
    base = load_module(root / "train-development-cycle-016-roi-segformer-pilot.py", "cycle016_base_threshold")
    refined_module = load_module(root / "train-development-cycle-016-roi-refinement-pilot.py", "cycle016_refined_threshold")
    checkpoint = torch.load(weights_path, map_location="cpu", weights_only=False)
    model = refined_module.RefinedSegformer(SegformerConfig.from_dict(checkpoint["config"]))
    model.load_state_dict(checkpoint["model"])
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device).eval()
    dataset_root = Path(dataset_report["outputDir"])
    manifest = json.loads((dataset_root / "manifest.json").read_text(encoding="utf-8"))
    records = [row for row in manifest["records"] if row["split"] == "val"]
    loader = DataLoader(base.RoiDataset(dataset_root, records, training=False, seed=0), batch_size=8, shuffle=False, num_workers=0, pin_memory=True)
    probabilities: list[np.ndarray] = []
    truths: list[np.ndarray] = []
    with torch.inference_mode():
        for images, truth, _ in loader:
            images = images.to(device, non_blocking=True)
            with torch.amp.autocast(device_type="cuda", enabled=device.type == "cuda"):
                logits = model(pixel_values=images)
                logits = F.interpolate(logits, size=truth.shape[-2:], mode="bilinear", align_corners=False)
            probabilities.extend(torch.sigmoid(logits).cpu().numpy()[:, 0])
            truths.extend(truth.numpy()[:, 0] >= 0.5)

    rows: list[dict[str, float]] = []
    for threshold in plan["thresholds"]:
        ious: list[float] = []
        boundary_ious: list[float] = []
        boundary_f1s: list[float] = []
        for probability, truth in zip(probabilities, truths, strict=True):
            prediction = probability >= float(threshold)
            union = np.logical_or(prediction, truth).sum()
            ious.append(float(np.logical_and(prediction, truth).sum() / union) if union else 1.0)
            biou, bf1 = base.boundary_metrics(truth, prediction, 2)
            boundary_ious.append(biou)
            boundary_f1s.append(bf1)
        joint = sum(
            iou >= 0.75 and biou >= 0.75 and bf1 >= 0.9
            for iou, biou, bf1 in zip(ious, boundary_ious, boundary_f1s, strict=True)
        ) / len(ious)
        rows.append({
            "threshold": threshold,
            "meanIou": round(float(np.mean(ious)), 8),
            "meanBoundaryIou": round(float(np.mean(boundary_ious)), 8),
            "meanBoundaryF1": round(float(np.mean(boundary_f1s)), 8),
            "jointInstancePassRate": round(joint, 8),
            "jointScore": round((float(np.mean(ious)) + float(np.mean(boundary_f1s))) / 2, 8),
        })
    best = max(rows, key=lambda row: row["jointScore"])
    gate = plan["gate"]
    reachable = any(
        row["meanIou"] >= gate["minimumMeanIou"]
        and row["meanBoundaryF1"] >= gate["minimumMeanBoundaryF1At2Pixels"]
        and row["jointInstancePassRate"] >= gate["minimumJointInstancePassRate"]
        for row in rows
    )
    report = {
        "schemaVersion": 1,
        "ok": True,
        "decision": "threshold_only_reachable" if reachable else "threshold_only_unreachable",
        "scope": plan["scope"],
        "inputs": {
            "plan": {"path": str(plan_path), "sha256": sha256_file(plan_path)},
            "evaluationReport": {"path": str(evaluation_path), "sha256": sha256_file(evaluation_path)},
            "weights": {"path": str(weights_path), "sha256": sha256_file(weights_path)},
            "datasetMaterializationReport": {"path": str(dataset_report_path), "sha256": sha256_file(dataset_report_path)},
        },
        "counts": {"valInstances": len(records)},
        "gate": gate,
        "rows": rows,
        "best": best,
        "reachable": reachable,
        "interpretation": "阈值扫描只判定校准路线，不改写既有pilot失败，也不构成正式候选或发布证据。",
        "errors": [],
    }
    write_atomic(output_path, report)
    return report


def verify(report_path: Path) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    for label, binding in report["inputs"].items():
        if sha256_file(Path(binding["path"])) != binding["sha256"]:
            raise ValueError(f"输入哈希漂移：{label}")
    return {"ok": True, "decision": "verified_roi_v2_threshold_ceiling", "result": report["decision"], "best": report["best"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        print(json.dumps(verify(args.verify_report), ensure_ascii=False, indent=2))
    else:
        if not args.plan or not args.output:
            parser.error("运行审计需要--plan与--output")
        print(json.dumps(run(args.plan, args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
