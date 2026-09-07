#!/usr/bin/env python3
"""仅用train图像与真值几何构建来源组原子的困难正样本重采样计划。"""

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
from PIL import Image, ImageDraw, ImageFilter


MAX_ANALYSIS_SIDE = 512
REPEAT_FACTOR = 2
FEATURE_WEIGHTS = {
    "lowContrast": 0.25,
    "smallMask": 0.20,
    "elongatedMask": 0.15,
    "adjacentMasks": 0.15,
    "manyMasks": 0.15,
    "backgroundComplexity": 0.10,
}


def load_materializer():
    path = Path(__file__).with_name("materialize-source-group-development-dataset.py")
    spec = importlib.util.spec_from_file_location("development_materializer", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"不能加载开发数据物化器：{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MATERIALIZER = load_materializer()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def atomic_write_new(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise ValueError(f"输出已存在，禁止覆盖：{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.tmp-", dir=path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def parse_polygons(label_path: Path) -> list[list[tuple[float, float]]]:
    polygons: list[list[tuple[float, float]]] = []
    for number, raw in enumerate(label_path.read_text(encoding="utf-8").splitlines(), 1):
        values = raw.split()
        if len(values) < 7 or values[0] != "0" or (len(values) - 1) % 2:
            raise ValueError(f"YOLO polygon无效：{label_path}:{number}")
        coordinates = [float(value) for value in values[1:]]
        if any(value < 0 or value > 1 for value in coordinates):
            raise ValueError(f"YOLO polygon坐标越界：{label_path}:{number}")
        polygons.append(list(zip(coordinates[0::2], coordinates[1::2])))
    return polygons


def polygon_mask(size: tuple[int, int], polygon: list[tuple[float, float]]) -> np.ndarray:
    width, height = size
    points = [
        (min(width - 1, max(0, round(x * width))), min(height - 1, max(0, round(y * height))))
        for x, y in polygon
    ]
    canvas = Image.new("L", size, 0)
    ImageDraw.Draw(canvas).polygon(points, fill=255)
    return np.asarray(canvas, dtype=np.uint8) > 0


def analyze_record(root: Path, record: dict[str, Any]) -> dict[str, Any]:
    image_path = root / str(record["image"])
    label_path = root / str(record["label"])
    if sha256_file(image_path) != record["imageSha256"]:
        raise ValueError(f"训练图片哈希漂移：{image_path}")
    if sha256_file(label_path) != record["labelSha256"]:
        raise ValueError(f"训练标签哈希漂移：{label_path}")
    polygons = parse_polygons(label_path)
    if len(polygons) != record["maskCount"]:
        raise ValueError(f"训练标签mask数不一致：{record['fileName']}")
    with Image.open(image_path) as source:
        source.load()
        rgb_source = source.convert("RGB")
    scale = min(1.0, MAX_ANALYSIS_SIDE / max(rgb_source.size))
    size = tuple(max(1, round(value * scale)) for value in rgb_source.size)
    rgb_image = rgb_source.resize(size, Image.Resampling.BILINEAR)
    rgb = np.asarray(rgb_image, dtype=np.float32) / 255.0
    masks = [polygon_mask(size, polygon) for polygon in polygons]
    union = np.logical_or.reduce(masks)
    area_fractions: list[float] = []
    aspect_ratios: list[float] = []
    contrasts: list[float] = []
    centers: list[tuple[float, float, float]] = []
    for mask in masks:
        ys, xs = np.nonzero(mask)
        if len(xs) < 4:
            raise ValueError(f"训练mask退化：{record['fileName']}")
        area = float(mask.mean())
        box_width = int(xs.max() - xs.min() + 1)
        box_height = int(ys.max() - ys.min() + 1)
        aspect = max(box_width, box_height) / max(1, min(box_width, box_height))
        mask_image = Image.fromarray(mask.astype(np.uint8) * 255, mode="L")
        dilated = np.asarray(mask_image.filter(ImageFilter.MaxFilter(5))) > 0
        eroded = np.asarray(mask_image.filter(ImageFilter.MinFilter(5))) > 0
        outer_ring = dilated & ~mask
        inner_ring = mask & ~eroded
        if not outer_ring.any() or not inner_ring.any():
            contrast = 1.0
        else:
            contrast = float(
                np.abs(rgb[inner_ring].mean(axis=0) - rgb[outer_ring].mean(axis=0)).mean()
            )
        area_fractions.append(area)
        aspect_ratios.append(aspect)
        contrasts.append(contrast)
        centers.append((float(xs.mean()), float(ys.mean()), float(np.sqrt(len(xs)))))
    adjacency = 0.0
    if len(centers) > 1:
        normalized_distances = []
        for index, first in enumerate(centers):
            for second in centers[index + 1 :]:
                distance = np.hypot(first[0] - second[0], first[1] - second[1])
                normalized_distances.append(float(distance / max(1.0, first[2] + second[2])))
        adjacency = clamp((1.75 - min(normalized_distances)) / 1.25)
    grayscale = rgb.mean(axis=2)
    gradient = np.zeros_like(grayscale)
    gradient[:, 1:] += np.abs(grayscale[:, 1:] - grayscale[:, :-1])
    gradient[1:, :] += np.abs(grayscale[1:, :] - grayscale[:-1, :])
    outside = ~union
    edge_density = float((gradient[outside] > 0.10).mean()) if outside.any() else 0.0
    median_area = float(np.median(area_fractions))
    median_aspect = float(np.median(aspect_ratios))
    median_contrast = float(np.median(contrasts))
    features = {
        "lowContrast": clamp((0.12 - median_contrast) / 0.10),
        "smallMask": clamp((0.006 - median_area) / 0.005),
        "elongatedMask": clamp((median_aspect - 2.0) / 2.0),
        "adjacentMasks": adjacency,
        "manyMasks": clamp((len(masks) - 5) / 5),
        "backgroundComplexity": clamp((edge_density - 0.08) / 0.12),
    }
    score = sum(features[name] * weight for name, weight in FEATURE_WEIGHTS.items())
    return {
        "fileName": record["fileName"],
        "imageSha256": record["imageSha256"],
        "labelSha256": record["labelSha256"],
        "sourceGroup": record["sourceGroup"],
        "maskCount": len(masks),
        "analysisSize": list(size),
        "medianMaskAreaFraction": round(median_area, 8),
        "medianMaskAspectRatio": round(median_aspect, 8),
        "medianBoundaryContrast": round(median_contrast, 8),
        "backgroundEdgeDensity": round(edge_density, 8),
        "featureScores": {name: round(value, 8) for name, value in features.items()},
        "difficultyScore": round(score, 8),
    }


def build_report(
    materialization_report_path: Path,
    target_minimum_images: int,
    maximum_source_groups: int,
) -> dict[str, Any]:
    if target_minimum_images < 1 or maximum_source_groups < 1:
        raise ValueError("选择数量参数必须为正数")
    materialization = MATERIALIZER.verify_report(materialization_report_path)
    root = Path(materialization["outputDir"]).resolve()
    train_records = [
        item
        for item in materialization["records"]
        if item["developmentSplit"] == "train"
        and item["role"] == "train-positive"
        and item.get("isResampledCopy") is not True
    ]
    if len(train_records) != 263:
        raise ValueError("困难度审计只接受固定开发折的263张唯一train正样本")
    metrics = [analyze_record(root, item) for item in train_records]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in metrics:
        grouped.setdefault(item["sourceGroup"], []).append(item)
    group_metrics = []
    for source_group, items in grouped.items():
        scores = [item["difficultyScore"] for item in items]
        group_metrics.append(
            {
                "sourceGroup": source_group,
                "imageCount": len(items),
                "maskCount": sum(item["maskCount"] for item in items),
                "meanDifficultyScore": round(float(np.mean(scores)), 8),
                "maximumDifficultyScore": round(max(scores), 8),
                "groupDifficultyScore": round(0.4 * float(np.mean(scores)) + 0.6 * max(scores), 8),
                "recordIdentitiesSha256": canonical_sha256(
                    [
                        {
                            "fileName": item["fileName"],
                            "imageSha256": item["imageSha256"],
                            "labelSha256": item["labelSha256"],
                        }
                        for item in sorted(items, key=lambda value: value["fileName"])
                    ]
                ),
            }
        )
    group_metrics.sort(key=lambda item: (-item["groupDifficultyScore"], item["sourceGroup"]))
    selected = []
    selected_images = 0
    for item in group_metrics:
        if len(selected) >= maximum_source_groups:
            break
        selected.append(item)
        selected_images += item["imageCount"]
        if selected_images >= target_minimum_images:
            break
    if selected_images < target_minimum_images:
        raise ValueError("来源组上限内无法达到目标困难正样本数量")
    report = {
        "schemaVersion": 1,
        "ok": True,
        "decision": "approved_train_internal_positive_resampling_selection",
        "trainingUse": "development-experiment-only",
        "selectionBasis": "train-images-and-ground-truth-only-no-model-predictions",
        "inputs": {
            "developmentMaterializationReport": {
                "path": str(materialization_report_path),
                "sha256": sha256_file(materialization_report_path),
                "recordsSha256": materialization["recordsSha256"],
                "datasetFilesSha256": materialization["datasetFilesSha256"],
            }
        },
        "policy": {
            "maximumAnalysisSide": MAX_ANALYSIS_SIDE,
            "featureWeights": FEATURE_WEIGHTS,
            "groupAggregation": "0.4*meanDifficultyScore+0.6*maximumDifficultyScore",
            "targetMinimumImages": target_minimum_images,
            "maximumSourceGroups": maximum_source_groups,
            "sourceGroupAtomic": True,
            "repeatFactor": REPEAT_FACTOR,
            "forbiddenInputs": [
                "development-evaluation-predictions",
                "old-val30",
                "old-test100",
                "release-holdout",
            ],
        },
        "expectedBaseTrainingPositiveImages": len(train_records),
        "selectedSourceGroups": sorted(item["sourceGroup"] for item in selected),
        "expectedSelectedUniqueImages": selected_images,
        "repeatFactor": REPEAT_FACTOR,
        "expectedResampledPositiveCopies": selected_images,
        "selectedGroupMetrics": selected,
        "allGroupMetrics": group_metrics,
        "recordsSha256": canonical_sha256(metrics),
        "records": sorted(metrics, key=lambda item: item["fileName"]),
        "invariants": {
            "onlyTrainPositiveRecordsRead": True,
            "modelPredictionsRead": False,
            "evaluationImagesAnalyzed": False,
            "oldValidationTestOrHoldoutRead": False,
            "sourceGroupAtomic": True,
        },
        "errors": [],
    }
    report["contentSha256"] = canonical_sha256(report)
    return report


def verify_report(path: Path) -> dict[str, Any]:
    report = json.loads(path.read_text(encoding="utf-8"))
    if (
        report.get("schemaVersion") != 1
        or report.get("ok") is not True
        or report.get("decision")
        != "approved_train_internal_positive_resampling_selection"
        or report.get("trainingUse") != "development-experiment-only"
        or report.get("errors") not in (None, [])
    ):
        raise ValueError("困难正样本重采样报告顶层合同无效")
    binding = report["inputs"]["developmentMaterializationReport"]
    input_path = Path(binding["path"]).resolve()
    if sha256_file(input_path) != binding["sha256"]:
        raise ValueError("困难正样本审计输入报告哈希漂移")
    replayed = build_report(
        input_path,
        int(report["policy"]["targetMinimumImages"]),
        int(report["policy"]["maximumSourceGroups"]),
    )
    if replayed != report:
        raise ValueError("困难正样本重采样报告无法确定性重放")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development-materialization-report", type=Path)
    parser.add_argument("--target-minimum-images", type=int, default=60)
    parser.add_argument("--maximum-source-groups", type=int, default=25)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report is not None:
        if args.development_materialization_report is not None or args.output is not None:
            raise ValueError("--verify-report不能与构建参数并用")
        report = verify_report(args.verify_report.resolve())
    else:
        if args.development_materialization_report is None or args.output is None:
            raise ValueError("构建必须提供输入物化报告和输出路径")
        report = build_report(
            args.development_materialization_report.resolve(),
            args.target_minimum_images,
            args.maximum_source_groups,
        )
        atomic_write_new(args.output.resolve(), report)
        verify_report(args.output.resolve())
    print(
        json.dumps(
            {
                "ok": True,
                "decision": report["decision"],
                "selectedSourceGroups": len(report["selectedSourceGroups"]),
                "selectedImages": report["expectedSelectedUniqueImages"],
                "contentSha256": report["contentSha256"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
