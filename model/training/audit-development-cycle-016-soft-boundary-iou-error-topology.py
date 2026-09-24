#!/usr/bin/env python3
"""只读重建固定train-only微拟合，再诊断严格边界失败的像素位置。"""

from __future__ import annotations

import argparse
import atexit
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch
from torch.utils.data import DataLoader


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_module(file_name: str, name: str) -> Any:
    path = Path(__file__).resolve().with_name(file_name)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def shape_metrics(base: Any, truth: np.ndarray, prediction: np.ndarray) -> dict[str, float]:
    union = int(np.logical_or(truth, prediction).sum())
    iou = float(np.logical_and(truth, prediction).sum() / union) if union else 1.0
    boundary_iou, boundary_f1 = base.boundary_metrics(truth, prediction, 2)
    return {"iou": iou, "boundaryIou": boundary_iou, "boundaryF1": boundary_f1}


def diagnostic_oracle(base: Any, truth: np.ndarray, prediction: np.ndarray) -> dict[str, object]:
    """仅计算真值知情的train诊断上限，绝不可作为生产后处理。"""
    height, width = prediction.shape
    kernel = np.ones((3, 3), dtype=np.uint8)
    options: list[tuple[float, str, bool]] = []
    for operation in ("identity", "erode1", "dilate1"):
        mask = prediction.astype(np.uint8)
        if operation == "erode1":
            mask = cv2.erode(mask, kernel, iterations=1)
        elif operation == "dilate1":
            mask = cv2.dilate(mask, kernel, iterations=1)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                shifted = cv2.warpAffine(mask, np.float32([[1, 0, dx], [0, 1, dy]]),
                                         (width, height), flags=cv2.INTER_NEAREST,
                                         borderMode=cv2.BORDER_CONSTANT, borderValue=0).astype(bool)
                metrics = shape_metrics(base, truth, shifted)
                joint = metrics["iou"] >= 0.75 and metrics["boundaryIou"] >= 0.75 and metrics["boundaryF1"] >= 0.9
                options.append((metrics["boundaryIou"], f"{operation}:dx{dx}:dy{dy}", joint))
    best = max(options, key=lambda item: (item[0], item[1]))
    return {"bestBoundaryIou": best[0], "bestTransform": best[1],
            "anyJointPass": any(option[2] for option in options), "candidateTransforms": len(options)}


def error_geometry(truth: np.ndarray, prediction: np.ndarray) -> dict[str, object]:
    false_positive = np.logical_and(prediction, ~truth)
    false_negative = np.logical_and(truth, ~prediction)
    disagreement = np.logical_xor(truth, prediction)
    boundary = truth.astype(np.uint8) - cv2.erode(truth.astype(np.uint8), np.ones((3, 3), np.uint8))
    near_two = cv2.dilate(boundary, np.ones((5, 5), np.uint8)).astype(bool)
    near_five = cv2.dilate(boundary, np.ones((11, 11), np.uint8)).astype(bool)
    mismatched = int(disagreement.sum())
    return {
        "truthAreaPixels": int(truth.sum()), "predictionAreaPixels": int(prediction.sum()),
        "falsePositivePixels": int(false_positive.sum()), "falseNegativePixels": int(false_negative.sum()),
        "disagreementPixels": mismatched,
        "disagreementWithin2PxBoundary": int(np.logical_and(disagreement, near_two).sum()),
        "disagreementWithin5PxBoundary": int(np.logical_and(disagreement, near_five).sum()),
        "disagreementBeyond5PxBoundary": int(np.logical_and(disagreement, ~near_five).sum()),
        "truthBoundaryPixels": int(boundary.sum()),
        "truthTouchesCropBorder": bool(truth[0].any() or truth[-1].any() or truth[:, 0].any() or truth[:, -1].any()),
    }


def compute(plan_path: Path) -> dict[str, object]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if plan["schemaVersion"] != 1 or plan["analysis"]["selectedTrainInstances"] != 32:
        raise ValueError("诊断计划合同无效")
    for name, binding in plan["inputs"].items():
        if not Path(binding["path"]).is_file() or sha256_file(Path(binding["path"])) != binding["sha256"]:
            raise ValueError(f"冻结输入哈希漂移：{name}")
    prior = json.loads(Path(plan["inputs"]["microfitReport"]["path"]).read_text(encoding="utf-8"))
    if prior["decision"] != "soft_boundary_iou_train_only_microfit_fail_no_full_pilot" or prior["completedOptimizerSteps"] != 256:
        raise ValueError("前序失败报告不符")
    if prior["inputs"]["finalWeights"]["sha256"] != plan["inputs"]["finalWeights"]["sha256"]:
        raise ValueError("冻结权重不符")
    if prior["inputs"]["plan"]["sha256"] != plan["inputs"]["microfitPlan"]["sha256"]:
        raise ValueError("微拟合计划绑定不符")
    microfit_plan = json.loads(Path(plan["inputs"]["microfitPlan"]["path"]).read_text(encoding="utf-8"))
    selected_ids = microfit_plan["dataset"]["selectedTrainIds"]
    if plan["analysis"]["scoreThreshold"] != microfit_plan["training"]["scoreThreshold"] or plan["analysis"]["diagnosticOracle"] != "3 morphology operations x 9 integer shifts; train truth aware, no deployment":
        raise ValueError("冻结诊断口径漂移")
    if selected_ids != prior["dataset"]["selectedTrainIds"] or len(selected_ids) != 32:
        raise ValueError("train-only名单不符")
    materialization_path = Path(plan["inputs"]["materializationReport"]["path"])
    materialization = json.loads(materialization_path.read_text(encoding="utf-8"))
    root = Path(materialization["outputDir"])
    guards = load_module("train-yolo-seg.py", "cycle016_error_guard")
    materializer = load_module("materialize-development-cycle-016-roi-dataset-v2.py", "cycle016_error_materializer")
    guards.install_read_only_ultralytics_image_check()
    removed_before = guards.remove_ultralytics_label_caches(root)
    cleanup = lambda: guards.remove_ultralytics_label_caches(root)
    atexit.register(cleanup)
    before = materializer.verify(materialization_path)
    if not before["ok"] or before["datasetFilesSha256"] != microfit_plan["dataset"]["datasetFilesSha256"]:
        raise ValueError("ROI v2数据集前置重放失败")
    rows = json.loads((root / "manifest.json").read_text(encoding="utf-8"))["records"]
    by_id = {row["id"]: row for row in rows if row["split"] == "train"}
    if any(identity not in by_id for identity in selected_ids):
        raise ValueError("train-only身份缺失")
    selected = [by_id[identity] for identity in selected_ids]
    if len({row["sourceGroup"] for row in selected}) != 32:
        raise ValueError("来源组不互异")

    base = load_module("train-development-cycle-016-roi-segformer-pilot.py", "cycle016_error_base")
    auditor = load_module("audit-development-cycle-016-bidirectional-highres-feasibility.py", "cycle016_error_model")
    dataset = base.RoiDataset(root, selected, training=False, seed=int(microfit_plan["training"]["seed"]))
    loader = DataLoader(dataset, batch_size=2, shuffle=False, num_workers=0)
    model = auditor.load_model(microfit_plan).cuda().eval()
    checkpoint = torch.load(Path(plan["inputs"]["finalWeights"]["path"]), map_location="cpu", weights_only=True)
    model.load_state_dict(checkpoint["model"], strict=True)
    reconstructed: list[dict[str, object]] = []
    with torch.inference_mode():
        for images, masks, identities in loader:
            with torch.amp.autocast(device_type="cuda"):
                logits = model(images.cuda())
            predictions = (torch.sigmoid(logits) >= float(microfit_plan["training"]["scoreThreshold"])).cpu().numpy()[:, 0]
            truths = masks.numpy()[:, 0] >= 0.5
            for identity, truth, prediction in zip(identities, truths, predictions, strict=True):
                metrics = shape_metrics(base, truth, prediction)
                reconstructed.append({"id": identity, **metrics, "error": error_geometry(truth, prediction),
                                      "trainTruthAwareOracle": diagnostic_oracle(base, truth, prediction)})
    mismatches: list[str] = []
    for actual, expected in zip(reconstructed, prior["perInstance"], strict=True):
        if actual["id"] != expected["id"] or any(abs(actual[key] - expected[key]) > 1e-8 for key in ("iou", "boundaryIou", "boundaryF1")):
            mismatches.append(str(expected["id"]))
    after = materializer.verify(materialization_path)
    removed_after = guards.remove_ultralytics_label_caches(root)
    atexit.unregister(cleanup)
    if not after["ok"] or after["datasetFilesSha256"] != before["datasetFilesSha256"]:
        raise ValueError("ROI v2数据集后置重放失败")
    inputs = {"plan": {"path": str(plan_path), "sha256": sha256_file(plan_path)}, **plan["inputs"]}
    if mismatches:
        return {"schemaVersion": 1, "ok": False, "decision": "reconstruction_mismatch", "inputs": inputs,
                "reconstructionMismatchIds": mismatches, "datasetFilesSha256After": after["datasetFilesSha256"]}
    failed = [row for row in reconstructed if row["boundaryIou"] < 0.75 or row["boundaryF1"] < 0.9 or row["iou"] < 0.75]
    summary = {
        "reconstructedInstances": len(reconstructed), "jointFailures": len(failed),
        "strictBoundaryIouFailures": sum(row["boundaryIou"] < 0.75 for row in reconstructed),
        "twoPixelBoundaryF1Failures": sum(row["boundaryF1"] < 0.9 for row in reconstructed),
        "failedInstancesWithOracleJointPass": sum(bool(row["trainTruthAwareOracle"]["anyJointPass"]) for row in failed),
        "failedDisagreementPixels": sum(int(row["error"]["disagreementPixels"]) for row in failed),
        "failedDisagreementWithin2PxBoundary": sum(int(row["error"]["disagreementWithin2PxBoundary"]) for row in failed),
        "failedDisagreementWithin5PxBoundary": sum(int(row["error"]["disagreementWithin5PxBoundary"]) for row in failed),
        "failedDisagreementBeyond5PxBoundary": sum(int(row["error"]["disagreementBeyond5PxBoundary"]) for row in failed),
        "failedTruthTouchingCropBorder": sum(bool(row["error"]["truthTouchesCropBorder"]) for row in failed),
    }
    return {"schemaVersion": 1, "ok": True, "decision": "train_only_error_topology_diagnostic", "inputs": inputs,
            "scope": {"trainOnly": True, "valTestHoldoutRead": False, "optimizerSteps": 0,
                      "oracleMayBeUsedForModelSelection": False, "trainingUse": "prohibited"},
            "dataset": {"selectedTrainIds": selected_ids, "sourceGroups": 32, "datasetFilesSha256After": after["datasetFilesSha256"],
                        "removedCachesBefore": removed_before, "removedCachesAfter": removed_after},
            "summary": summary, "perInstance": reconstructed}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        recorded = json.loads(args.verify_report.read_text(encoding="utf-8"))
        current = compute(Path(recorded["inputs"]["plan"]["path"]))
        ok = current == recorded
        print(json.dumps({"ok": ok, "decision": "verified_error_topology" if ok else "reconstruction_mismatch",
                          "summary": current.get("summary")}, ensure_ascii=False))
        if not ok:
            raise SystemExit(1)
        return
    if not args.plan or not args.output:
        parser.error("--plan and --output are required")
    if args.output.exists():
        raise FileExistsError(args.output)
    report = compute(args.plan)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": report["ok"], "decision": report["decision"], "summary": report.get("summary")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
