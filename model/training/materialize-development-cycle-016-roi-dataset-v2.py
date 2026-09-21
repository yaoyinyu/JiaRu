#!/usr/bin/env python3
"""冻结57个返修polygon并物化循环016 ROI验证真值v2。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image
from shapely.geometry import Polygon


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


def aggregate_files(root: Path) -> tuple[str, int]:
    entries = []
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        entries.append(f"{path.relative_to(root).as_posix()}\t{sha256_file(path)}")
    return hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest(), len(entries)


def parse_label(path: Path) -> list[np.ndarray]:
    result = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        tokens = line.split()
        if not tokens:
            continue
        if len(tokens) < 7 or (len(tokens) - 1) % 2:
            raise ValueError(f"非法YOLO标签：{path}:{line_number}")
        result.append(np.asarray([float(value) for value in tokens[1:]], dtype=np.float64).reshape(-1, 2))
    return result


def validate_plan(plan_path: Path) -> dict[str, Any]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    for name, binding in plan["inputs"].items():
        path = Path(binding["path"])
        if not path.is_file() or sha256_file(path) != binding["sha256"]:
            raise ValueError(f"计划输入不存在或哈希漂移：{name}")
    expected = plan["expected"]
    if expected["totalReplacements"] != expected["samAcceptedReplacements"] + expected["manualReplacements"]:
        raise ValueError("计划替换数不闭合")
    if expected["v2Instances"] != expected["totalReplacements"] + expected["retainedInstances"]:
        raise ValueError("计划v2实例数不闭合")
    return plan


def collect_truth(plan: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    base = json.loads(Path(plan["inputs"]["baseWorkspaceReport"]["path"]).read_text(encoding="utf-8"))
    base_plan = json.loads(Path(base["inputs"]["plan"]["path"]).read_text(encoding="utf-8"))
    manifest = json.loads(Path(base_plan["inputs"]["correctionManifest"]).read_text(encoding="utf-8"))
    source_report = json.loads(Path(base_plan["inputs"]["cycle012DatasetReport"]).read_text(encoding="utf-8"))
    residual_report = json.loads(Path(plan["inputs"]["manualResidualWorkspaceReport"]["path"]).read_text(encoding="utf-8"))
    editor_path = Path(residual_report["editorData"]["path"])
    accepted_path = Path(residual_report["acceptedSamCandidates"]["path"])
    if sha256_file(editor_path) != residual_report["editorData"]["sha256"] or sha256_file(accepted_path) != residual_report["acceptedSamCandidates"]["sha256"]:
        raise ValueError("残项工作区子文件哈希漂移")
    editor = json.loads(editor_path.read_text(encoding="utf-8"))
    accepted = json.loads(accepted_path.read_text(encoding="utf-8"))
    manual = json.loads(Path(plan["inputs"]["manualResidualDecisions"]["path"]).read_text(encoding="utf-8"))
    manual_ids = [row["id"] for row in editor["items"]]
    if set(manual) != set(manual_ids) or any(manual[item_id].get("status") != "reviewed_pass" for item_id in manual_ids):
        raise ValueError("人工残项裁决未21/21闭合")
    replacements: dict[str, dict[str, Any]] = {}
    for row in accepted["items"]:
        replacements[row["id"]] = {"source": "single_sam_visual_accept", "polygon": row["candidatePolygon"]}
    for item_id in manual_ids:
        replacements[item_id] = {"source": "manual_original_resolution_reviewed_pass", "polygon": manual[item_id]["candidatePolygon"]}
    if len(replacements) != int(plan["expected"]["totalReplacements"]):
        raise ValueError("替换polygon数量不一致")
    source_root = Path(source_report["outputDir"])
    source_by_key = {(row["fileName"], row["sourceGroup"]): row for row in source_report["records"]}
    final_items = []
    groups = set()
    by_file: dict[str, list[tuple[str, Polygon]]] = {}
    for item in manifest["items"]:
        if item["action"] == "exclude_source_image":
            continue
        row = source_by_key[(item["sourceFileName"], item["sourceGroup"])]
        image_path, label_path = source_root / row["image"], source_root / row["label"]
        if sha256_file(image_path) != row["imageSha256"] or sha256_file(label_path) != row["labelSha256"]:
            raise ValueError(f"源图或标签哈希漂移：{item['id']}")
        with Image.open(image_path) as opened:
            width, height = opened.size
        if item["action"] == "repair_polygon":
            replacement = replacements.get(item["id"])
            if replacement is None:
                raise ValueError(f"缺少替换polygon：{item['id']}")
            pixels = np.asarray([[float(p["x"]), float(p["y"])] for p in replacement["polygon"]], dtype=np.float64)
            origin = replacement["source"]
        else:
            polygons = parse_label(label_path)
            pixels = polygons[int(item["truthIndex"]) - 1] * np.asarray([width, height], dtype=np.float64)
            origin = "frozen_retained_truth"
        shape = Polygon(pixels)
        if not shape.is_valid or shape.area <= 1 or not np.isfinite(pixels).all():
            raise ValueError(f"polygon非法：{item['id']}")
        if np.any(pixels[:, 0] < 0) or np.any(pixels[:, 0] >= width) or np.any(pixels[:, 1] < 0) or np.any(pixels[:, 1] >= height):
            raise ValueError(f"polygon越出原图：{item['id']}")
        by_file.setdefault(item["sourceFileName"], []).append((item["id"], shape))
        groups.add(item["sourceGroup"])
        final_items.append({**item, "polygonOrigin": origin, "polygonPixels": [{"x": round(float(x), 4), "y": round(float(y), 4)} for x, y in pixels], "imageWidth": width, "imageHeight": height})
    overlaps = []
    for file_name, rows in by_file.items():
        for index, (left_id, left) in enumerate(rows):
            for right_id, right in rows[index + 1:]:
                area = left.intersection(right).area
                if area > 1e-6:
                    overlaps.append({"fileName": file_name, "left": left_id, "right": right_id, "areaPixels": round(area, 6)})
    if overlaps:
        raise ValueError(f"同图polygon发生交叠：{overlaps[:3]}")
    expected = plan["expected"]
    if len(final_items) != expected["v2Instances"] or len(by_file) != expected["v2PositiveImages"] or len(groups) != expected["v2SourceGroups"]:
        raise ValueError(f"v2计数不一致：instances={len(final_items)} images={len(by_file)} groups={len(groups)}")
    return manifest, final_items, source_report, {"sourceGroups": sorted(groups), "overlaps": overlaps, "replacements": replacements}


def materialize(plan_path: Path, output: Path, crop_scale: float = 1.6, size: int = 384) -> dict[str, Any]:
    if output.exists():
        raise ValueError(f"输出目录已存在，禁止覆盖：{output}")
    report_path = output.parent / f"{output.name}-materialization-report.json"
    if report_path.exists():
        raise ValueError(f"输出报告已存在，禁止覆盖：{report_path}")
    plan = validate_plan(plan_path)
    manifest, final_items, source_report, audit = collect_truth(plan)
    roi_v1_report = json.loads(Path(plan["inputs"]["roiDatasetV1Report"]["path"]).read_text(encoding="utf-8"))
    roi_v1_root = Path(roi_v1_report["outputDir"])
    roi_v1_manifest = json.loads(Path(roi_v1_report["manifest"]["path"]).read_text(encoding="utf-8"))
    source_root = Path(source_report["outputDir"])
    source_by_key = {(row["fileName"], row["sourceGroup"]): row for row in source_report["records"]}
    roi_module = load_module("materialize-development-cycle-016-roi-dataset.py", "cycle016_roi_v1")
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.tmp-", dir=output.parent))
    records = []
    try:
        for row in roi_v1_manifest["records"]:
            if row["split"] != "train":
                continue
            image_src, mask_src = roi_v1_root / row["image"], roi_v1_root / row["mask"]
            if sha256_file(image_src) != row["imageSha256"] or sha256_file(mask_src) != row["maskSha256"]:
                raise ValueError(f"v1 train ROI哈希漂移：{row['id']}")
            image_dst, mask_dst = temporary / row["image"], temporary / row["mask"]
            image_dst.parent.mkdir(parents=True, exist_ok=True); mask_dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(image_src, image_dst); shutil.copyfile(mask_src, mask_dst)
            records.append(dict(row))
        for item in final_items:
            source_row = source_by_key[(item["sourceFileName"], item["sourceGroup"])]
            image_path = source_root / source_row["image"]
            with Image.open(image_path) as opened:
                image = np.asarray(opened.convert("RGB"))
            height, width = image.shape[:2]
            pixels = np.asarray([[p["x"], p["y"]] for p in item["polygonPixels"]], dtype=np.float32)
            normalized = pixels / np.asarray([width, height], dtype=np.float32)
            x1, y1, x2, y2 = roi_module.crop_box(normalized, width, height, crop_scale)
            crop = image[y1:y2, x1:x2]
            local = pixels - np.asarray([x1, y1], dtype=np.float32)
            mask = np.zeros((y2 - y1, x2 - x1), dtype=np.uint8)
            cv2.fillPoly(mask, [np.rint(local).astype(np.int32)], 255)
            crop_resized = cv2.resize(crop, (size, size), interpolation=cv2.INTER_LANCZOS4)
            mask_resized = cv2.resize(mask, (size, size), interpolation=cv2.INTER_NEAREST)
            stem = f"{Path(item['sourceFileName']).stem}__nail-{int(item['truthIndex']):02d}"
            image_rel, mask_rel = f"images/val/{stem}.jpg", f"masks/val/{stem}.png"
            image_out, mask_out = temporary / image_rel, temporary / mask_rel
            image_out.parent.mkdir(parents=True, exist_ok=True); mask_out.parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray(crop_resized).save(image_out, format="JPEG", quality=95, subsampling=0)
            Image.fromarray(mask_resized).save(mask_out, format="PNG", optimize=True)
            records.append({"id": stem, "split": "val", "sourceFileName": item["sourceFileName"], "sourceGroup": item["sourceGroup"], "truthIndex": item["truthIndex"], "cropBox": [x1, y1, x2, y2], "polygonOrigin": item["polygonOrigin"], "image": image_rel, "mask": mask_rel, "imageSha256": sha256_file(image_out), "maskSha256": sha256_file(mask_out)})
        manifest_out = temporary / "manifest.json"
        manifest_out.write_text(json.dumps({"schemaVersion": 2, "records": records}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, output)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    train_groups = sorted({row["sourceGroup"] for row in records if row["split"] == "train"})
    val_groups = sorted({row["sourceGroup"] for row in records if row["split"] == "val"})
    overlap = sorted(set(train_groups) & set(val_groups))
    if overlap:
        raise ValueError(f"train/val sourceGroup交叠：{overlap}")
    aggregate, file_count = aggregate_files(output)
    report = {
        "schemaVersion": 2, "ok": True, "decision": "roi_validation_truth_v2_materialized_pending_full_original_resolution_review",
        "scope": {"trainingRoleOnly": True, "formalCalibrationTestOrHoldoutEligible": False, "testOrHoldoutRead": False, "trainingUse": "prohibited_until_278_of_278_original_resolution_review_pass"},
        "inputs": {"plan": {"path": str(plan_path), "sha256": sha256_file(plan_path)}, **plan["inputs"]},
        "contract": {"cropScale": crop_scale, "size": size, "splitSalt": roi_v1_report["contract"]["splitSalt"]},
        "outputDir": str(output),
        "counts": {"instances": len(records), "trainInstances": sum(row["split"] == "train" for row in records), "valInstances": sum(row["split"] == "val" for row in records), "trainSourceGroups": len(train_groups), "valSourceGroups": len(val_groups), "samAcceptedReplacements": plan["expected"]["samAcceptedReplacements"], "manualReplacements": plan["expected"]["manualReplacements"], "retainedValInstances": plan["expected"]["retainedInstances"], "excludedValInstances": plan["expected"]["excludedInstances"]},
        "sourceGroups": {"train": train_groups, "val": val_groups, "overlap": overlap},
        "truthAudit": {"validPolygons": len(final_items), "sameImagePairwiseOverlapCount": len(audit["overlaps"]), "v2PositiveImages": plan["expected"]["v2PositiveImages"], "correctedPriorSourceGroupCount": plan["correctedPriorAssumption"]},
        "datasetFilesSha256": aggregate, "datasetFileCount": file_count,
        "manifest": {"path": str(output / "manifest.json"), "sha256": sha256_file(output / "manifest.json")},
        "errors": [],
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def verify(report_path: Path) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    for name, binding in report["inputs"].items():
        if name == "plan":
            path, expected = Path(binding["path"]), binding["sha256"]
        else:
            path, expected = Path(binding["path"]), binding["sha256"]
        if not path.is_file() or sha256_file(path) != expected:
            raise ValueError(f"v2报告输入哈希漂移：{name}")
    plan = validate_plan(Path(report["inputs"]["plan"]["path"]))
    _, final_items, _, audit = collect_truth(plan)
    output = Path(report["outputDir"])
    aggregate, file_count = aggregate_files(output)
    if aggregate != report["datasetFilesSha256"] or file_count != report["datasetFileCount"]:
        raise ValueError("v2 ROI数据集文件聚合哈希漂移")
    manifest = json.loads(Path(report["manifest"]["path"]).read_text(encoding="utf-8"))
    records = manifest["records"]
    train_groups = {row["sourceGroup"] for row in records if row["split"] == "train"}
    val_groups = {row["sourceGroup"] for row in records if row["split"] == "val"}
    if train_groups & val_groups or len(final_items) != 278 or len([row for row in records if row["split"] == "val"]) != 278 or audit["overlaps"]:
        raise ValueError("v2 ROI验证真值不满足数量、隔离或零交叠门")
    for row in records:
        if sha256_file(output / row["image"]) != row["imageSha256"] or sha256_file(output / row["mask"]) != row["maskSha256"]:
            raise ValueError(f"v2 ROI资产哈希漂移：{row['id']}")
    return {"ok": True, "decision": "verified_roi_validation_truth_v2_pending_visual_review", "counts": report["counts"], "datasetFilesSha256": aggregate, "reportSha256": sha256_file(report_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan")
    parser.add_argument("--output-dir")
    parser.add_argument("--verify-report")
    args = parser.parse_args()
    if args.verify_report:
        print(json.dumps(verify(Path(args.verify_report).resolve()), ensure_ascii=False))
        return 0
    if not args.plan or not args.output_dir:
        raise ValueError("物化模式需要--plan与--output-dir")
    plan_path, output = Path(args.plan).resolve(), Path(args.output_dir).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    guards = load_module("train-yolo-seg.py", "cycle016_v2_guard")
    guards.install_read_only_ultralytics_image_check()
    plan = validate_plan(plan_path)
    base = json.loads(Path(plan["inputs"]["baseWorkspaceReport"]["path"]).read_text(encoding="utf-8"))
    base_plan = json.loads(Path(base["inputs"]["plan"]["path"]).read_text(encoding="utf-8"))
    source_report = json.loads(Path(base_plan["inputs"]["cycle012DatasetReport"]).read_text(encoding="utf-8"))
    source_root = Path(source_report["outputDir"])
    guards.remove_ultralytics_label_caches(source_root)
    try:
        report = materialize(plan_path, output)
    finally:
        guards.remove_ultralytics_label_caches(source_root)
    print(json.dumps({"ok": report["ok"], "decision": report["decision"], "counts": report["counts"], "datasetFilesSha256": report["datasetFilesSha256"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
