from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import onnxruntime as ort

from _instance_segmentation_metrics import match_instances, parse_yolo_polygons


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def parse_grid(raw: str) -> list[float]:
    values = sorted({round(float(value.strip()), 8) for value in raw.split(",") if value.strip()})
    if not values or any(value <= 0 or value >= 1 for value in values):
        raise ValueError("threshold grid must contain values between zero and one")
    return values


def rasterize_polygon(polygon: Any, width: int, height: int) -> np.ndarray:
    coordinates = np.asarray(polygon.exterior.coords[:-1], dtype=np.float32)
    coordinates[:, 0] *= width
    coordinates[:, 1] *= height
    coordinates[:, 0] = np.clip(coordinates[:, 0], 0, width - 1)
    coordinates[:, 1] = np.clip(coordinates[:, 1], 0, height - 1)
    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.fillPoly(mask, [np.rint(coordinates).astype(np.int32)], 1)
    return mask


def proposal_tensor(rgb: np.ndarray, mask: np.ndarray, size: int = 96) -> np.ndarray:
    height, width = mask.shape
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        raise ValueError("prediction polygon rasterized to an empty mask")
    min_x, max_x = int(xs.min()), int(xs.max()) + 1
    min_y, max_y = int(ys.min()), int(ys.max()) + 1
    side = max(8.0, max(max_x - min_x, max_y - min_y) * 2.0)
    center_x = (min_x + max_x) / 2
    center_y = (min_y + max_y) / 2
    x0 = max(0, int(round(center_x - side / 2)))
    y0 = max(0, int(round(center_y - side / 2)))
    x1 = min(width, int(round(center_x + side / 2)))
    y1 = min(height, int(round(center_y + side / 2)))
    rgb_crop = cv2.resize(rgb[y0:y1, x0:x1], (size, size), interpolation=cv2.INTER_AREA)
    mask_crop = cv2.resize(
        (mask[y0:y1, x0:x1] * 255).astype(np.uint8),
        (size, size), interpolation=cv2.INTER_NEAREST,
    )
    rgba = np.dstack([rgb_crop, mask_crop]).astype(np.float32) / 255.0
    mean = np.asarray([0.485, 0.456, 0.406, 0.0], dtype=np.float32)
    std = np.asarray([0.229, 0.224, 0.225, 1.0], dtype=np.float32)
    return ((rgba - mean) / std).transpose(2, 0, 1)


def sigmoid(value: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-value))


def verify_base_calibration(path: Path, weights: Path) -> None:
    script = Path(__file__).with_name("calibrate-model-score-threshold.py")
    result = subprocess.run(
        [
            sys.executable, str(script), "--verify-report", str(path),
            "--expected-weights", str(weights),
        ],
        capture_output=True, text=True, encoding="utf-8",
    )
    if result.returncode != 0:
        raise ValueError(f"base calibration deep replay failed: {result.stderr or result.stdout}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Select a detector/verifier joint threshold on canonical val30 only."
    )
    parser.add_argument("--base-calibration", required=True)
    parser.add_argument("--training-report", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--detector-thresholds",
        default="0.20,0.21,0.22,0.23,0.24,0.25,0.26,0.27,0.28,0.29,0.30",
    )
    parser.add_argument(
        "--verifier-thresholds",
        default="0.05,0.10,0.15,0.20,0.25,0.30,0.35,0.40,0.45,0.50,0.55,0.60,0.65,0.70,0.75,0.80,0.85,0.90,0.95",
    )
    parser.add_argument("--minimum-matched", type=int, default=128)
    parser.add_argument("--maximum-missed", type=int, default=16)
    parser.add_argument("--maximum-false-positives", type=int, default=18)
    parser.add_argument("--match-iou", type=float, default=0.5)
    parser.add_argument("--strong-iou", type=float, default=0.75)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    base_path = Path(args.base_calibration).resolve()
    training_report_path = Path(args.training_report).resolve()
    output = Path(args.output).resolve()
    if output.exists():
        raise ValueError(f"output must be fresh: {output}")
    base = json.loads(base_path.read_text(encoding="utf-8"))
    training = json.loads(training_report_path.read_text(encoding="utf-8"))
    weights = Path(base["inputs"]["weights"]).resolve()
    verify_base_calibration(base_path, weights)
    if training.get("decision") != "proposal_verifier_training_complete_requires_val30_joint_selection":
        raise ValueError("verifier training report is not eligible for val selection")
    corpus_path = Path(training["inputs"]["corpus"]).resolve()
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    if corpus.get("rolePolicy") != {
        "allowed": ["train-positive", "hard-negative"],
        "valUsedForTraining": False,
        "testUsedForTraining": False,
        "holdoutUsedForTraining": False,
    }:
        raise ValueError("verifier corpus role policy drifted")
    onnx_path = Path(training["artifacts"]["onnx"]).resolve()
    if sha256_file(onnx_path) != training["artifacts"]["onnxSha256"]:
        raise ValueError("verifier ONNX drifted")

    metrics_path = Path(base["inputs"]["metrics"]).resolve()
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    artifact_index_path = Path(base["inputs"]["artifactIndex"]).resolve()
    artifact_index = json.loads(artifact_index_path.read_text(encoding="utf-8"))
    artifact_root = artifact_index_path.parent
    image_records = {item["stem"]: item for item in metrics["runtime_materialization_records"]}
    prediction_records = {item["stem"]: item for item in artifact_index["prediction_records"]}
    if set(image_records) != set(prediction_records) or len(image_records) != 30:
        raise ValueError("val30 image and prediction inventories differ")

    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name
    all_items: list[dict[str, Any]] = []
    for stem in sorted(image_records):
        record = image_records[stem]
        image_path = Path(record["sourceImage"]).resolve()
        truth_path = Path(record["sourceLabel"]).resolve()
        if sha256_file(image_path) != record["sourceImageSha256"]:
            raise ValueError(f"validation image drift: {stem}")
        if sha256_file(truth_path) != record["sourceLabelSha256"]:
            raise ValueError(f"validation truth drift: {stem}")
        prediction_record = prediction_records[stem]
        prediction_path = (
            artifact_root / prediction_record["path"] if prediction_record["path"] else None
        )
        if prediction_path and sha256_file(prediction_path) != prediction_record["sha256"]:
            raise ValueError(f"validation prediction drift: {stem}")
        bgr = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if bgr is None:
            raise ValueError(f"cannot decode validation image: {stem}")
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        height, width = rgb.shape[:2]
        truth = parse_yolo_polygons(truth_path, prediction=False)
        predictions = (
            parse_yolo_polygons(prediction_path, prediction=True)
            if prediction_path else []
        )
        tensors = [
            proposal_tensor(rgb, rasterize_polygon(item["polygon"], width, height))
            for item in predictions
        ]
        scores: list[float] = []
        if tensors:
            logits = session.run(None, {input_name: np.stack(tensors).astype(np.float32)})[0]
            scores = sigmoid(np.asarray(logits).reshape(-1)).astype(float).tolist()
        if len(scores) != len(predictions):
            raise ValueError("verifier score count differs from predictions")
        for prediction, score in zip(predictions, scores, strict=True):
            prediction["verifierScore"] = score
        all_items.append({"stem": stem, "truth": truth, "predictions": predictions})

    detector_thresholds = parse_grid(args.detector_thresholds)
    verifier_thresholds = parse_grid(args.verifier_thresholds)
    sweep: list[dict[str, Any]] = []
    for detector_threshold in detector_thresholds:
        for verifier_threshold in verifier_thresholds:
            totals = {
                "truth": 0, "predictions": 0, "matched": 0,
                "missed": 0, "falsePositives": 0, "maxPredictionsPerImage": 0,
            }
            for item in all_items:
                kept = [
                    prediction for prediction in item["predictions"]
                    if float(prediction["confidence"]) >= detector_threshold
                    and float(prediction["verifierScore"]) >= verifier_threshold
                ]
                matched = match_instances(item["truth"], kept, args.match_iou, args.strong_iou)
                totals["truth"] += matched["truthCount"]
                totals["predictions"] += matched["predictionCount"]
                totals["matched"] += matched["matchedCount"]
                totals["missed"] += matched["missedCount"]
                totals["falsePositives"] += matched["falsePositiveCount"]
                totals["maxPredictionsPerImage"] = max(
                    totals["maxPredictionsPerImage"], matched["predictionCount"]
                )
            qualifies = (
                totals["matched"] >= args.minimum_matched
                and totals["missed"] <= args.maximum_missed
                and totals["falsePositives"] <= args.maximum_false_positives
                and totals["maxPredictionsPerImage"] <= 7
            )
            sweep.append({
                "detectorThreshold": detector_threshold,
                "verifierThreshold": verifier_threshold,
                **totals,
                "qualifies": qualifies,
            })
    qualified = [item for item in sweep if item["qualifies"]]
    qualified.sort(key=lambda item: (
        -item["matched"], item["falsePositives"], item["maxPredictionsPerImage"],
        -item["verifierThreshold"], -item["detectorThreshold"],
    ))
    selected = qualified[0] if qualified else None
    score_records = [
        {
            "stem": item["stem"],
            "scores": [
                {
                    "line": prediction["line"],
                    "detector": round(float(prediction["confidence"]), 8),
                    "verifier": round(float(prediction["verifierScore"]), 8),
                }
                for prediction in item["predictions"]
            ],
        }
        for item in all_items
    ]
    report = {
        "schemaVersion": 1,
        "ok": selected is not None,
        "decision": (
            "candidate26_proposal_verifier_val30_replacement_gate_pass"
            if selected else "candidate26_proposal_verifier_val30_rejected"
        ),
        "productionPromotion": False,
        "frozenTest100Consumed": False,
        "inputs": {
            "baseCalibration": str(base_path),
            "baseCalibrationSha256": sha256_file(base_path),
            "baseWeights": str(weights),
            "baseWeightsSha256": sha256_file(weights),
            "trainingReport": str(training_report_path),
            "trainingReportSha256": sha256_file(training_report_path),
            "verifierOnnx": str(onnx_path),
            "verifierOnnxSha256": sha256_file(onnx_path),
            "valMetrics": str(metrics_path),
            "valMetricsSha256": sha256_file(metrics_path),
            "artifactIndex": str(artifact_index_path),
            "artifactIndexSha256": sha256_file(artifact_index_path),
        },
        "gate": {
            "minimumMatched": args.minimum_matched,
            "maximumMissed": args.maximum_missed,
            "maximumFalsePositives": args.maximum_false_positives,
            "maximumPredictionsPerImage": 7,
            "matchIou": args.match_iou,
            "strongIou": args.strong_iou,
            "selectionSplit": "val30-only",
        },
        "baseline": {"candidate": "candidate21", "matched": 128, "missed": 16, "falsePositives": 19},
        "selected": selected,
        "thresholdSweep": sweep,
        "scoreRecordsSha256": canonical_sha256(score_records),
        "scoreRecords": score_records,
        "next": (
            "lock_candidate26_before_single_frozen_test100_diagnostic"
            if selected else "reject_candidate26_without_running_frozen_test100"
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "ok": report["ok"], "decision": report["decision"],
        "selected": selected, "output": str(output), "sha256": sha256_file(output),
    }, ensure_ascii=False, indent=2))
    if not report["ok"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
