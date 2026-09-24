#!/usr/bin/env python3
"""重建循环016固定32例train原图/ROI审核包；不自动批准视觉真值。"""

from __future__ import annotations

import argparse
import atexit
import hashlib
import importlib.util
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw
from shapely.geometry import Polygon


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def module(name: str):
    path = Path(__file__).resolve().with_name(name)
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载：{path}")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def bound_json(binding: dict) -> dict:
    path = Path(binding["path"])
    if not path.is_file() or digest(path) != binding["sha256"]:
        raise ValueError(f"输入哈希漂移：{path}")
    return json.loads(path.read_text(encoding="utf-8"))


def polygon_lines(label: Path) -> list[np.ndarray]:
    polygons = []
    for line in label.read_text(encoding="utf-8").splitlines():
        tokens = line.split()
        if not tokens:
            continue
        if len(tokens) < 7 or (len(tokens) - 1) % 2:
            raise ValueError(f"非法源标签：{label}")
        polygons.append(np.asarray([float(value) for value in tokens[1:]], dtype=np.float32).reshape(-1, 2))
    return polygons


def load_context(plan_path: Path):
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if (Path(plan["builderSource"]["path"]).resolve() != Path(__file__).resolve() or
            digest(Path(__file__).resolve()) != plan["builderSource"]["sha256"]):
        raise ValueError("审核包构建器哈希漂移")
    for name, binding in plan["inputs"].items():
        bound_json(binding)
    previous = bound_json(plan["inputs"]["baselineMicrofitReport"])
    candidate = bound_json(plan["inputs"]["candidateMicrofitReport"])
    roi_report = bound_json(plan["inputs"]["roiMaterializationReport"])
    roi_manifest = bound_json(plan["inputs"]["roiManifest"])
    roi_v1 = bound_json(plan["inputs"]["roiV1MaterializationReport"])
    source_report = bound_json(plan["inputs"]["cycle012MaterializationReport"])
    identities = plan["selectedTrainIds"]
    if (len(identities) != 32 or len(set(identities)) != 32 or
            identities != previous["dataset"]["selectedTrainIds"] or
            identities != candidate["dataset"]["selectedTrainIds"] or
            [row["id"] for row in previous["perInstance"]] != identities or
            [row["id"] for row in candidate["perInstance"]] != identities):
        raise ValueError("固定32例或两份报告不逐例同构")
    if (previous["decision"] != "soft_boundary_iou_train_only_microfit_fail_no_full_pilot" or
            candidate["decision"] != "boundary_weight_train_only_microfit_fail_no_full_pilot" or
            previous["completedOptimizerSteps"] != 256 or candidate["completedOptimizerSteps"] != 256):
        raise ValueError("两份冻结失败身份不符")
    if (roi_report["datasetFilesSha256"] != plan["roiDatasetFilesSha256"] or
            roi_report["manifest"]["sha256"] != plan["inputs"]["roiManifest"]["sha256"] or
            roi_v1["inputs"]["cycle012MaterializationReport"] != plan["inputs"]["cycle012MaterializationReport"] or
            roi_v1["contract"]["cropScale"] != 1.6 or roi_v1["contract"]["size"] != 384):
        raise ValueError("ROI/源数据冻结身份漂移")
    return plan, previous, candidate, roi_report, roi_manifest, source_report


def build(plan_path: Path, output: Path) -> dict:
    if output.exists():
        raise FileExistsError(output)
    plan, previous, candidate, roi_report, roi_manifest, source_report = load_context(plan_path)
    source_root, roi_root = Path(source_report["outputDir"]), Path(roi_report["outputDir"])
    guards = module("train-yolo-seg.py")
    guards.install_read_only_ultralytics_image_check()
    def cleanup():
        guards.remove_ultralytics_label_caches(source_root)
        guards.remove_ultralytics_label_caches(roi_root)
    cleanup()
    atexit.register(cleanup)
    cycle012 = module("materialize-development-cycle-012-dataset.py")
    roi_v2 = module("materialize-development-cycle-016-roi-dataset-v2.py")
    roi_v1 = module("materialize-development-cycle-016-roi-dataset.py")
    cycle012.verify_report(Path(plan["inputs"]["cycle012MaterializationReport"]["path"]))
    if not roi_v2.verify(Path(plan["inputs"]["roiMaterializationReport"]["path"]))["ok"]:
        raise ValueError("ROI v2重放失败")
    by_roi = {row["id"]: row for row in roi_manifest["records"] if row["split"] == "train"}
    by_source = {(row["fileName"], row["sourceGroup"]): row for row in source_report["records"]}
    before = {"source": source_report["datasetFilesSha256"], "roi": roi_report["datasetFilesSha256"]}
    output.mkdir(parents=True)
    rows = []
    for index, (identity, old, new) in enumerate(zip(plan["selectedTrainIds"], previous["perInstance"], candidate["perInstance"], strict=True), start=1):
        roi = by_roi.get(identity)
        if roi is None or roi["id"] != old["id"] or roi["id"] != new["id"]:
            raise ValueError(f"ROI身份漂移：{identity}")
        source = by_source.get((roi["sourceFileName"], roi["sourceGroup"]))
        if source is None or source["developmentSplit"] != "train" or source["maskCount"] < roi["truthIndex"]:
            raise ValueError(f"源图或train角色不符：{identity}")
        image_path, label_path = source_root / source["image"], source_root / source["label"]
        roi_image, roi_mask = roi_root / roi["image"], roi_root / roi["mask"]
        for path, expected in ((image_path, source["imageSha256"]), (label_path, source["labelSha256"]),
                               (roi_image, roi["imageSha256"]), (roi_mask, roi["maskSha256"])):
            if digest(path) != expected:
                raise ValueError(f"资产哈希漂移：{identity}: {path}")
        with Image.open(image_path) as opened:
            source_image = np.asarray(opened.convert("RGB"))
        height, width = source_image.shape[:2]
        polygons = polygon_lines(label_path)
        if len(polygons) != source["maskCount"]:
            raise ValueError(f"源图mask数漂移：{identity}")
        normalized = polygons[roi["truthIndex"] - 1]
        pixels = normalized * np.asarray([width, height], dtype=np.float32)
        shape = Polygon(pixels)
        if not shape.is_valid or shape.area <= 1 or not np.isfinite(pixels).all():
            raise ValueError(f"源polygon非法：{identity}")
        bbox = roi_v1.crop_box(normalized, width, height, 1.6)
        if list(bbox) != roi["cropBox"]:
            raise ValueError(f"原分辨率cropBox不符：{identity}")
        x1, y1, x2, y2 = bbox
        crop = source_image[y1:y2, x1:x2]
        local = pixels - np.asarray([x1, y1], dtype=np.float32)
        mask = np.zeros((y2-y1, x2-x1), dtype=np.uint8)
        cv2.fillPoly(mask, [np.rint(local).astype(np.int32)], 255)
        with Image.open(roi_mask) as opened:
            frozen_mask = np.asarray(opened.convert("L"))
        reconstructed = cv2.resize(mask, (384, 384), interpolation=cv2.INTER_NEAREST)
        if not np.array_equal(reconstructed, frozen_mask):
            raise ValueError(f"384 mask逐像素重建失败：{identity}")
        with Image.open(roi_image) as opened:
            frozen_image = np.asarray(opened.convert("RGB"))
        temporary = output / f"{index:02d}-rebuild.jpg"
        Image.fromarray(cv2.resize(crop, (384, 384), interpolation=cv2.INTER_LANCZOS4)).save(
            temporary, format="JPEG", quality=95, subsampling=0)
        if digest(temporary) != roi["imageSha256"] or not np.array_equal(np.asarray(Image.open(temporary).convert("RGB")), frozen_image):
            raise ValueError(f"384 JPEG字节重建失败：{identity}")
        temporary.unlink()
        native_path = output / f"{index:02d}-native-overlay.png"
        overlay = Image.fromarray(crop.copy())
        canvas = Image.new("RGBA", overlay.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)
        vertices = [(float(x), float(y)) for x, y in local]
        draw.polygon(vertices, fill=(0, 255, 0, 45))
        draw.line(vertices + vertices[:1], fill=(255, 30, 20, 255), width=2)
        overlay = Image.alpha_composite(overlay.convert("RGBA"), canvas).convert("RGB")
        overlay.save(native_path, format="PNG")
        rows.append({
            "ordinal": index, "id": identity, "sourceGroup": roi["sourceGroup"],
            "sourceFileName": roi["sourceFileName"], "truthIndex": roi["truthIndex"],
            "sourceImage": {"path": str(image_path), "sha256": source["imageSha256"], "width": width, "height": height},
            "sourceLabel": {"path": str(label_path), "sha256": source["labelSha256"], "maskCount": source["maskCount"]},
            "cropBox": list(bbox), "polygonPixels": [[round(float(x), 4), round(float(y), 4)] for x, y in pixels],
            "nativeOverlay": {"path": str(native_path), "sha256": digest(native_path)},
            "roiImageSha256": roi["imageSha256"], "roiMaskSha256": roi["maskSha256"],
            "baseline": old, "candidate": new, "visualDecision": "pending_original_resolution_review",
        })
    cleanup()
    cycle012.verify_report(Path(plan["inputs"]["cycle012MaterializationReport"]["path"]))
    after_roi = roi_v2.verify(Path(plan["inputs"]["roiMaterializationReport"]["path"]))
    if before != {"source": source_report["datasetFilesSha256"], "roi": after_roi["datasetFilesSha256"]}:
        raise ValueError("审核后文件树身份漂移")
    result = {"schemaVersion": 1, "ok": True, "decision": "train_truth_review_workspace_pending_visual_decisions",
              "inputs": {"plan": {"path": str(plan_path), "sha256": digest(plan_path)}, **plan["inputs"]},
              "datasetFilesSha256": before, "count": len(rows), "records": rows,
              "visualApprovalCount": 0, "trainingUse": "unchanged", "testOrHoldoutRead": False, "errors": []}
    report_path = output / "workspace-report.json"
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    atexit.unregister(cleanup)
    return result


def verify(report_path: Path) -> dict:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    plan_path = Path(report["inputs"]["plan"]["path"])
    if digest(plan_path) != report["inputs"]["plan"]["sha256"]:
        raise ValueError("冻结计划哈希漂移")
    plan, previous, candidate, roi_report, roi_manifest, source_report = load_context(plan_path)
    if (report["count"] != 32 or report["visualApprovalCount"] != 0 or
            report["decision"] != "train_truth_review_workspace_pending_visual_decisions" or
            [row["id"] for row in report["records"]] != plan["selectedTrainIds"]):
        raise ValueError("审核包名单或待审状态漂移")
    source_root, roi_root = Path(source_report["outputDir"]), Path(roi_report["outputDir"])
    guards = module("train-yolo-seg.py")
    guards.install_read_only_ultralytics_image_check()
    guards.remove_ultralytics_label_caches(source_root)
    guards.remove_ultralytics_label_caches(roi_root)
    cycle012 = module("materialize-development-cycle-012-dataset.py")
    roi_v2 = module("materialize-development-cycle-016-roi-dataset-v2.py")
    cycle012.verify_report(Path(plan["inputs"]["cycle012MaterializationReport"]["path"]))
    integrity = roi_v2.verify(Path(plan["inputs"]["roiMaterializationReport"]["path"]))
    if report["datasetFilesSha256"] != {"source": source_report["datasetFilesSha256"], "roi": integrity["datasetFilesSha256"]}:
        raise ValueError("训练/ROI文件树身份漂移")
    by_roi = {row["id"]: row for row in roi_manifest["records"] if row["split"] == "train"}
    for index, row in enumerate(report["records"]):
        old, new = previous["perInstance"][index], candidate["perInstance"][index]
        roi = by_roi[row["id"]]
        if (row["ordinal"] != index + 1 or row["baseline"] != old or row["candidate"] != new or
                row["sourceGroup"] != roi["sourceGroup"] or row["cropBox"] != roi["cropBox"] or
                row["roiImageSha256"] != roi["imageSha256"] or row["roiMaskSha256"] != roi["maskSha256"] or
                row["visualDecision"] != "pending_original_resolution_review"):
            raise ValueError(f"审核行漂移：{row['id']}")
        for key in ("sourceImage", "sourceLabel", "nativeOverlay"):
            binding = row[key]
            if digest(Path(binding["path"])) != binding["sha256"]:
                raise ValueError(f"资产漂移：{row['id']} {key}")
    guards.remove_ultralytics_label_caches(source_root)
    guards.remove_ultralytics_label_caches(roi_root)
    return {"ok": True, "decision": "verified_train_truth_review_workspace_pending_visual_decisions", "count": 32,
            "datasetFilesSha256": report["datasetFilesSha256"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    result = verify(args.verify_report) if args.verify_report else build(args.plan, args.output)
    print(json.dumps({key: result[key] for key in ("ok", "decision", "count", "datasetFilesSha256")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
