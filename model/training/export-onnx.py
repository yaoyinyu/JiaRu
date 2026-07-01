from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from _training_common import ensure_python_dependency, resolve_best_weights_path, write_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export the nail texture segmentation model to ONNX and write a browser manifest.")
    parser.add_argument("--weights", default="", help="PyTorch checkpoint to export; defaults to <train-output-dir>/<run-name>/weights/best.pt")
    parser.add_argument("--train-output-dir", default="model/exports/nail-texture-seg-v1", help="Training output directory used to derive default weights path")
    parser.add_argument("--run-name", default="nail-texture-seg-v1", help="Training run name used to derive default weights path")
    parser.add_argument("--output-dir", default="public/models/nail-texture-seg", help="Browser model output directory")
    parser.add_argument("--model-version", default="nail-texture-seg-v1")
    parser.add_argument("--input-size", type=int, default=640)
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

    summary = {
        "weights": str(weights),
        "train_output_dir": str(train_output_dir),
        "run_name": args.run_name,
        "output_dir": str(output_dir),
        "onnx_path": str(onnx_path),
        "manifest_path": str(manifest_path),
        "model_version": args.model_version,
        "input_size": args.input_size,
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
    write_json(
        manifest_path,
        {
            "version": args.model_version,
            "task": args.task,
            "inputSize": args.input_size,
            "backendPreferences": args.backend_preferences,
            "modelFile": onnx_path.name,
            "labels": args.labels,
        },
    )
    print(f"ONNX export finished. Manifest written to {manifest_path}")


if __name__ == "__main__":
    main()
