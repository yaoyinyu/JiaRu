#!/usr/bin/env python3
"""从哈希绑定YOLO粗polygon生成PCA长轴多点SAM候选提示。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np


WORKSPACE_DECISION = "development_cycle_015_generated_annotation_workspace_ready_candidate_only"
PRELABEL_DECISION = "candidate_only_not_training_truth"
OUTPUT_DECISION = "sam_candidate_only_not_training_truth"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_object(path: Path, label: str) -> dict[str, Any]:
    path = path.resolve()
    if not path.is_file():
        raise ValueError(f"{label}不存在：{path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label}不是JSON对象")
    return value


def normalized(value: float, extent: float) -> float:
    return round(min(1.0, max(0.0, value / extent)), 6)


def build_prompt_for_polygon(
    polygon: list[dict[str, Any]], width: int, height: int, box_padding: float,
) -> tuple[list[float], list[list[float]], list[list[float]]]:
    points = np.asarray([[float(point["x"]), float(point["y"])] for point in polygon], dtype=np.float64)
    if len(points) < 4 or not np.isfinite(points).all():
        raise ValueError("候选polygon少于4点或包含非有限坐标")
    x1, y1 = np.floor(points.min(axis=0)).astype(int)
    x2, y2 = np.ceil(points.max(axis=0)).astype(int)
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(width - 1, x2), min(height - 1, y2)
    if x2 <= x1 or y2 <= y1:
        raise ValueError("候选polygon外接框无效")

    local = np.rint(points - np.asarray([x1, y1])).astype(np.int32)
    mask = np.zeros((y2 - y1 + 1, x2 - x1 + 1), dtype=np.uint8)
    cv2.fillPoly(mask, [local], 1)
    ys, xs = np.nonzero(mask)
    if len(xs) < 16:
        raise ValueError("候选polygon前景像素过少")
    foreground = np.column_stack((xs + x1, ys + y1)).astype(np.float64)
    center = foreground.mean(axis=0)
    covariance = np.cov(foreground - center, rowvar=False)
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    axis = eigenvectors[:, int(np.argmax(eigenvalues))]
    projections = (foreground - center) @ axis
    targets = [0.0, float(np.quantile(projections, 0.25)), float(np.quantile(projections, 0.75))]
    positive_pixels: list[np.ndarray] = []
    orthogonal = foreground - center - np.outer(projections, axis)
    orthogonal_sq = np.square(orthogonal).sum(axis=1)
    projection_span = max(1.0, float(np.ptp(projections)))
    for target in targets:
        score = np.square((projections - target) / projection_span) + orthogonal_sq / (projection_span ** 2)
        positive_pixels.append(foreground[int(np.argmin(score))])

    span_x, span_y = x2 - x1 + 1, y2 - y1 + 1
    pad_x, pad_y = span_x * box_padding, span_y * box_padding
    bx1, by1 = max(0.0, x1 - pad_x), max(0.0, y1 - pad_y)
    bx2, by2 = min(float(width - 1), x2 + pad_x), min(float(height - 1), y2 + pad_y)
    inset_x, inset_y = max(1.0, (bx2 - bx1) * 0.02), max(1.0, (by2 - by1) * 0.02)
    box = [normalized(bx1, width), normalized(by1, height), normalized(bx2, width), normalized(by2, height)]
    positives = [[normalized(point[0], width), normalized(point[1], height)] for point in positive_pixels]
    negatives = [
        [normalized(bx1 + inset_x, width), normalized(by1 + inset_y, height)],
        [normalized(bx2 - inset_x, width), normalized(by1 + inset_y, height)],
        [normalized(bx1 + inset_x, width), normalized(by2 - inset_y, height)],
        [normalized(bx2 - inset_x, width), normalized(by2 - inset_y, height)],
    ]
    return box, positives, negatives


def build_document(
    workspace_path: Path, prelabel_path: Path, box_padding: float, max_overprediction_trim: int,
) -> dict[str, Any]:
    workspace_path, prelabel_path = workspace_path.resolve(), prelabel_path.resolve()
    workspace = read_object(workspace_path, "标注工作区")
    prelabel = read_object(prelabel_path, "YOLO预标注报告")
    if (
        workspace.get("ok") is not True
        or workspace.get("decision") != WORKSPACE_DECISION
        or workspace.get("trainingUse") != "prohibited"
    ):
        raise ValueError("标注工作区合同无效")
    if (
        prelabel.get("ok") is not True
        or prelabel.get("decision") != PRELABEL_DECISION
        or prelabel.get("trainingUse") != "prohibited"
        or Path(str(prelabel.get("workspaceManifest") or "")).resolve() != workspace_path
        or prelabel.get("workspaceManifestSha256") != sha256_file(workspace_path)
    ):
        raise ValueError("YOLO预标注报告未绑定当前工作区")
    by_name = {str(item["fileName"]): item for item in workspace.get("items") or []}
    if len(by_name) != len(workspace.get("items") or []):
        raise ValueError("工作区文件名为空或重复")
    images: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    trimmed_count = 0
    for report_item in prelabel.get("items") or []:
        name = str(report_item.get("fileName") or "")
        workspace_item = by_name.get(name)
        if workspace_item is None or report_item.get("sha256") != workspace_item.get("sha256"):
            raise ValueError(f"预标注图片身份未绑定工作区：{name}")
        expected = int(workspace_item.get("expectedFullyVisibleNails") or 0)
        annotation_path = Path(str(report_item.get("annotationPath") or "")).resolve()
        annotation = read_object(annotation_path, f"{name}预标注")
        if (
            annotation.get("decision") != PRELABEL_DECISION
            or annotation.get("trainingUse") != "prohibited"
            or (annotation.get("image") or {}).get("fileName") != name
            or (annotation.get("image") or {}).get("sourceGroup") != workspace_item.get("sourceGroup")
        ):
            raise ValueError(f"预标注annotation合同漂移：{name}")
        candidates = annotation.get("annotations")
        if not isinstance(candidates, list) or len(candidates) != report_item.get("candidateCount"):
            raise ValueError(f"预标注候选计数漂移：{name}")
        excess = len(candidates) - expected
        if excess < 0 or excess > max_overprediction_trim:
            skipped.append({"fileName": name, "expected": expected, "candidates": len(candidates), "reason": "candidate_count_not_recoverable_by_bounded_overprediction_trim"})
            continue
        ranked = sorted(
            enumerate(candidates),
            key=lambda pair: (-float((pair[1].get("attributes") or {}).get("confidence") or 0.0), pair[0]),
        )[:expected]
        selected_indices = {index for index, _ in ranked}
        selected = [candidate for index, candidate in enumerate(candidates) if index in selected_indices]
        dropped = [
            {"sourceIndex": index + 1, "confidence": float((candidate.get("attributes") or {}).get("confidence") or 0.0)}
            for index, candidate in enumerate(candidates) if index not in selected_indices
        ]
        if dropped:
            trimmed_count += len(dropped)
        image = annotation.get("image") or {}
        width, height = int(image.get("width") or 0), int(image.get("height") or 0)
        if width < 1 or height < 1:
            raise ValueError(f"预标注图片尺寸无效：{name}")
        boxes, positives, negatives = [], [], []
        source_indices = []
        for original_index, candidate in enumerate(candidates, start=1):
            if original_index - 1 not in selected_indices:
                continue
            box, positive, negative = build_prompt_for_polygon(candidate.get("polygon") or [], width, height, box_padding)
            boxes.append(box); positives.append(positive); negatives.append(negative); source_indices.append(original_index)
        images.append({
            "fileName": name,
            "sha256": workspace_item["sha256"],
            "sourceGroup": workspace_item["sourceGroup"],
            "expectedFullyVisibleNails": expected,
            "sourceIndices": source_indices,
            "boxes": boxes,
            "positivePoints": positives,
            "negativePoints": negatives,
            "promptModes": ["center-negative-corners"] * len(boxes),
            "boundedOverpredictionTrim": {"applied": bool(dropped), "dropped": dropped},
        })
    return {
        "schemaVersion": 1,
        "source": "hash-bound YOLO coarse polygons with PCA long-axis internal multipoints",
        "decision": OUTPUT_DECISION,
        "inputs": {
            "workspace": {"path": str(workspace_path), "sha256": sha256_file(workspace_path)},
            "prelabel": {"path": str(prelabel_path), "sha256": sha256_file(prelabel_path)},
        },
        "settings": {"boxPadding": box_padding, "maxOverpredictionTrim": max_overprediction_trim},
        "imageCount": len(images),
        "promptCount": sum(len(image["boxes"]) for image in images),
        "trimmedOverpredictionCandidateCount": trimmed_count,
        "images": images,
        "skippedImages": skipped,
        "policy": {
            "rankTrimIsCandidateGenerationOnly": True,
            "failedOrDroppedYoloCandidatesRemainUnapproved": True,
            "samOutputStillRequiresOriginalResolutionPerNailReview": True,
            "trainingUse": "prohibited",
        },
        "trainingUse": "prohibited",
        "formalPromotionAllowed": False,
        "releaseState": "hold",
        "productState": "hold",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-manifest", required=True)
    parser.add_argument("--prelabel-report", required=True)
    parser.add_argument("--box-padding", type=float, default=0.15)
    parser.add_argument("--max-overprediction-trim", type=int, default=2)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if not 0 <= args.box_padding <= 0.3 or not 0 <= args.max_overprediction_trim <= 3:
        raise ValueError("box padding or bounded overprediction trim is outside the safe range")
    output = Path(args.output).resolve()
    if output.exists():
        raise ValueError(f"输出已存在，禁止覆盖：{output}")
    document = build_document(
        Path(args.workspace_manifest), Path(args.prelabel_report), args.box_padding, args.max_overprediction_trim
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: document[key] for key in ("decision", "imageCount", "promptCount", "trimmedOverpredictionCandidateCount")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
