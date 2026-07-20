from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import shutil
from pathlib import Path
from types import ModuleType

from _training_common import ensure_python_dependency, resolve_best_weights_path, write_json


def sha256_file(file_path: Path) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def probability(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0 or parsed >= 1:
        raise argparse.ArgumentTypeError("must be a finite number between 0 and 1 (exclusive)")
    return parsed


def load_calibration_verifier() -> ModuleType:
    script = Path(__file__).with_name("calibrate-model-score-threshold.py")
    spec = importlib.util.spec_from_file_location("score_threshold_calibration_for_export", script)
    if spec is None or spec.loader is None:
        raise ValueError(f"calibration verifier cannot be loaded: {script}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export the nail texture segmentation model to ONNX and write a browser manifest.")
    parser.add_argument("--weights", default="", help="PyTorch checkpoint to export; defaults to <train-output-dir>/<run-name>/weights/best.pt")
    parser.add_argument("--train-output-dir", default="model/exports/nail-texture-seg-v1", help="Training output directory used to derive default weights path")
    parser.add_argument("--run-name", default="nail-texture-seg-v1", help="Training run name used to derive default weights path")
    parser.add_argument("--output-dir", default="public/models/nail-texture-seg", help="Browser model output directory")
    parser.add_argument("--model-version", default="nail-texture-seg-v1")
    parser.add_argument("--input-size", type=int, default=640)
    parser.add_argument("--input-layout", default="NCHW")
    parser.add_argument("--color-order", default="RGB")
    parser.add_argument("--normalization", default="zero_to_one")
    parser.add_argument("--resize-mode", default="letterbox")
    parser.add_argument("--output-contract", default="ultralytics-seg-raw-v1")
    parser.add_argument("--score-threshold", type=probability)
    parser.add_argument("--candidate-mode", action="store_true")
    parser.add_argument("--calibration-report")
    parser.add_argument("--task", default="segment")
    parser.add_argument("--backend-preferences", nargs="+", default=["webgpu", "wasm"])
    parser.add_argument("--labels", nargs="+", default=["nail_texture"])
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    train_output_dir = Path(args.train_output_dir).resolve()
    weights = Path(args.weights).resolve() if args.weights else resolve_best_weights_path(train_output_dir, args.run_name).resolve()
    output_dir = Path(args.output_dir).resolve()
    onnx_path = output_dir / f"{args.model_version}.onnx"
    manifest_path = output_dir / "manifest.json"
    calibration_evidence = None
    if args.candidate_mode:
        if not args.calibration_report:
            raise ValueError("candidate mode requires --calibration-report")
        if args.score_threshold is not None:
            raise ValueError(
                "candidate mode derives scoreThreshold from --calibration-report; "
                "--score-threshold is prohibited"
            )
        calibration_report = Path(args.calibration_report).resolve()
        if calibration_report in {onnx_path, manifest_path}:
            raise ValueError("candidate export output must not overwrite the calibration report")
        verifier = load_calibration_verifier()
        verified = verifier.verify_calibration_report(calibration_report, weights)
        score_threshold = verified["scoreThreshold"]
        calibration_evidence = {
            "path": str(verified["reportPath"]),
            "sha256": verified["reportSha256"],
            "datasetYamlSha256": verified["datasetYamlSha256"],
            "metricsSha256": verified["metricsSha256"],
            "artifactIndexSha256": verified["artifactIndexSha256"],
            "weightsSha256": verified["weightsSha256"],
            "decision": verified["decision"],
        }
    else:
        if args.calibration_report:
            raise ValueError("--calibration-report requires --candidate-mode")
        score_threshold = args.score_threshold if args.score_threshold is not None else 0.35

    summary = {
        "weights": str(weights),
        "train_output_dir": str(train_output_dir),
        "run_name": args.run_name,
        "output_dir": str(output_dir),
        "onnx_path": str(onnx_path),
        "manifest_path": str(manifest_path),
        "model_version": args.model_version,
        "input_size": args.input_size,
        "input_layout": args.input_layout,
        "color_order": args.color_order,
        "normalization": args.normalization,
        "resize_mode": args.resize_mode,
        "output_contract": args.output_contract,
        "score_threshold": score_threshold,
        "candidate_mode": args.candidate_mode,
        "score_threshold_evidence": calibration_evidence,
        "task": args.task,
        "backend_preferences": args.backend_preferences,
        "labels": args.labels,
        "dry_run": args.dry_run,
    }

    if args.dry_run:
        print(json.dumps(summary, indent=2))
        return

    ultralytics = ensure_python_dependency("ultralytics", "pip install ultralytics")
    model = ultralytics.YOLO(str(weights))
    export_path = Path(model.export(format="onnx", imgsz=args.input_size))

    output_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(export_path, onnx_path)
    model_size_bytes = onnx_path.stat().st_size
    model_sha256 = sha256_file(onnx_path)
    manifest = {
            "version": args.model_version,
            "task": args.task,
            "inputSize": args.input_size,
            "inputLayout": args.input_layout,
            "colorOrder": args.color_order,
            "normalization": args.normalization,
            "resizeMode": args.resize_mode,
            "backendPreferences": args.backend_preferences,
            "modelFile": onnx_path.name,
            "outputContract": args.output_contract,
            "scoreThreshold": score_threshold,
            "modelSizeBytes": model_size_bytes,
            "sha256": model_sha256,
            "labels": args.labels,
        }
    if calibration_evidence is not None:
        manifest["scoreThresholdEvidence"] = calibration_evidence
    write_json(manifest_path, manifest)
    print(f"ONNX export finished. Manifest written to {manifest_path}")


if __name__ == "__main__":
    main()
