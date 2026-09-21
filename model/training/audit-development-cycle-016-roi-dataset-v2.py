#!/usr/bin/env python3
"""终审循环016 ROI验证真值v2的278个实例与物化字节。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image


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
        raise RuntimeError(f"无法加载模块：{file_name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def audit(materialization_report_path: Path, output_path: Path) -> dict[str, Any]:
    if output_path.exists():
        raise ValueError(f"输出已存在，禁止覆盖：{output_path}")
    materializer = load_module("materialize-development-cycle-016-roi-dataset-v2.py", "cycle016_roi_v2")
    materialized = materializer.verify(materialization_report_path)
    dataset_report = json.loads(materialization_report_path.read_text(encoding="utf-8"))
    plan_path = Path(dataset_report["inputs"]["plan"]["path"])
    plan = materializer.validate_plan(plan_path)
    manifest, final_items, source_report, audit_state = materializer.collect_truth(plan)
    frozen_sam = json.loads(Path(plan["inputs"]["frozenSamReview"]["path"]).read_text(encoding="utf-8"))
    residual_report = json.loads(Path(plan["inputs"]["manualResidualWorkspaceReport"]["path"]).read_text(encoding="utf-8"))
    editor = json.loads(Path(residual_report["editorData"]["path"]).read_text(encoding="utf-8"))
    manual = json.loads(Path(plan["inputs"]["manualResidualDecisions"]["path"]).read_text(encoding="utf-8"))
    retain_ids = {row["id"] for row in manifest["items"] if row["action"] == "retain" and row["originalVerdict"] == "pass"}
    sam_ids = {row["id"] for row in frozen_sam["records"] if row["verdict"] == "accept_sam"}
    manual_ids = {row["id"] for row in editor["items"] if manual[row["id"]]["status"] == "reviewed_pass"}
    final_ids = {row["id"] for row in final_items}
    approved_ids = retain_ids | sam_ids | manual_ids
    if len(retain_ids) != 221 or len(sam_ids) != 36 or len(manual_ids) != 21 or approved_ids != final_ids:
        raise ValueError("278实例视觉裁决身份未闭合")
    dataset_root = Path(dataset_report["outputDir"])
    dataset_manifest = json.loads(Path(dataset_report["manifest"]["path"]).read_text(encoding="utf-8"))
    val_records = {row["id"]: row for row in dataset_manifest["records"] if row["split"] == "val"}
    source_root = Path(source_report["outputDir"])
    source_by_key = {(row["fileName"], row["sourceGroup"]): row for row in source_report["records"]}
    crop_scale = float(dataset_report["contract"]["cropScale"])
    size = int(dataset_report["contract"]["size"])
    roi_v1 = materializer.load_module("materialize-development-cycle-016-roi-dataset.py", "cycle016_roi_v1_audit")
    rebuilt = 0
    for item in final_items:
        stem = f"{Path(item['sourceFileName']).stem}__nail-{int(item['truthIndex']):02d}"
        row = val_records.get(stem)
        if row is None:
            raise ValueError(f"v2 manifest缺少实例：{stem}")
        source_row = source_by_key[(item["sourceFileName"], item["sourceGroup"])]
        with Image.open(source_root / source_row["image"]) as opened:
            image = np.asarray(opened.convert("RGB"))
        height, width = image.shape[:2]
        pixels = np.asarray([[p["x"], p["y"]] for p in item["polygonPixels"]], dtype=np.float32)
        normalized = pixels / np.asarray([width, height], dtype=np.float32)
        x1, y1, x2, y2 = roi_v1.crop_box(normalized, width, height, crop_scale)
        if row["cropBox"] != [x1, y1, x2, y2]:
            raise ValueError(f"cropBox重建不一致：{stem}")
        crop = cv2.resize(image[y1:y2, x1:x2], (size, size), interpolation=cv2.INTER_LANCZOS4)
        local = pixels - np.asarray([x1, y1], dtype=np.float32)
        mask = np.zeros((y2 - y1, x2 - x1), dtype=np.uint8)
        cv2.fillPoly(mask, [np.rint(local).astype(np.int32)], 255)
        mask = cv2.resize(mask, (size, size), interpolation=cv2.INTER_NEAREST)
        image_out, mask_out = dataset_root / row["image"], dataset_root / row["mask"]
        with Image.open(image_out) as opened:
            actual_image = np.asarray(opened.convert("RGB"))
        with Image.open(mask_out) as opened:
            actual_mask = np.asarray(opened.convert("L"))
        # JPEG编码有损，图像以物化哈希验证；mask必须逐像素同构。
        if not np.array_equal(mask, actual_mask) or actual_image.shape != crop.shape:
            raise ValueError(f"ROI mask或图像尺寸重建不一致：{stem}")
        rebuilt += 1
    if rebuilt != 278 or audit_state["overlaps"]:
        raise ValueError("278实例字节重建或零交叠门失败")
    report = {
        "schemaVersion": 1, "ok": True, "decision": "roi_validation_truth_v2_full_review_pass",
        "scope": {"developmentModelSelectionEligible": True, "formalCalibrationTestOrHoldoutEligible": False, "testOrHoldoutRead": False, "trainingUse": "validation_only_not_training_examples"},
        "inputs": {
            "materializationReport": {"path": str(materialization_report_path), "sha256": sha256_file(materialization_report_path)},
            "plan": {"path": str(plan_path), "sha256": sha256_file(plan_path)},
            "datasetFilesSha256": dataset_report["datasetFilesSha256"],
        },
        "counts": {"reviewedInstances": 278, "frozenRetainedPass": 221, "samVisualPass": 36, "manualVisualPass": 21, "rebuiltRoiMasks": rebuilt, "validPolygons": 278, "sameImagePairwiseOverlapCount": 0, "valPositiveImages": 49, "valSourceGroups": 20, "trainValSourceGroupOverlap": 0},
        "correctedPriorAssumption": plan["correctedPriorAssumption"],
        "materializationVerification": materialized,
        "errors": [],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def verify(report_path: Path) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    materialization_path = Path(report["inputs"]["materializationReport"]["path"])
    if sha256_file(materialization_path) != report["inputs"]["materializationReport"]["sha256"]:
        raise ValueError("终审输入物化报告哈希漂移")
    materializer = load_module("materialize-development-cycle-016-roi-dataset-v2.py", "cycle016_roi_v2_verify")
    verified = materializer.verify(materialization_path)
    counts = report["counts"]
    if report.get("decision") != "roi_validation_truth_v2_full_review_pass" or counts["reviewedInstances"] != 278 or counts["rebuiltRoiMasks"] != 278 or counts["sameImagePairwiseOverlapCount"] != 0 or counts["trainValSourceGroupOverlap"] != 0:
        raise ValueError("终审报告门值异常")
    return {"ok": True, "decision": "verified_roi_validation_truth_v2_full_review_pass", "counts": counts, "datasetFilesSha256": verified["datasetFilesSha256"], "reportSha256": sha256_file(report_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--materialization-report")
    parser.add_argument("--output")
    parser.add_argument("--verify-report")
    args = parser.parse_args()
    if args.verify_report:
        print(json.dumps(verify(Path(args.verify_report).resolve()), ensure_ascii=False))
        return 0
    if not args.materialization_report or not args.output:
        raise ValueError("终审模式需要--materialization-report与--output")
    report = audit(Path(args.materialization_report).resolve(), Path(args.output).resolve())
    print(json.dumps({"ok": report["ok"], "decision": report["decision"], "counts": report["counts"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
