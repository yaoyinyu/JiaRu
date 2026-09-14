#!/usr/bin/env python3
"""用真值几何、历史浏览器实测和训练墙钟验证循环014路线可达性与工期收益。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


CROPS = {
    "topLeft": (0.0, 0.0, 0.7, 0.7),
    "topRight": (0.3, 0.0, 1.0, 0.7),
    "bottomLeft": (0.0, 0.3, 0.7, 1.0),
    "bottomRight": (0.3, 0.3, 1.0, 1.0),
}
CONTEXT_RATIO = 0.20
DESKTOP_TARGET_MS = 800.0
MOBILE_TARGET_MS = 1500.0


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


def binding(path: Path) -> dict[str, str]:
    path = path.resolve()
    return {"path": str(path), "sha256": sha256_file(path)}


def parse_boxes(label_path: Path) -> list[tuple[float, float, float, float]]:
    boxes: list[tuple[float, float, float, float]] = []
    for line_number, line in enumerate(label_path.read_text(encoding="utf-8").splitlines(), start=1):
        parts = line.split()
        if len(parts) < 7 or (len(parts) - 1) % 2:
            raise ValueError(f"YOLO polygon格式无效：{label_path}:{line_number}")
        coordinates = [float(value) for value in parts[1:]]
        xs, ys = coordinates[0::2], coordinates[1::2]
        if any(value < 0 or value > 1 for value in coordinates):
            raise ValueError(f"YOLO polygon越界：{label_path}:{line_number}")
        boxes.append((min(xs), min(ys), max(xs), max(ys)))
    return boxes


def crop_covers(box: tuple[float, float, float, float], crop: tuple[float, float, float, float]) -> bool:
    x0, y0, x1, y1 = box
    crop_x0, crop_y0, crop_x1, crop_y1 = crop
    padding = CONTEXT_RATIO * max(x1 - x0, y1 - y0)
    return (
        x0 - padding >= crop_x0
        and y0 - padding >= crop_y0
        and x1 + padding <= crop_x1
        and y1 + padding <= crop_y1
    )


def analyze_geometry(materialization: dict[str, Any], quality: dict[str, Any]) -> dict[str, Any]:
    if materialization.get("counts", {}).get("evaluationPositiveImages") != 58 or materialization.get("counts", {}).get("evaluationPositiveMasks") != 354:
        raise ValueError("clean98物化分母漂移")
    summary = quality.get("summary", {})
    if (
        int(summary.get("truth", -1)) != 354
        or int(summary.get("missing", -1)) != 21
        or int(summary.get("missingImages", -1)) != 13
        or int(summary.get("predictions", -1)) != 348
    ):
        raise ValueError("clean98质量基线漂移")
    root = Path(str(materialization.get("outputDir") or "")).resolve()
    if not root.is_dir():
        raise ValueError(f"clean98物化根不存在：{root}")
    missing_by_stem = {
        str(row.get("stem")): {int(value) for value in row.get("missingTruthIndices") or []}
        for row in quality.get("images") or []
        if row.get("role") == "train-positive"
    }
    quality_by_stem = {
        str(row.get("stem")): row for row in quality.get("images") or []
        if row.get("role") == "train-positive"
    }
    truth_count = 0
    missing_count = 0
    all_crop_covered = 0
    missing_crop_covered = 0
    uncovered_truths: list[dict[str, Any]] = []
    uncovered_missing: list[dict[str, Any]] = []
    maximum_truths_per_image = 0
    records = [row for row in materialization.get("records") or [] if row.get("role") == "train-positive"]
    if len(records) != 58:
        raise ValueError("clean98正图记录数漂移")
    for record in records:
        stem = Path(str(record["fileName"])).stem
        label_path = (root / str(record["label"])).resolve()
        if not label_path.is_file() or sha256_file(label_path) != record.get("labelSha256"):
            raise ValueError(f"clean98标签缺失或哈希漂移：{stem}")
        boxes = parse_boxes(label_path)
        quality_row = quality_by_stem.get(stem)
        if not quality_row or int(quality_row.get("truthCount", -1)) != len(boxes):
            raise ValueError(f"clean98真值与质量报告不同构：{stem}")
        maximum_truths_per_image = max(maximum_truths_per_image, len(boxes))
        for truth_index, box in enumerate(boxes, start=1):
            truth_count += 1
            is_missing = truth_index in missing_by_stem.get(stem, set())
            if is_missing:
                missing_count += 1
            covered_by = [name for name, crop in CROPS.items() if crop_covers(box, crop)]
            if covered_by:
                all_crop_covered += 1
                if is_missing:
                    missing_crop_covered += 1
            else:
                item = {"stem": stem, "truthIndex": truth_index, "baselineMissing": is_missing}
                uncovered_truths.append(item)
                if is_missing:
                    uncovered_missing.append(item)
    if truth_count != 354 or missing_count != 21:
        raise ValueError("clean98标签重建分母漂移")
    return {
        "truthInstances": truth_count,
        "baselineMissingInstances": missing_count,
        "cropCoveredTruthInstances": all_crop_covered,
        "cropCoverageRate": round(all_crop_covered / truth_count, 8),
        "cropCoveredMissingInstances": missing_crop_covered,
        "missingCoverageRate": round(missing_crop_covered / missing_count, 8),
        "uncoveredTruths": uncovered_truths,
        "uncoveredMissingTruths": uncovered_missing,
        "maximumTruthsPerImage": maximum_truths_per_image,
        "effectiveLinearResolutionGain": round(1 / 0.7, 8),
    }


def analyze_runtime(performance: dict[str, Any]) -> dict[str, Any]:
    if performance.get("ok") is not True or performance.get("profile") != "desktop" or int(performance.get("totals", {}).get("samples", 0)) != 29:
        raise ValueError("历史桌面浏览器性能报告无效")
    stats = performance.get("stats", {})
    p95 = float(stats.get("p95Ms", -1))
    maximum = float(stats.get("maxMs", -1))
    if p95 != 133.7 or maximum != 159.5:
        raise ValueError("历史浏览器性能基线漂移")
    passes = 1 + len(CROPS)
    p95_projection = round(p95 * passes, 2)
    max_projection = round(maximum * passes, 2)
    return {
        "inferencePassesPerImage": passes,
        "historicalSinglePassP95Ms": p95,
        "historicalSinglePassMaxMs": maximum,
        "linearP95ProjectionMs": p95_projection,
        "linearMaxProjectionMs": max_projection,
        "desktopTargetMs": DESKTOP_TARGET_MS,
        "p95ProjectionHeadroomMs": round(DESKTOP_TARGET_MS - p95_projection, 2),
        "maxProjectionHeadroomMs": round(DESKTOP_TARGET_MS - max_projection, 2),
        "mobileTargetMs": MOBILE_TARGET_MS,
        "maximumAllowedMobilePerPassMs": round(MOBILE_TARGET_MS / passes, 2),
        "desktopBudgetProven": False,
        "mobileBudgetProven": False,
        "reason": "线性投影不包含裁剪、坐标映射、跨窗口去重与设备差异；最坏投影只剩2.5ms，必须实测。",
    }


def analyze_schedule(throughput: dict[str, Any], capacity: dict[str, Any]) -> dict[str, Any]:
    reference = throughput.get("referenceRun", {})
    lever = next((row for row in throughput.get("levers") or [] if row.get("change") == "workers: 0 -> 8"), None)
    if not lever or float(reference.get("totalSeconds", -1)) != 490.815:
        raise ValueError("训练吞吐报告缺少workers=8基线")
    projected = float(lever.get("projectedCycle012TotalSeconds", -1))
    saved_seconds = round(float(reference["totalSeconds"]) - projected, 3)
    supply = capacity.get("minimumNewPositiveSupply", {})
    required = int(supply.get("extendCleanDevelopmentTo352PlusReleaseReserve", -1))
    remaining = int(supply.get("remainingAfterCandidateOnlyUpperBound", -1))
    if required != 424 or remaining != 414:
        raise ValueError("正图容量缺口漂移")
    scenarios = [
        {
            "reviewedPositiveImagesPerDay": rate,
            "daysForRemaining414": round(remaining / rate, 2),
        }
        for rate in (10, 25, 50, 100)
    ]
    return {
        "workers8SavingPer12EpochRunSeconds": saved_seconds,
        "workers8SavingPer12EpochRunMinutes": round(saved_seconds / 60, 2),
        "workers8SpeedupPercent": float(lever.get("projectedSpeedupPercent")),
        "minimumNewPositiveImages": required,
        "remainingAfterKnownCandidateUpperBound": remaining,
        "reviewThroughputScenarios": scenarios,
        "criticalPath": "source-isolated acquisition and original-resolution mask review",
        "conclusion": "workers=8真实缩短GPU墙钟，但单次只省约1.72分钟；数据并行化决定日历工期。",
    }


def build(paths: dict[str, Path]) -> dict[str, Any]:
    documents = {key: read_object(path, key) for key, path in paths.items()}
    capacity = documents["capacityAudit"]
    if capacity.get("decision") != "cycle014_positive_capacity_insufficient_start_parallel_acquisition_and_review":
        raise ValueError("循环014容量审计状态无效")
    geometry = analyze_geometry(documents["cleanMaterialization"], documents["cleanQuality"])
    runtime = analyze_runtime(documents["browserPerformance"])
    schedule = analyze_schedule(documents["trainingThroughput"], capacity)
    geometry_reachable = (
        geometry["cropCoveredMissingInstances"] == geometry["baselineMissingInstances"]
        and geometry["maximumTruthsPerImage"] <= 10
    )
    perfect = {
        "matched": 354,
        "completeMasks": 354,
        "missing": 0,
        "missingImages": 0,
        "weightedSpuriousNumerator": 0.0,
        "instanceRecall": 1.0,
        "completeMaskRatio": 1.0,
        "missingImageRate": 0.0,
        "weightedSpuriousRate": 0.0,
        "assumption": "全图保留既有正确结果，裁片模型对覆盖真值完美输出，跨窗口去重完美且不新增误检。",
    }
    decision = (
        "geometrically_reachable_runtime_conditional_quality_unproven_require_no_training_pilot"
        if geometry_reachable
        else "unreachable_by_fixed_multicrop_geometry"
    )
    return {
        "schemaVersion": 1,
        "ok": geometry_reachable,
        "decision": decision,
        "analysisKind": "development_cycle_014_zero_inference_route_viability",
        "readImagePixels": False,
        "runTraining": False,
        "runInference": False,
        "inputs": {key: binding(path) for key, path in paths.items()},
        "routeContract": {
            "baselinePass": "one full-image 512 letterbox inference",
            "fixedFallbackCrops": {name: list(crop) for name, crop in CROPS.items()},
            "cropSideRatio": 0.7,
            "minimumContextRatioToTruthBoundingBoxMaximumSide": CONTEXT_RATIO,
            "mediaPipeRole": "optional crop selection optimization only; never required for correctness and never counted as a mask",
            "onlyPixelSegmentationModelMasksCount": True,
            "maximumMergedCandidatesPerImage": 10,
        },
        "geometry": geometry,
        "perfectOutputCeiling": perfect,
        "runtime": runtime,
        "schedule": schedule,
        "validationConclusion": {
            "technicallyReasonable": True,
            "trainingAllowed": False,
            "formalPromotionAllowed": False,
            "provenToImproveQuality": False,
            "provenToMeetDesktopBudget": False,
            "provenToMeetMobileBudget": False,
            "provenToShortenEndToEndReleaseSchedule": False,
            "provenTrainingWallClockReduction": True,
            "nextRequiredEvidence": "implement a no-training, fixed-weight multicrop pilot on development-only data and measure actual quality plus browser P95 before any training",
        },
        "releaseState": "hold",
        "productState": "hold",
        "errors": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("capacity-audit", "clean-materialization", "clean-quality", "browser-performance", "training-throughput"):
        parser.add_argument(f"--{key}")
    parser.add_argument("--output")
    parser.add_argument("--verify-report")
    args = parser.parse_args()
    argument_keys = {
        "capacityAudit": "capacity_audit",
        "cleanMaterialization": "clean_materialization",
        "cleanQuality": "clean_quality",
        "browserPerformance": "browser_performance",
        "trainingThroughput": "training_throughput",
    }
    if args.verify_report:
        report_path = Path(args.verify_report).resolve()
        existing = read_object(report_path, "待重放路线可行性报告")
        replay = build({key: Path(existing["inputs"][key]["path"]) for key in argument_keys})
        if replay != existing:
            raise ValueError("路线可行性报告与当前证据深重放不一致")
        print(json.dumps({"ok": True, "decision": existing["decision"], "reportSha256": sha256_file(report_path)}, ensure_ascii=False))
        return 0
    raw = {key: getattr(args, attribute) for key, attribute in argument_keys.items()}
    if any(value is None for value in (*raw.values(), args.output)):
        raise ValueError("构建模式缺少必填参数")
    output = Path(args.output).resolve()
    if output.exists():
        raise ValueError(f"输出已存在，禁止覆盖：{output}")
    payload = build({key: Path(value) for key, value in raw.items()})
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": payload["ok"], "decision": payload["decision"], "runtime": payload["runtime"], "schedule": payload["schedule"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
