#!/usr/bin/env python3
"""为循环011在干净开发真值上的唯一一次只读复评生成可重放质量报告。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
LEGACY_QUALITY_SOURCE = HERE / "build-development-instance-quality-report.py"
MATERIALIZATION_SOURCE = HERE / "materialize-clean-development-evaluation.py"
POSTPROCESS_SOURCE = HERE / "evaluate-candidate53-two-stage-val30.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载模块：{path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


LEGACY = load_module("jiaru_legacy_development_quality", LEGACY_QUALITY_SOURCE)
QUALITY = LEGACY.QUALITY
MATERIALIZATION = load_module("jiaru_clean_development_materialization", MATERIALIZATION_SOURCE)


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


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON根节点必须是对象：{path}")
    return value


def require_file(path: Path, expected_sha256: str | None, label: str) -> Path:
    resolved = path.resolve()
    if not resolved.is_file():
        raise ValueError(f"{label}缺失：{resolved}")
    if expected_sha256 is not None and sha256_file(resolved) != expected_sha256:
        raise ValueError(f"{label}哈希漂移：{resolved}")
    return resolved


def bound_path(binding: Any, label: str) -> Path:
    if not isinstance(binding, dict):
        raise ValueError(f"{label}绑定缺失")
    return require_file(Path(str(binding.get("path", ""))), str(binding.get("sha256", "")), label)


def validate_plan(plan_path: Path) -> tuple[dict[str, Any], Path, Path, Path]:
    plan = read_json(plan_path)
    if (
        plan.get("schemaVersion") != 1
        or plan.get("decision") != "pre_registered_single_read_only_clean_truth_rebaseline"
        or plan.get("releaseState") != "hold"
    ):
        raise ValueError("干净重基线计划顶层合同无效")
    source = plan.get("sourceExperiment", {})
    bound_path(source.get("plan"), "循环011原计划")
    train_summary_path = bound_path(source.get("trainSummary"), "循环011训练摘要")
    weights_path = bound_path(source.get("weights"), "循环011锁定权重")
    dataset = plan.get("evaluationDataset", {})
    materialization_path = bound_path(dataset.get("materializationReport"), "98图评估物化报告")
    materialization = MATERIALIZATION.verify_report(materialization_path)
    dataset_yaml_path = bound_path(dataset.get("datasetYaml"), "98图dataset.yaml")
    if (
        dataset.get("datasetFilesSha256") != materialization.get("datasetFilesSha256")
        or dataset.get("counts") != {
            "evaluationImages": 98,
            "positiveImages": 58,
            "positiveMasks": 354,
            "hardNegativeImages": 40,
        }
        or dataset.get("trainingSourceGroupOverlap") != 0
        or dataset.get("trainingImageSha256Overlap") != 0
        or dataset.get("formalCalibrationTestOrHoldout") is not False
    ):
        raise ValueError("98图评估集计划绑定漂移")
    contract = plan.get("fixedEvaluationContract", {})
    product = contract.get("productDeduplication", {})
    if (
        contract.get("split") != "val"
        or contract.get("inputSize") != 512
        or float(contract.get("scoreThreshold", 0)) != 0.25
        or float(contract.get("matchIou", 0)) != 0.5
        or float(contract.get("completeMaskIou", 0)) != 0.75
        or contract.get("diagnosticOnly") is not True
        or product.get("implementationSha256") != sha256_file(POSTPROCESS_SOURCE)
        or float(product.get("maskIouThreshold", 0)) != LEGACY.MASK_IOU_THRESHOLD
        or float(product.get("maskContainmentThreshold", 0)) != LEGACY.MASK_CONTAINMENT_THRESHOLD
        or float(product.get("maskScoreTolerance", 0)) != LEGACY.MASK_SCORE_TOLERANCE
        or float(product.get("boxIouThreshold", 0)) != LEGACY.BOX_IOU_THRESHOLD
        or int(product.get("maximumCandidatesPerImage", 0)) != LEGACY.MAXIMUM_CANDIDATES
    ):
        raise ValueError("固定评估或产品去重合同漂移")
    lock = plan.get("executionLock", {})
    runner = bound_path(lock.get("evaluationRunner"), "评估runner")
    if lock.get("maximumInferenceRuns") != 1 or lock.get("allOutputsMustBeNew") is not True:
        raise ValueError("一次性推理锁无效")
    train_summary = read_json(train_summary_path)
    if (
        train_summary.get("training_intent") != "pre-registered-development-experiment"
        or train_summary.get("development_experiment_evidence", {}).get("experiment_id") != source.get("experimentId")
        or Path(str(train_summary.get("best_weights_path", ""))).resolve() != weights_path
        or train_summary.get("best_weights_sha256") != sha256_file(weights_path)
    ):
        raise ValueError("循环011训练摘要与锁定权重不一致")
    del runner
    return plan, materialization_path, train_summary_path, weights_path


def build(
    plan_path: Path, metrics_path: Path, artifact_path: Path
) -> dict[str, Any]:
    plan, materialization_path, train_summary_path, weights_path = validate_plan(plan_path)
    materialization = MATERIALIZATION.verify_report(materialization_path)
    dataset_root = Path(str(materialization["outputDir"])).resolve()
    records = materialization.get("records", [])
    by_stem = {Path(str(row["fileName"])).stem: row for row in records}
    if len(by_stem) != 98:
        raise ValueError("98图评估记录存在重复stem或计数漂移")

    metrics_path = require_file(metrics_path, None, "评估metrics")
    artifact_path = require_file(artifact_path, None, "预测artifact索引")
    metrics = read_json(metrics_path)
    artifact = read_json(artifact_path)
    lock = plan["executionLock"]
    dataset_binding = plan["evaluationDataset"]
    if (
        metrics.get("split") != "val"
        or metrics.get("imgsz") != 512
        or Path(str(metrics.get("dataset_yaml", ""))).resolve() != Path(str(dataset_binding["datasetYaml"]["path"])).resolve()
        or metrics.get("dataset_yaml_sha256") != dataset_binding["datasetYaml"]["sha256"]
        or Path(str(metrics.get("weights", ""))).resolve() != weights_path
        or metrics.get("weights_sha256") != sha256_file(weights_path)
        or Path(str(metrics.get("output", ""))).resolve() != Path(str(lock["metrics"])).resolve()
        or Path(str(metrics.get("artifacts_dir", ""))).resolve() != Path(str(lock["artifacts"])).resolve()
        or metrics.get("source_dataset_inventory_sha256_before") != materialization["datasetFilesSha256"]
        or metrics.get("source_dataset_inventory_sha256_after") != materialization["datasetFilesSha256"]
        or metrics.get("source_dataset_unchanged") is not True
        or Path(str(metrics.get("artifact_index", ""))).resolve() != artifact_path
        or artifact.get("split") != "val"
    ):
        raise ValueError("评估metrics或一次性输出路径与预注册锁不一致")
    prediction_records = artifact.get("prediction_records")
    if not isinstance(prediction_records, list) or canonical_sha256(prediction_records) != artifact.get("prediction_records_sha256"):
        raise ValueError("预测记录缺失或哈希漂移")
    artifact_root = Path(str(artifact.get("artifacts_dir", ""))).resolve()
    predictions: dict[str, Path | None] = {}
    for row in prediction_records:
        stem = str(row.get("stem", ""))
        if stem in predictions:
            raise ValueError(f"预测stem重复：{stem}")
        relative = row.get("path")
        if relative is None:
            if row.get("sha256") is not None or int(row.get("prediction_count", -1)) != 0:
                raise ValueError(f"零预测记录无效：{stem}")
            predictions[stem] = None
            continue
        path = (artifact_root / str(relative)).resolve()
        try:
            path.relative_to(artifact_root)
        except ValueError as error:
            raise ValueError(f"预测路径越界：{stem}") from error
        require_file(path, str(row.get("sha256", "")), "预测标签")
        predictions[stem] = path
    if set(predictions) != set(by_stem):
        raise ValueError("预测没有逐图覆盖98图评估集")

    threshold = 0.25
    image_rows: list[dict[str, Any]] = []
    totals = {"truth": 0, "predictions": 0, "matched": 0, "completeMasks": 0, "missing": 0, "duplicates": 0, "falsePositives": 0, "invalidPredictionMasks": 0}
    for stem in sorted(by_stem):
        record = by_stem[stem]
        truth = QUALITY.parse_label(dataset_root / str(record["label"]), prediction=False, threshold=threshold)
        prediction_path = predictions[stem]
        raw = QUALITY.parse_label(prediction_path, prediction=True, threshold=threshold) if prediction_path else []
        predicted = LEGACY.suppress_product_duplicates(raw)
        matches, missing, unmatched = QUALITY.match_instances(truth, predicted)
        matched_details = [
            {"truthIndex": truth_index + 1, "predictionIndex": prediction_index + 1, "iou": round(iou, 6), "complete": iou >= 0.75}
            for truth_index, prediction_index, iou in sorted(matches)
        ]
        unmatched_details: list[dict[str, Any]] = []
        duplicates = 0
        false_positives = 0
        for prediction_index in unmatched:
            best_iou = max((QUALITY.polygon_iou(item[0], predicted[prediction_index][0]) for item in truth), default=0.0)
            category = "duplicate" if best_iou >= 0.10 else "false-positive"
            duplicates += category == "duplicate"
            false_positives += category == "false-positive"
            unmatched_details.append({
                "predictionIndex": prediction_index + 1,
                "category": category,
                "bestTruthIou": round(best_iou, 6),
                "originallyValid": bool(predicted[prediction_index][2]),
            })
        complete = sum(item["complete"] for item in matched_details)
        invalid = sum(not item[2] for item in predicted)
        positive = record.get("role") == "train-positive"
        image_row = {
            "stem": stem,
            "role": record.get("role"),
            "sourceGroup": record.get("sourceGroup"),
            "truthCount": len(truth),
            "predictionCount": len(predicted),
            "matchedCount": len(matches),
            "completeMaskCount": complete,
            "missingCount": len(missing),
            "missingTruthIndices": [index + 1 for index in sorted(missing)],
            "duplicateCount": duplicates,
            "falsePositiveCount": false_positives,
            "invalidPredictionMaskCount": invalid,
            "matchedInstances": matched_details,
            "unmatchedPredictions": unmatched_details,
            "allVisibleNailsRecognized": positive and not missing,
            "directlyExtractable": positive and not missing and duplicates == 0 and false_positives == 0 and invalid == 0 and complete == len(truth),
        }
        image_rows.append(image_row)
        totals["truth"] += len(truth)
        totals["predictions"] += len(predicted)
        totals["matched"] += len(matches)
        totals["completeMasks"] += complete
        totals["missing"] += len(missing)
        totals["duplicates"] += duplicates
        totals["falsePositives"] += false_positives
        totals["invalidPredictionMasks"] += invalid

    positives = [row for row in image_rows if row["role"] == "train-positive"]
    negatives = [row for row in image_rows if row["role"] == "hard-negative"]
    if len(positives) != 58 or len(negatives) != 40 or totals["truth"] != 354:
        raise ValueError("质量统计角色或真值分母漂移")
    missing_images = sum(row["missingCount"] > 0 for row in positives)
    direct_images = sum(row["directlyExtractable"] for row in positives)
    negative_fp_images = sum(row["predictionCount"] > 0 for row in negatives)
    weighted = totals["duplicates"] + 1.5 * totals["invalidPredictionMasks"] + 2 * totals["falsePositives"]
    summary = {
        "evaluationImages": 98,
        "positiveImages": 58,
        "hardNegativeImages": 40,
        **totals,
        "missingImages": missing_images,
        "directlyExtractableImages": direct_images,
        "hardNegativeFalsePositiveImages": negative_fp_images,
        "instanceRecall": round(totals["matched"] / totals["truth"], 8),
        "completeMaskRatio": round(totals["completeMasks"] / totals["truth"], 8),
        "missingImageRate": round(missing_images / len(positives), 8),
        "weightedSpuriousRate": round(weighted / totals["truth"], 8),
        "directlyExtractableRate": round(direct_images / len(positives), 8),
    }
    floors = plan["formalFloorForDevelopmentSignalOnly"]
    gates = {
        "instanceRecall": summary["instanceRecall"] >= float(floors["minimumInstanceRecall"]),
        "completeMaskRatio": summary["completeMaskRatio"] >= float(floors["minimumCompleteMaskRatio"]),
        "missingImageRate": summary["missingImageRate"] <= float(floors["maximumMissingImageRate"]),
        "weightedSpuriousRate": summary["weightedSpuriousRate"] <= float(floors["maximumWeightedSpuriousRate"]),
        "everyEvaluationImageAccountedFor": len(predictions) == 98,
    }
    payload = {
        "schemaVersion": 2,
        "evaluationKind": "single_read_only_clean_truth_rebaseline",
        "ok": True,
        "decision": "pass_train_internal_development_floor" if all(gates.values()) else "fail_train_internal_development_floor",
        "diagnosticOnly": True,
        "cannotSelectFormalScoreThreshold": True,
        "cannotProveReleaseQuality": True,
        "releaseState": "hold",
        "experimentId": plan["sourceExperiment"]["experimentId"],
        "inputs": {
            "plan": {"path": str(plan_path), "sha256": sha256_file(plan_path)},
            "materializationReport": {"path": str(materialization_path), "sha256": sha256_file(materialization_path)},
            "trainSummary": {"path": str(train_summary_path), "sha256": sha256_file(train_summary_path)},
            "metrics": {"path": str(metrics_path), "sha256": sha256_file(metrics_path)},
            "artifactIndex": {"path": str(artifact_path), "sha256": sha256_file(artifact_path)},
            "weights": {"path": str(weights_path), "sha256": sha256_file(weights_path)},
        },
        "contract": plan["fixedEvaluationContract"],
        "executionEvidence": {"observedInferenceRuns": 1, "freshUniqueOutputRoot": str(Path(str(lock["outputRoot"])).resolve()), "historicalCycle011ReportModified": False},
        "gates": gates,
        "summary": summary,
        "images": image_rows,
    }
    payload["contentSha256"] = canonical_sha256(payload)
    return payload


def first_difference(left: Any, right: Any, path: str = "$") -> str | None:
    if type(left) is not type(right):
        return f"{path}: type differs"
    if isinstance(left, dict):
        if set(left) != set(right):
            return f"{path}: keys differ"
        for key in sorted(left):
            difference = first_difference(left[key], right[key], f"{path}.{key}")
            if difference:
                return difference
        return None
    if isinstance(left, list):
        if len(left) != len(right):
            return f"{path}: length differs"
        for index, (a, b) in enumerate(zip(left, right)):
            difference = first_difference(a, b, f"{path}[{index}]")
            if difference:
                return difference
        return None
    return None if left == right else f"{path}: value differs"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--metrics", type=Path)
    parser.add_argument("--artifact-index", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        if any((args.plan, args.metrics, args.artifact_index, args.output)):
            parser.error("--verify-report不能与生成参数并用")
        saved = read_json(args.verify_report.resolve())
        inputs = saved.get("inputs", {})
        rebuilt = build(
            Path(str(inputs.get("plan", {}).get("path", ""))).resolve(),
            Path(str(inputs.get("metrics", {}).get("path", ""))).resolve(),
            Path(str(inputs.get("artifactIndex", {}).get("path", ""))).resolve(),
        )
        difference = first_difference(saved, rebuilt)
        if difference:
            raise ValueError(f"干净重基线质量报告重放不一致：{difference}")
        payload = saved
    else:
        if not all((args.plan, args.metrics, args.artifact_index, args.output)):
            parser.error("生成参数不完整")
        output = args.output.resolve()
        if output.exists():
            raise ValueError(f"输出报告必须是新路径：{output}")
        payload = build(args.plan.resolve(), args.metrics.resolve(), args.artifact_index.resolve())
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": payload["decision"], "summary": payload["summary"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
