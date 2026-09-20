#!/usr/bin/env python3
"""为 cycle016 验证真值 v2 的57个冻结返修实例构建一次性SAM2.1-L提示。"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import OrderedDict
from pathlib import Path
from typing import Any

import cv2
import numpy as np


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized(value: float, extent: int) -> float:
    return round(min(1.0, max(0.0, value / extent)), 6)


def prompt_from_polygon(
    raw: list[dict[str, Any]], width: int, height: int, padding: float
) -> tuple[list[float], list[list[float]], list[list[float]]]:
    points = np.asarray([[float(row["x"]), float(row["y"])] for row in raw], dtype=np.float64)
    if len(points) < 4 or not np.isfinite(points).all():
        raise ValueError("原polygon少于4点或含非有限坐标")
    x1, y1 = np.floor(points.min(axis=0)).astype(int)
    x2, y2 = np.ceil(points.max(axis=0)).astype(int)
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(width - 1, x2), min(height - 1, y2)
    local = np.rint(points - np.asarray([x1, y1])).astype(np.int32)
    mask = np.zeros((y2 - y1 + 1, x2 - x1 + 1), dtype=np.uint8)
    cv2.fillPoly(mask, [local], 1)
    ys, xs = np.nonzero(mask)
    if len(xs) < 16:
        raise ValueError("原polygon前景过小")
    foreground = np.column_stack((xs + x1, ys + y1)).astype(np.float64)
    center = foreground.mean(axis=0)
    covariance = np.cov(foreground - center, rowvar=False)
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    axis = eigenvectors[:, int(np.argmax(eigenvalues))]
    projections = (foreground - center) @ axis
    orthogonal = foreground - center - np.outer(projections, axis)
    orthogonal_sq = np.square(orthogonal).sum(axis=1)
    span = max(1.0, float(np.ptp(projections)))
    targets = [0.0, float(np.quantile(projections, 0.25)), float(np.quantile(projections, 0.75))]
    positive_pixels = []
    for target in targets:
        score = np.square((projections - target) / span) + orthogonal_sq / (span * span)
        positive_pixels.append(foreground[int(np.argmin(score))])
    pad_x = (x2 - x1 + 1) * padding
    pad_y = (y2 - y1 + 1) * padding
    bx1, by1 = max(0.0, x1 - pad_x), max(0.0, y1 - pad_y)
    bx2, by2 = min(float(width - 1), x2 + pad_x), min(float(height - 1), y2 + pad_y)
    inset_x = max(1.0, (bx2 - bx1) * 0.02)
    inset_y = max(1.0, (by2 - by1) * 0.02)
    box = [normalized(bx1, width), normalized(by1, height), normalized(bx2, width), normalized(by2, height)]
    positives = [[normalized(p[0], width), normalized(p[1], height)] for p in positive_pixels]
    negatives = [
        [normalized(bx1 + inset_x, width), normalized(by1 + inset_y, height)],
        [normalized(bx2 - inset_x, width), normalized(by1 + inset_y, height)],
        [normalized(bx1 + inset_x, width), normalized(by2 - inset_y, height)],
        [normalized(bx2 - inset_x, width), normalized(by2 - inset_y, height)],
    ]
    return box, positives, negatives


def load_inputs(plan_path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    pairs = (
        ("workspaceReport", "workspaceReportSha256"),
        ("editorData", "editorDataSha256"),
        ("finalReviewReport", "finalReviewReportSha256"),
        ("samModel", "samModelSha256"),
    )
    for name, hash_name in pairs:
        if sha256_file(Path(plan["inputs"][name])) != plan["inputs"][hash_name]:
            raise ValueError(f"计划输入哈希不匹配：{name}")
    editor = json.loads(Path(plan["inputs"]["editorData"]).read_text(encoding="utf-8"))
    review = json.loads(Path(plan["inputs"]["finalReviewReport"]).read_text(encoding="utf-8"))
    if len(editor["items"]) != int(plan["expected"]["repairInstances"]):
        raise ValueError("返修实例数不匹配")
    return plan, editor, review


def build(plan_path: Path, output: Path) -> dict[str, Any]:
    if output.exists():
        raise ValueError(f"输出已存在，禁止覆盖：{output}")
    plan, editor, review = load_inputs(plan_path)
    decision_by_id = {row["id"]: row for row in review["decisions"]}
    groups: OrderedDict[tuple[str, str], list[dict[str, Any]]] = OrderedDict()
    for item in editor["items"]:
        if item["status"] != "pending_original_resolution_manual_repair":
            raise ValueError(f"返修工作区状态漂移：{item['id']}")
        groups.setdefault((item["sourceFileName"], item["sourceGroup"]), []).append(item)
    if len(groups) != int(plan["expected"]["sourceImages"]):
        raise ValueError("返修源图数不匹配")
    padding = float(plan["promptContract"]["boxPadding"])
    source_dir = Path(plan["inputs"]["sourceImageDir"])
    images = []
    for (file_name, source_group), items in groups.items():
        source_path = source_dir / file_name
        if not source_path.is_file():
            raise ValueError(f"缺少源图：{file_name}")
        if sha256_file(source_path) != items[0]["sourceImageSha256"]:
            raise ValueError(f"源图哈希不匹配：{file_name}")
        boxes, positives, negatives = [], [], []
        for item in items:
            box, positive, negative = prompt_from_polygon(
                item["originalPolygon"], int(item["imageWidth"]), int(item["imageHeight"]), padding
            )
            boxes.append(box); positives.append(positive); negatives.append(negative)
        images.append({
            "fileName": file_name,
            "sha256": items[0]["sourceImageSha256"],
            "sourceGroup": source_group,
            "repairIds": [item["id"] for item in items],
            "truthIndices": [item["truthIndex"] for item in items],
            "originalVerdicts": [item["originalVerdict"] for item in items],
            "issueCodes": [item["issueCodes"] for item in items],
            "reviewRegions": [decision_by_id[item["id"]]["regions"] for item in items],
            "reviewNotes": [decision_by_id[item["id"]]["notes"] for item in items],
            "boxes": boxes,
            "positivePoints": positives,
            "negativePoints": negatives,
            "promptModes": [plan["promptContract"]["promptMode"]] * len(items),
        })
    report = {
        "schemaVersion": 1,
        "decision": "single_sam21_large_repair_candidates_only",
        "trainingUse": "prohibited",
        "originalResolutionReviewRequired": True,
        "formalPromotionAllowed": False,
        "inputs": {
            "plan": {"path": str(plan_path), "sha256": sha256_file(plan_path)},
            "workspaceReport": {"path": plan["inputs"]["workspaceReport"], "sha256": plan["inputs"]["workspaceReportSha256"]},
            "editorData": {"path": plan["inputs"]["editorData"], "sha256": plan["inputs"]["editorDataSha256"]},
            "finalReviewReport": {"path": plan["inputs"]["finalReviewReport"], "sha256": plan["inputs"]["finalReviewReportSha256"]},
            "samModel": {"path": plan["inputs"]["samModel"], "sha256": plan["inputs"]["samModelSha256"]},
        },
        "settings": plan["promptContract"],
        "imageCount": len(images),
        "promptCount": sum(len(row["boxes"]) for row in images),
        "images": images,
        "stopLoss": plan["acceptance"]["stopLoss"],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def verify(path: Path) -> dict[str, Any]:
    report = json.loads(path.read_text(encoding="utf-8"))
    for name, binding in report["inputs"].items():
        if sha256_file(Path(binding["path"])) != binding["sha256"]:
            raise ValueError(f"提示输入哈希不匹配：{name}")
    ids = [item for image in report["images"] for item in image["repairIds"]]
    if report["imageCount"] != 25 or report["promptCount"] != 57 or len(ids) != len(set(ids)):
        raise ValueError("提示覆盖数量或身份不一致")
    if report["trainingUse"] != "prohibited" or not report["originalResolutionReviewRequired"]:
        raise ValueError("提示角色或视觉复核门漂移")
    return {"ok": True, "decision": "verified_sam_repair_prompts", "imageCount": report["imageCount"], "promptCount": report["promptCount"], "reportSha256": sha256_file(path)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan")
    parser.add_argument("--output")
    parser.add_argument("--verify-report")
    args = parser.parse_args()
    if args.verify_report:
        print(json.dumps(verify(Path(args.verify_report).resolve()), ensure_ascii=False))
        return 0
    if not args.plan or not args.output:
        raise ValueError("构建模式需要--plan和--output")
    report = build(Path(args.plan).resolve(), Path(args.output).resolve())
    print(json.dumps({"ok": True, "decision": report["decision"], "imageCount": report["imageCount"], "promptCount": report["promptCount"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
