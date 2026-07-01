from __future__ import annotations

import argparse
import json
from pathlib import Path

from _training_common import (
    ensure_python_dependency,
    load_dataset_config,
    resolve_best_weights_path,
    write_json,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate the nail texture segmentation model.")
    parser.add_argument("--dataset", default="model/training/dataset.yaml", help="Path to dataset.yaml")
    parser.add_argument("--weights", default="", help="Model weights to evaluate; defaults to <train-output-dir>/<run-name>/weights/best.pt")
    parser.add_argument("--train-output-dir", default="model/exports/nail-texture-seg-v1", help="Training output directory used to derive default weights path")
    parser.add_argument("--run-name", default="nail-texture-seg-v1", help="Training run name used to derive default weights path")
    parser.add_argument("--output", default="model/exports/nail-texture-seg-v1/metrics.json", help="Where to write evaluation metrics")
    parser.add_argument("--split", default="test", choices=["train", "val", "test"])
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    dataset_yaml = Path(args.dataset).resolve()
    train_output_dir = Path(args.train_output_dir).resolve()
    weights = Path(args.weights).resolve() if args.weights else resolve_best_weights_path(train_output_dir, args.run_name).resolve()
    output = Path(args.output).resolve()
    config = load_dataset_config(dataset_yaml)

    summary = {
        "dataset_yaml": str(dataset_yaml),
        "dataset_root": str(config.dataset_root),
        "weights": str(weights),
        "train_output_dir": str(train_output_dir),
        "run_name": args.run_name,
        "output": str(output),
        "split": args.split,
        "imgsz": args.imgsz,
        "device": args.device,
        "dry_run": args.dry_run,
    }

    if args.dry_run:
        print(json.dumps(summary, indent=2))
        return

    ultralytics = ensure_python_dependency("ultralytics", "pip install ultralytics")
    model = ultralytics.YOLO(str(weights))
    metrics = model.val(
        data=str(dataset_yaml),
        split=args.split,
        imgsz=args.imgsz,
        device=args.device,
    )
    payload = {
        **summary,
        "box_map50": float(getattr(metrics.box, "map50", 0.0)),
        "box_map": float(getattr(metrics.box, "map", 0.0)),
        "seg_map50": float(getattr(metrics.seg, "map50", 0.0)),
        "seg_map": float(getattr(metrics.seg, "map", 0.0)),
    }
    write_json(output, payload)
    print(f"Evaluation finished. Metrics written to {output}")


if __name__ == "__main__":
    main()
