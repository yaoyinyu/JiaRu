from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
POSTPROCESS_SOURCE = HERE / "evaluate-candidate53-two-stage-val30.py"
MASK_IOU_THRESHOLD = 0.60
MASK_CONTAINMENT_THRESHOLD = 0.85
MASK_SCORE_TOLERANCE = 0.12
BOX_IOU_THRESHOLD = 0.55
MAXIMUM_CANDIDATES = 10


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


QUALITY = load_module(
    "jiaru_positive_quality", HERE / "build-positive-recognition-quality-report.py"
)
MATERIALIZATION = load_module(
    "jiaru_development_materialization",
    HERE / "materialize-source-group-development-dataset.py",
)


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


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def require_file(value: str, label: str) -> Path:
    path = Path(value).resolve()
    if not path.is_file():
        raise ValueError(f"{label} is missing: {path}")
    return path


def box_iou(left: tuple[float, float, float, float], right: tuple[float, float, float, float]) -> float:
    x0, y0 = max(left[0], right[0]), max(left[1], right[1])
    x1, y1 = min(left[2], right[2]), min(left[3], right[3])
    intersection = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    if intersection <= 0:
        return 0.0
    left_area = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    right_area = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    union = left_area + right_area - intersection
    return intersection / union if union else 0.0


def suppress_product_duplicates(items: list[tuple[Any, float, bool]]) -> list[tuple[Any, float, bool]]:
    indexed = [
        {"item": item, "polygon": item[0], "score": item[1], "index": index}
        for index, item in enumerate(items)
    ]
    kept: list[dict[str, Any]] = []
    for candidate in sorted(indexed, key=lambda row: (-row["score"], row["index"])):
        duplicate_index = -1
        for index, selected in enumerate(kept):
            intersection = candidate["polygon"].intersection(selected["polygon"]).area
            union = candidate["polygon"].union(selected["polygon"]).area
            iou = intersection / union if union else 0.0
            containment = intersection / min(candidate["polygon"].area, selected["polygon"].area)
            if iou >= MASK_IOU_THRESHOLD or containment >= MASK_CONTAINMENT_THRESHOLD:
                duplicate_index = index
                break
        if duplicate_index < 0:
            kept.append(candidate)
            continue
        selected = kept[duplicate_index]
        if (
            candidate["polygon"].area > selected["polygon"].area
            and candidate["score"] + MASK_SCORE_TOLERANCE >= selected["score"]
        ):
            kept[duplicate_index] = candidate
    box_kept: list[dict[str, Any]] = []
    for candidate in sorted(kept, key=lambda row: (-row["score"], row["index"])):
        bounds = tuple(float(value) for value in candidate["polygon"].bounds)
        if any(
            box_iou(bounds, tuple(float(value) for value in selected["polygon"].bounds))
            >= BOX_IOU_THRESHOLD
            for selected in box_kept
        ):
            continue
        box_kept.append(candidate)
    return [row["item"] for row in box_kept[:MAXIMUM_CANDIDATES]]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a fixed-threshold train-internal development quality report."
    )
    parser.add_argument("--plan")
    parser.add_argument("--experiment-id")
    parser.add_argument("--materialization-report")
    parser.add_argument("--train-summary")
    parser.add_argument("--metrics")
    parser.add_argument("--artifact-index")
    parser.add_argument("--weights")
    parser.add_argument("--output")
    parser.add_argument("--verify-report")
    return parser


def build(args: argparse.Namespace) -> dict[str, Any]:
    plan_path = require_file(args.plan, "plan")
    materialization_path = require_file(
        args.materialization_report, "materialization report"
    )
    train_summary_path = require_file(args.train_summary, "train summary")
    metrics_path = require_file(args.metrics, "metrics")
    artifact_path = require_file(args.artifact_index, "artifact index")
    weights_path = require_file(args.weights, "weights")

    plan = load_object(plan_path)
    if plan.get("decision") != "pre_registered_two_short_single_variable_experiments":
        raise ValueError("development plan decision is not approved")
    experiments = plan.get("experiments")
    experiment = next(
        (
            row
            for row in experiments
            if isinstance(row, dict) and row.get("experimentId") == args.experiment_id
        ),
        None,
    ) if isinstance(experiments, list) else None
    if experiment is None:
        raise ValueError("experimentId is not registered in the development plan")
    contract = plan.get("fixedDevelopmentEvaluationContract")
    if not isinstance(contract, dict) or contract.get("diagnosticOnly") is not True:
        raise ValueError("development evaluation contract is invalid")
    if (
        contract.get("split") != "val"
        or int(contract.get("inputSize", 0)) != 512
        or float(contract.get("scoreThreshold", 0)) != 0.25
        or float(contract.get("matchIou", 0)) != 0.5
        or float(contract.get("completeMaskIou", 0)) != 0.75
    ):
        raise ValueError("fixed development evaluation contract drifted")

    materialization = MATERIALIZATION.verify_report(materialization_path)
    records = materialization.get("records")
    dataset_root = Path(str(materialization.get("outputDir", ""))).resolve()
    eval_records = [
        row
        for row in records
        if isinstance(row, dict) and row.get("developmentSplit") == "val"
    ] if isinstance(records, list) else []
    if len(eval_records) != 105:
        raise ValueError("development evaluation must contain exactly 105 images")
    by_stem = {Path(str(row["fileName"])).stem: row for row in eval_records}
    if len(by_stem) != len(eval_records):
        raise ValueError("development evaluation contains duplicate image stems")

    train_summary = load_object(train_summary_path)
    evidence = train_summary.get("development_experiment_evidence")
    if (
        train_summary.get("training_intent") != "pre-registered-development-experiment"
        or not isinstance(evidence, dict)
        or evidence.get("experiment_id") != args.experiment_id
        or Path(str(evidence.get("plan", ""))).resolve() != plan_path
        or evidence.get("plan_sha256") != sha256_file(plan_path)
        or train_summary.get("best_weights_sha256") != sha256_file(weights_path)
        or Path(str(train_summary.get("best_weights_path", ""))).resolve() != weights_path
    ):
        raise ValueError("train summary is not bound to this experiment and weight")

    metrics = load_object(metrics_path)
    artifacts = load_object(artifact_path)
    metric_artifacts = metrics.get("evaluation_artifacts")
    if (
        metrics.get("split") != "val"
        or int(metrics.get("imgsz", 0)) != 512
        or metrics.get("weights_sha256") != sha256_file(weights_path)
        or metrics.get("source_dataset_unchanged") is not True
        or metrics.get("source_dataset_inventory_sha256_before")
        != materialization.get("datasetFilesSha256")
        or not isinstance(metric_artifacts, dict)
        or Path(str(metric_artifacts.get("index", ""))).resolve() != artifact_path
        or metric_artifacts.get("index_sha256") != sha256_file(artifact_path)
        or artifacts.get("split") != "val"
    ):
        raise ValueError("evaluation metrics or artifact lineage is invalid")
    prediction_records = artifacts.get("prediction_records")
    if (
        not isinstance(prediction_records, list)
        or canonical_sha256(prediction_records)
        != artifacts.get("prediction_records_sha256")
    ):
        raise ValueError("prediction records are invalid")
    predictions: dict[str, Path | None] = {}
    artifacts_dir = Path(str(artifacts.get("artifacts_dir", ""))).resolve()
    for row in prediction_records:
        if not isinstance(row, dict):
            raise ValueError("prediction record is invalid")
        stem = str(row.get("stem", ""))
        if stem in predictions:
            raise ValueError(f"duplicate prediction stem: {stem}")
        relative = row.get("path")
        if relative is None:
            if row.get("sha256") is not None or int(row.get("prediction_count", -1)) != 0:
                raise ValueError(f"zero-prediction record is invalid: {stem}")
            predictions[stem] = None
        else:
            path = artifacts_dir / str(relative)
            if not path.is_file() or sha256_file(path) != row.get("sha256"):
                raise ValueError(f"prediction label drifted: {path}")
            predictions[stem] = path
    if set(predictions) != set(by_stem):
        raise ValueError("prediction index does not account for every evaluation image")

    threshold = 0.25
    image_rows: list[dict[str, Any]] = []
    totals = {
        "truth": 0,
        "predictions": 0,
        "matched": 0,
        "completeMasks": 0,
        "missing": 0,
        "duplicates": 0,
        "falsePositives": 0,
        "invalidPredictionMasks": 0,
    }
    for stem in sorted(by_stem):
        record = by_stem[stem]
        truth_path = dataset_root / str(record["label"])
        truth = QUALITY.parse_label(truth_path, prediction=False, threshold=threshold)
        prediction_path = predictions[stem]
        raw_predicted = (
            QUALITY.parse_label(prediction_path, prediction=True, threshold=threshold)
            if prediction_path is not None
            else []
        )
        predicted = suppress_product_duplicates(raw_predicted)
        matches, missing, unmatched = QUALITY.match_instances(truth, predicted)
        duplicates = 0
        false_positives = 0
        for prediction_index in unmatched:
            maximum_iou = max(
                (
                    QUALITY.polygon_iou(item[0], predicted[prediction_index][0])
                    for item in truth
                ),
                default=0.0,
            )
            if maximum_iou >= 0.10:
                duplicates += 1
            else:
                false_positives += 1
        complete = sum(1 for _, _, iou in matches if iou >= 0.75)
        invalid = sum(1 for _, _, originally_valid in predicted if not originally_valid)
        positive = record.get("role") == "train-positive"
        row = {
            "stem": stem,
            "role": record.get("role"),
            "sourceGroup": record.get("sourceGroup"),
            "truthCount": len(truth),
            "predictionCount": len(predicted),
            "matchedCount": len(matches),
            "completeMaskCount": complete,
            "missingCount": len(missing),
            "duplicateCount": duplicates,
            "falsePositiveCount": false_positives,
            "invalidPredictionMaskCount": invalid,
            "allVisibleNailsRecognized": positive and len(missing) == 0,
            "directlyExtractable": positive
            and len(missing) == 0
            and duplicates == 0
            and false_positives == 0
            and invalid == 0
            and complete == len(truth),
            "matchIous": [round(iou, 6) for _, _, iou in sorted(matches)],
        }
        image_rows.append(row)
        totals["truth"] += len(truth)
        totals["predictions"] += len(predicted)
        totals["matched"] += len(matches)
        totals["completeMasks"] += complete
        totals["missing"] += len(missing)
        totals["duplicates"] += duplicates
        totals["falsePositives"] += false_positives
        totals["invalidPredictionMasks"] += invalid

    positive_rows = [row for row in image_rows if row["role"] == "train-positive"]
    negative_rows = [row for row in image_rows if row["role"] == "hard-negative"]
    if len(positive_rows) != 65 or len(negative_rows) != 40 or totals["truth"] != 400:
        raise ValueError("development role counts drifted")
    missing_images = sum(row["missingCount"] > 0 for row in positive_rows)
    directly_extractable = sum(row["directlyExtractable"] for row in positive_rows)
    negative_false_positive_images = sum(row["predictionCount"] > 0 for row in negative_rows)
    weighted_spurious = (
        totals["duplicates"]
        + 1.5 * totals["invalidPredictionMasks"]
        + 2.0 * totals["falsePositives"]
    )
    summary = {
        "evaluationImages": len(image_rows),
        "positiveImages": len(positive_rows),
        "hardNegativeImages": len(negative_rows),
        **totals,
        "missingImages": missing_images,
        "directlyExtractableImages": directly_extractable,
        "hardNegativeFalsePositiveImages": negative_false_positive_images,
        "instanceRecall": round(totals["matched"] / totals["truth"], 8),
        "completeMaskRatio": round(totals["completeMasks"] / totals["truth"], 8),
        "missingImageRate": round(missing_images / len(positive_rows), 8),
        "weightedSpuriousRate": round(weighted_spurious / totals["truth"], 8),
        "directlyExtractableRate": round(directly_extractable / len(positive_rows), 8),
    }
    floors = contract.get("formalFloorForPromotionToFullTrain")
    if not isinstance(floors, dict):
        raise ValueError("formal-like development floors are missing")
    gates = {
        "instanceRecall": summary["instanceRecall"]
        >= float(floors["minimumInstanceRecall"]),
        "completeMaskRatio": summary["completeMaskRatio"]
        >= float(floors["minimumCompleteMaskRatio"]),
        "missingImageRate": summary["missingImageRate"]
        <= float(floors["maximumMissingImageRate"]),
        "weightedSpuriousRate": summary["weightedSpuriousRate"]
        <= float(floors["maximumWeightedSpuriousRate"]),
        "everyEvaluationImageAccountedFor": len(predictions) == len(image_rows),
    }
    payload = {
        "schemaVersion": 1,
        "decision": (
            "pass_train_internal_development_floor"
            if all(gates.values())
            else "fail_train_internal_development_floor"
        ),
        "diagnosticOnly": True,
        "cannotSelectFormalScoreThreshold": True,
        "cannotProveReleaseQuality": True,
        "releaseState": "hold",
        "experimentId": args.experiment_id,
        "inputs": {
            "plan": {"path": str(plan_path), "sha256": sha256_file(plan_path)},
            "materializationReport": {
                "path": str(materialization_path),
                "sha256": sha256_file(materialization_path),
            },
            "trainSummary": {
                "path": str(train_summary_path),
                "sha256": sha256_file(train_summary_path),
            },
            "metrics": {"path": str(metrics_path), "sha256": sha256_file(metrics_path)},
            "artifactIndex": {
                "path": str(artifact_path),
                "sha256": sha256_file(artifact_path),
            },
            "weights": {"path": str(weights_path), "sha256": sha256_file(weights_path)},
        },
        "contract": contract,
        "productDeduplication": {
            "implementation": str(POSTPROCESS_SOURCE.resolve()),
            "implementationSha256": sha256_file(POSTPROCESS_SOURCE),
            "maskIouThreshold": MASK_IOU_THRESHOLD,
            "maskContainmentThreshold": MASK_CONTAINMENT_THRESHOLD,
            "maskScoreTolerance": MASK_SCORE_TOLERANCE,
            "boxIouThreshold": BOX_IOU_THRESHOLD,
            "maximumCandidatesPerImage": MAXIMUM_CANDIDATES,
        },
        "gates": gates,
        "summary": summary,
        "images": image_rows,
    }
    payload["contentSha256"] = canonical_sha256(payload)
    return payload


def args_from_report(report: dict[str, Any]) -> argparse.Namespace:
    inputs = report.get("inputs")
    if not isinstance(inputs, dict):
        raise ValueError("report inputs are missing")
    return argparse.Namespace(
        plan=inputs["plan"]["path"],
        experiment_id=report["experimentId"],
        materialization_report=inputs["materializationReport"]["path"],
        train_summary=inputs["trainSummary"]["path"],
        metrics=inputs["metrics"]["path"],
        artifact_index=inputs["artifactIndex"]["path"],
        weights=inputs["weights"]["path"],
        output=None,
        verify_report=None,
    )


def main() -> int:
    args = build_parser().parse_args()
    if args.verify_report:
        path = require_file(args.verify_report, "report")
        saved = load_object(path)
        rebuilt = build(args_from_report(saved))
        if rebuilt != saved:
            raise ValueError("development quality report replay differs from saved report")
        print(json.dumps({"ok": True, "decision": saved["decision"], "summary": saved["summary"]}, ensure_ascii=False))
        return 0
    required = (
        args.plan,
        args.experiment_id,
        args.materialization_report,
        args.train_summary,
        args.metrics,
        args.artifact_index,
        args.weights,
        args.output,
    )
    if not all(required):
        raise ValueError("all build arguments are required")
    payload = build(args)
    output = Path(args.output).resolve()
    if output.exists():
        raise ValueError(f"output must not already exist: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": payload["decision"], "summary": payload["summary"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
