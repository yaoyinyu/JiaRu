#!/usr/bin/env python3
"""以循环011冻结权重在clean98隔离副本上执行循环014固定四裁片零训练试验。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
ANALYZER_SOURCE = HERE / "analyze-development-cycle-013-candidate-ceiling.py"
MATERIALIZER_SOURCE = HERE / "materialize-clean-development-evaluation.py"
TRAINER_SOURCE = HERE / "train-yolo-seg.py"
EXPECTED_DECISION = "pre_registered_cycle014_no_training_fixed_weight_multicrop_pilot"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载模块：{path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ANALYZER = load_module("jiaru_cycle014_pilot_analyzer", ANALYZER_SOURCE)
MATERIALIZER = load_module("jiaru_cycle014_pilot_materializer", MATERIALIZER_SOURCE)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def read_object(path: Path, label: str) -> dict[str, Any]:
    path = path.resolve()
    if not path.is_file():
        raise ValueError(f"{label}不存在：{path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label}不是JSON对象")
    return value


def require_binding(value: Any, label: str) -> Path:
    if not isinstance(value, dict):
        raise ValueError(f"{label}绑定缺失")
    path = Path(str(value.get("path", ""))).resolve()
    if not path.is_file() or sha256_file(path) != value.get("sha256"):
        raise ValueError(f"{label}缺失或哈希漂移：{path}")
    return path


def normalized_crops(contract: dict[str, Any]) -> list[tuple[str, tuple[float, float, float, float]]]:
    raw = contract.get("fixedFallbackCrops")
    if not isinstance(raw, dict) or list(raw) != ["topLeft", "topRight", "bottomLeft", "bottomRight"]:
        raise ValueError("固定裁片名称或顺序漂移")
    crops: list[tuple[str, tuple[float, float, float, float]]] = []
    for name, values in raw.items():
        if not isinstance(values, list) or len(values) != 4:
            raise ValueError(f"裁片无效：{name}")
        crop = tuple(float(item) for item in values)
        if not (0 <= crop[0] < crop[2] <= 1 and 0 <= crop[1] < crop[3] <= 1):
            raise ValueError(f"裁片越界：{name}")
        crops.append((name, crop))
    expected = {
        "topLeft": (0.0, 0.0, 0.7, 0.7),
        "topRight": (0.3, 0.0, 1.0, 0.7),
        "bottomLeft": (0.0, 0.3, 0.7, 1.0),
        "bottomRight": (0.3, 0.3, 1.0, 1.0),
    }
    if dict(crops) != expected:
        raise ValueError("固定四裁片坐标漂移")
    return crops


def validate_plan(plan_path: Path) -> tuple[dict[str, Any], dict[str, Path]]:
    plan = read_object(plan_path, "循环014多裁片预注册计划")
    if (
        plan.get("schemaVersion") != 1
        or plan.get("decision") != EXPECTED_DECISION
        or plan.get("releaseState") != "hold"
        or plan.get("trainingAllowed") is not False
        or plan.get("formalPromotionAllowed") is not False
    ):
        raise ValueError("循环014多裁片计划顶层合同无效")
    inputs = plan.get("inputs", {})
    paths = {key: require_binding(inputs.get(key), key) for key in (
        "routeViability", "cleanMaterialization", "cleanQuality", "baselineArtifactIndex", "weights", "runner"
    )}
    if paths["runner"] != Path(__file__).resolve():
        raise ValueError("计划未绑定当前runner")
    viability = read_object(paths["routeViability"], "路线可行性报告")
    if (
        viability.get("decision") != "geometrically_reachable_runtime_conditional_quality_unproven_require_no_training_pilot"
        or viability.get("validationConclusion", {}).get("trainingAllowed") is not False
    ):
        raise ValueError("路线可行性报告不允许本试验")
    materialization = MATERIALIZER.verify_report(paths["cleanMaterialization"])
    quality = read_object(paths["cleanQuality"], "clean98冻结质量报告")
    if quality.get("summary", {}).get("truth") != 354 or quality.get("summary", {}).get("missing") != 21:
        raise ValueError("clean98冻结质量分母漂移")
    route = plan.get("routeContract", {})
    normalized_crops(route)
    if (
        route.get("inputSize") != 512
        or float(route.get("scoreThreshold", -1)) != 0.25
        or float(route.get("nmsIou", -1)) != 0.7
        or int(route.get("maximumDetectionsPerCrop", -1)) != 20
        or int(route.get("internalEdgeMarginPixels", -1)) != 3
        or int(route.get("maximumMergedCandidatesPerImage", -1)) != 10
        or route.get("reuseFrozenFullImagePredictions") is not True
        or route.get("runFullImageInferenceAgain") is not False
    ):
        raise ValueError("固定多裁片推理合同漂移")
    execution = plan.get("executionLock", {})
    if (
        execution.get("maximumCommandExecutions") != 1
        or execution.get("maximumModelLoads") != 1
        or execution.get("exactCropEvaluations") != 392
        or execution.get("allOutputsMustBeNew") is not True
        or execution.get("sourceDatasetReadOnly") is not True
    ):
        raise ValueError("循环014试验执行锁漂移")
    if materialization.get("counts", {}).get("evaluationImages") != 98:
        raise ValueError("clean98图数漂移")
    return plan, paths


def pixel_crop(crop: tuple[float, float, float, float], width: int, height: int) -> tuple[int, int, int, int]:
    left = round(crop[0] * width)
    top = round(crop[1] * height)
    right = round(crop[2] * width)
    bottom = round(crop[3] * height)
    if not (0 <= left < right <= width and 0 <= top < bottom <= height):
        raise ValueError("像素裁片无效")
    return left, top, right, bottom


def touches_internal_edge(
    points: Any,
    crop: tuple[int, int, int, int],
    image_size: tuple[int, int],
    margin: int,
) -> bool:
    import numpy as np

    left, top, right, bottom = crop
    width, height = image_size
    local_width, local_height = right - left, bottom - top
    minimum = np.asarray(points).min(axis=0)
    maximum = np.asarray(points).max(axis=0)
    return bool(
        (left > 0 and minimum[0] <= margin)
        or (top > 0 and minimum[1] <= margin)
        or (right < width and maximum[0] >= local_width - 1 - margin)
        or (bottom < height and maximum[1] >= local_height - 1 - margin)
    )


def baseline_inputs(paths: dict[str, Path]):
    return ANALYZER.load_evaluation_inputs(paths["cleanMaterialization"], paths["baselineArtifactIndex"])


def compact_result(result: dict[str, Any]) -> dict[str, Any]:
    return {"summary": result["summary"], "images": result["images"]}


def metric_gates(summary: dict[str, Any], floors: dict[str, Any]) -> dict[str, bool]:
    return {
        "instanceRecall": float(summary["instanceRecall"]) >= float(floors["minimumInstanceRecall"]),
        "completeMaskRatio": float(summary["completeMaskRatio"]) >= float(floors["minimumCompleteMaskRatio"]),
        "missingImageRate": float(summary["missingImageRate"]) <= float(floors["maximumMissingImageRate"]),
        "weightedSpuriousRate": float(summary["weightedSpuriousRate"]) <= float(floors["maximumWeightedSpuriousRate"]),
        "everyEvaluationImageAccountedFor": int(summary["evaluationImages"]) == 98,
    }


def compare(baseline: dict[str, Any], pilot: dict[str, Any], floors: dict[str, Any]) -> dict[str, Any]:
    base, current = baseline["summary"], pilot["summary"]
    gates = metric_gates(current, floors)
    deltas = {
        key: round(float(current[key]) - float(base[key]), 8)
        for key in ("instanceRecall", "completeMaskRatio", "missingImageRate", "weightedSpuriousRate", "directlyExtractableRate")
    }
    deltas.update({
        key: int(current[key]) - int(base[key])
        for key in ("matched", "completeMasks", "missing", "missingImages", "duplicates", "falsePositives", "invalidPredictionMasks")
    })
    no_regression = (
        int(current["matched"]) >= int(base["matched"])
        and int(current["completeMasks"]) >= int(base["completeMasks"])
        and float(current["weightedSpuriousRate"]) <= float(base["weightedSpuriousRate"])
    )
    return {
        "gates": gates,
        "allRequired": all(gates.values()),
        "qualityImprovementWithoutCoreRegression": (
            no_regression and (int(current["missing"]) < int(base["missing"]) or int(current["missingImages"]) < int(base["missingImages"]))
        ),
        "deltas": deltas,
    }


def load_merged_predictions(artifact_index: Path, expected_stems: set[str]) -> dict[str, Path | None]:
    artifact = read_object(artifact_index, "多裁片合并预测索引")
    records = artifact.get("predictionRecords")
    if not isinstance(records, list) or canonical_sha256(records) != artifact.get("predictionRecordsSha256"):
        raise ValueError("多裁片预测索引漂移")
    root = Path(str(artifact.get("artifactRoot", ""))).resolve()
    predictions: dict[str, Path | None] = {}
    for row in records:
        stem = str(row.get("stem", ""))
        relative = row.get("path")
        if relative is None:
            if row.get("sha256") is not None or row.get("predictionCount") != 0:
                raise ValueError(f"零预测记录无效：{stem}")
            predictions[stem] = None
        else:
            path = (root / str(relative)).resolve()
            path.relative_to(root)
            if not path.is_file() or sha256_file(path) != row.get("sha256"):
                raise ValueError(f"合并预测缺失或漂移：{stem}")
            predictions[stem] = path
    if set(predictions) != expected_stems:
        raise ValueError("合并预测未精确覆盖clean98")
    return predictions


def replay(plan_path: Path, report_path: Path) -> dict[str, Any]:
    plan, paths = validate_plan(plan_path)
    report = read_object(report_path, "循环014多裁片试验报告")
    artifact_index = require_binding(report.get("outputs", {}).get("mergedPredictionIndex"), "合并预测索引")
    dataset_root, by_stem, baseline_prediction_paths = baseline_inputs(paths)
    baseline = ANALYZER.reconstruct(dataset_root, by_stem, baseline_prediction_paths)
    fidelity = ANALYZER.check_fidelity(baseline, read_object(paths["cleanQuality"], "冻结质量报告"))
    if fidelity.get("ok") is not True:
        raise ValueError("冻结全图预测重建保真失败")
    merged_paths = load_merged_predictions(artifact_index, set(by_stem))
    pilot = ANALYZER.reconstruct(dataset_root, by_stem, merged_paths)
    comparison = compare(baseline, pilot, plan["qualityDecisionContract"])
    expected = {
        "baselineFidelity": fidelity,
        "baseline": compact_result(baseline),
        "pilot": compact_result(pilot),
        "comparison": comparison,
    }
    if report.get("replayableEvidence") != expected:
        raise ValueError("循环014多裁片试验报告深重放不一致")
    if report.get("contentSha256") != canonical_sha256({key: value for key, value in report.items() if key != "contentSha256"}):
        raise ValueError("循环014多裁片试验报告内容哈希漂移")
    return report


def execute(plan_path: Path, output: Path, device: str) -> dict[str, Any]:
    plan, paths = validate_plan(plan_path)
    output = output.resolve()
    expected_output = Path(str(plan["executionLock"]["outputReport"])).resolve()
    expected_root = Path(str(plan["executionLock"]["outputRoot"])).resolve()
    if output != expected_output or output.parent != expected_root or expected_root.exists():
        raise ValueError("输出路径不等于预注册全新根")
    source_report_before = MATERIALIZER.verify_report(paths["cleanMaterialization"])
    dataset_root, by_stem, baseline_prediction_paths = baseline_inputs(paths)
    baseline = ANALYZER.reconstruct(dataset_root, by_stem, baseline_prediction_paths)
    fidelity = ANALYZER.check_fidelity(baseline, read_object(paths["cleanQuality"], "冻结质量报告"))
    if fidelity.get("ok") is not True:
        raise ValueError("冻结全图预测重建保真失败，禁止推理")

    import cv2
    import numpy as np
    from PIL import Image, ImageOps
    from shapely.geometry import Polygon
    from ultralytics import YOLO

    trainer = load_module("jiaru_cycle014_read_only_guard", TRAINER_SOURCE)
    trainer.install_read_only_ultralytics_image_check()
    route = plan["routeContract"]
    crops = normalized_crops(route)
    staging = Path(tempfile.mkdtemp(prefix=f"{expected_root.name}-", dir=expected_root.parent))
    started = time.perf_counter()
    image_timings: list[float] = []
    edge_rejections = 0
    tile_candidates = 0
    crop_evaluations = 0
    try:
        runtime_images = staging / "runtime-images"
        label_root = staging / "merged-raw-labels"
        runtime_images.mkdir(parents=True)
        label_root.mkdir(parents=True)
        for stem, record in by_stem.items():
            source = (dataset_root / str(record["image"])).resolve()
            target = runtime_images / str(record["fileName"])
            shutil.copy2(source, target)
            if sha256_file(target) != record["imageSha256"]:
                raise ValueError(f"隔离副本哈希漂移：{stem}")
        model = YOLO(str(paths["weights"]))
        prediction_records: list[dict[str, Any]] = []
        for stem in sorted(by_stem):
            record = by_stem[stem]
            image_path = runtime_images / str(record["fileName"])
            with Image.open(image_path) as encoded:
                image = ImageOps.exif_transpose(encoded).convert("RGB")
            width, height = image.size
            pixel_crops = [(name, pixel_crop(crop, width, height)) for name, crop in crops]
            arrays = [
                cv2.cvtColor(np.asarray(image.crop(box)), cv2.COLOR_RGB2BGR)
                for _, box in pixel_crops
            ]
            image_started = time.perf_counter()
            results = model.predict(
                source=arrays,
                imgsz=int(route["inputSize"]),
                conf=float(route["scoreThreshold"]),
                iou=float(route["nmsIou"]),
                max_det=int(route["maximumDetectionsPerCrop"]),
                device=device,
                retina_masks=True,
                rect=False,
                verbose=False,
            )
            image_timings.append(time.perf_counter() - image_started)
            if len(results) != len(pixel_crops):
                raise ValueError(f"裁片预测数漂移：{stem}")
            crop_evaluations += len(results)
            lines = []
            baseline_path = baseline_prediction_paths[stem]
            if baseline_path is not None:
                lines.extend(line for line in baseline_path.read_text(encoding="utf-8").splitlines() if line.strip())
            for (_, box), result in zip(pixel_crops, results, strict=True):
                if result.boxes is None or result.masks is None:
                    continue
                scores = result.boxes.conf.detach().cpu().tolist()
                polygons = result.masks.xy
                if len(scores) != len(polygons):
                    raise ValueError(f"裁片box/mask数漂移：{stem}")
                for score, raw_points in zip(scores, polygons, strict=True):
                    points = np.asarray(raw_points, dtype=np.float64)
                    if points.ndim != 2 or len(points) < 3:
                        continue
                    if touches_internal_edge(points, box, (width, height), int(route["internalEdgeMarginPixels"])):
                        edge_rejections += 1
                        continue
                    translated = points + np.asarray([box[0], box[1]], dtype=np.float64)
                    polygon = Polygon([(float(x) / width, float(y) / height) for x, y in translated])
                    if not polygon.is_valid:
                        polygon = polygon.buffer(0)
                        if polygon.geom_type == "MultiPolygon":
                            polygon = max(polygon.geoms, key=lambda item: item.area)
                    if polygon.geom_type != "Polygon" or polygon.is_empty or polygon.area <= 0:
                        continue
                    coordinates = " ".join(
                        f"{value:.8f}" for point in polygon.exterior.coords[:-1] for value in point
                    )
                    lines.append(f"0 {coordinates} {float(score):.8f}")
                    tile_candidates += 1
            label_path = label_root / f"{stem}.txt"
            if lines:
                label_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
                prediction_records.append({
                    "stem": stem,
                    "path": label_path.relative_to(staging).as_posix(),
                    "sha256": sha256_file(label_path),
                    "predictionCount": len(lines),
                })
            else:
                prediction_records.append({"stem": stem, "path": None, "sha256": None, "predictionCount": 0})
        if crop_evaluations != int(plan["executionLock"]["exactCropEvaluations"]):
            raise ValueError("实际裁片评估数与执行锁不一致")
        artifact = {
            "schemaVersion": 1,
            "artifactRoot": str(expected_root),
            "predictionRecords": prediction_records,
            "predictionRecordsSha256": canonical_sha256(prediction_records),
        }
        artifact_path = staging / "merged-prediction-index.json"
        artifact_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        # 索引在原子换名后必须指向最终根，staging内文件相对路径保持不变。
        merged_paths = {
            row["stem"]: None if row["path"] is None else (staging / row["path"])
            for row in prediction_records
        }
        pilot = ANALYZER.reconstruct(dataset_root, by_stem, merged_paths)
        comparison = compare(baseline, pilot, plan["qualityDecisionContract"])
        source_report_after = MATERIALIZER.verify_report(paths["cleanMaterialization"])
        if source_report_before.get("datasetFilesSha256") != source_report_after.get("datasetFilesSha256"):
            raise ValueError("clean98证据数据集在试验中漂移")
        removed_caches = trainer.remove_ultralytics_label_caches(staging)
        elapsed = time.perf_counter() - started
        timings_ms = sorted(value * 1000 for value in image_timings)
        p95_index = max(0, min(len(timings_ms) - 1, int((len(timings_ms) * 0.95 + 0.999999)) - 1))
        decision = (
            "pilot_passes_development_quality_require_browser_runtime_validation"
            if comparison["allRequired"]
            else "pilot_fails_development_quality_close_fixed_multicrop_route"
        )
        report = {
            "schemaVersion": 1,
            "ok": True,
            "decision": decision,
            "diagnosticOnly": True,
            "trainingAllowed": False,
            "formalPromotionAllowed": False,
            "releaseState": "hold",
            "productState": "hold",
            "inputs": {
                "plan": {"path": str(plan_path.resolve()), "sha256": sha256_file(plan_path)},
                **{key: {"path": str(path), "sha256": sha256_file(path)} for key, path in paths.items()},
            },
            "outputs": {
                "mergedPredictionIndex": {"path": str(expected_root / artifact_path.relative_to(staging)), "sha256": sha256_file(artifact_path)}
            },
            "executionEvidence": {
                "modelLoads": 1,
                "fullImageInferenceEvaluations": 0,
                "cropInferenceEvaluations": crop_evaluations,
                "tileCandidatesAcceptedBeforeProductDeduplication": tile_candidates,
                "internalEdgeRejections": edge_rejections,
                "wallClockSeconds": round(elapsed, 3),
                "perImageFourCropP95Ms": round(timings_ms[p95_index], 3),
                "perImageFourCropMaximumMs": round(max(timings_ms), 3),
                "device": device,
                "sourceDatasetFilesSha256Before": source_report_before["datasetFilesSha256"],
                "sourceDatasetFilesSha256After": source_report_after["datasetFilesSha256"],
                "sourceDatasetUnchanged": True,
                "removedUltralyticsCaches": removed_caches,
            },
            "replayableEvidence": {
                "baselineFidelity": fidelity,
                "baseline": compact_result(baseline),
                "pilot": compact_result(pilot),
                "comparison": comparison,
            },
            "errors": [],
        }
        report["contentSha256"] = canonical_sha256(report)
        output_in_staging = staging / output.name
        output_in_staging.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(staging, expected_root)
        return report
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--device", default="0")
    parser.add_argument("--verify-plan", action="store_true")
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_plan:
        if args.output or args.verify_report:
            parser.error("--verify-plan不能与输出或报告重放并用")
        plan, _ = validate_plan(args.plan.resolve())
        print(json.dumps({"ok": True, "decision": plan["decision"]}, ensure_ascii=False))
        return 0
    if args.verify_report:
        if args.output:
            parser.error("--verify-report不能与--output并用")
        report = replay(args.plan.resolve(), args.verify_report.resolve())
        print(json.dumps({"ok": True, "decision": report["decision"], "reportSha256": sha256_file(args.verify_report.resolve())}, ensure_ascii=False))
        return 0
    if not args.output:
        parser.error("执行模式必须提供--output")
    report = execute(args.plan.resolve(), args.output.resolve(), args.device)
    print(json.dumps({"ok": report["ok"], "decision": report["decision"], "summary": report["replayableEvidence"]["pilot"]["summary"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
