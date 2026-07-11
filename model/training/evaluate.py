from __future__ import annotations

import argparse
import json
from pathlib import Path

from _training_common import (
    ensure_python_dependency,
    load_dataset_config,
    resolve_best_weights_path,
    write_json,
    write_resolved_dataset_yaml,
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
    parser.add_argument("--artifacts-dir", default="", help="Validation plots, prediction labels, and artifact index directory; defaults to <metrics-dir>/evaluation-artifacts")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    dataset_yaml = Path(args.dataset).resolve()
    train_output_dir = Path(args.train_output_dir).resolve()
    weights = Path(args.weights).resolve() if args.weights else resolve_best_weights_path(train_output_dir, args.run_name).resolve()
    output = Path(args.output).resolve()
    artifacts_dir = (
        Path(args.artifacts_dir).resolve()
        if args.artifacts_dir
        else (output.parent / "evaluation-artifacts").resolve()
    )
    config = load_dataset_config(dataset_yaml)
    runtime_dataset_yaml = output.parent / "resolved-dataset.yaml"

    summary = {
        "dataset_yaml": str(dataset_yaml),
        "dataset_root": str(config.dataset_root),
        "runtime_dataset_yaml": str(runtime_dataset_yaml),
        "weights": str(weights),
        "train_output_dir": str(train_output_dir),
        "run_name": args.run_name,
        "output": str(output),
        "artifacts_dir": str(artifacts_dir),
        "artifact_index": str(artifacts_dir / "evaluation-artifacts.json"),
        "split": args.split,
        "imgsz": args.imgsz,
        "device": args.device,
        "dry_run": args.dry_run,
    }

    if args.dry_run:
        print(json.dumps(summary, indent=2))
        return

    ultralytics = ensure_python_dependency("ultralytics", "pip install ultralytics")
    write_resolved_dataset_yaml(runtime_dataset_yaml, config)
    model = ultralytics.YOLO(str(weights))
    artifacts_dir.parent.mkdir(parents=True, exist_ok=True)
    metrics = model.val(
        data=str(runtime_dataset_yaml),
        split=args.split,
        imgsz=args.imgsz,
        device=args.device,
        project=str(artifacts_dir.parent),
        name=artifacts_dir.name,
        exist_ok=True,
        plots=True,
        save_json=True,
        save_txt=True,
        save_conf=True,
    )
    resolved_artifacts_dir = Path(getattr(metrics, "save_dir", artifacts_dir)).resolve()
    artifact_files = sorted(
        str(item.relative_to(resolved_artifacts_dir)).replace("\\", "/")
        for item in resolved_artifacts_dir.rglob("*")
        if item.is_file() and item.name != "evaluation-artifacts.json"
    )
    artifact_index_path = resolved_artifacts_dir / "evaluation-artifacts.json"
    artifact_index = {
        "schema_version": 1,
        "split": args.split,
        "artifacts_dir": str(resolved_artifacts_dir),
        "files": artifact_files,
        "counts": {
            "total": len(artifact_files),
            "plots": sum(1 for item in artifact_files if item.lower().endswith((".png", ".jpg", ".jpeg"))),
            "prediction_labels": sum(1 for item in artifact_files if item.startswith("labels/") and item.endswith(".txt")),
            "json": sum(1 for item in artifact_files if item.lower().endswith(".json")),
        },
    }
    write_json(artifact_index_path, artifact_index)
    payload = {
        **summary,
        "box_map50": float(getattr(metrics.box, "map50", 0.0)),
        "box_map": float(getattr(metrics.box, "map", 0.0)),
        "seg_map50": float(getattr(metrics.seg, "map50", 0.0)),
        "seg_map": float(getattr(metrics.seg, "map", 0.0)),
        "evaluation_artifacts": {
            "directory": str(resolved_artifacts_dir),
            "index": str(artifact_index_path),
            "counts": artifact_index["counts"],
        },
    }
    write_json(output, payload)
    print(f"Evaluation finished. Metrics written to {output}")


if __name__ == "__main__":
    main()
