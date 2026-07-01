from __future__ import annotations

import argparse
from pathlib import Path

from _training_common import (
    count_files,
    ensure_python_dependency,
    load_dataset_config,
    resolve_best_weights_path,
    resolve_training_run_dir,
    write_json,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train the nail texture YOLO segmentation model.")
    parser.add_argument("--dataset", default="model/training/dataset.yaml", help="Path to dataset.yaml")
    parser.add_argument("--output-dir", default="model/exports/nail-texture-seg-v1", help="Directory for training outputs")
    parser.add_argument("--model", default="yolo11n-seg.pt", help="Ultralytics segmentation checkpoint to fine-tune")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", default="auto")
    parser.add_argument("--patience", type=int, default=20)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--run-name", default="nail-texture-seg-v1")
    parser.add_argument("--dry-run", action="store_true", help="Validate config and print the resolved training plan")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    dataset_yaml = Path(args.dataset).resolve()
    output_dir = Path(args.output_dir).resolve()
    config = load_dataset_config(dataset_yaml)

    summary = {
        "dataset_yaml": str(dataset_yaml),
        "dataset_root": str(config.dataset_root),
        "train_images": count_files(config.dataset_root / config.train, (".jpg", ".jpeg", ".png", ".webp")),
        "val_images": count_files(config.dataset_root / config.val, (".jpg", ".jpeg", ".png", ".webp")),
        "test_images": count_files(config.dataset_root / config.test, (".jpg", ".jpeg", ".png", ".webp")),
        "task": config.task,
        "class_count": config.class_count,
        "names": config.names,
        "model": args.model,
        "epochs": args.epochs,
        "imgsz": args.imgsz,
        "batch": args.batch,
        "patience": args.patience,
        "device": args.device,
        "workers": args.workers,
        "run_name": args.run_name,
        "output_dir": str(output_dir),
        "run_dir": str(resolve_training_run_dir(output_dir, args.run_name)),
        "best_weights_path": str(resolve_best_weights_path(output_dir, args.run_name)),
        "dry_run": args.dry_run,
    }

    if args.dry_run:
        print(__import__("json").dumps(summary, indent=2))
        return

    ultralytics = ensure_python_dependency("ultralytics", "pip install ultralytics")
    model = ultralytics.YOLO(args.model)
    output_dir.mkdir(parents=True, exist_ok=True)
    results = model.train(
        data=str(dataset_yaml),
        task="segment",
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        patience=args.patience,
        device=args.device,
        workers=args.workers,
        project=str(output_dir),
        name=args.run_name,
    )
    write_json(
        output_dir / "train-summary.json",
        {
            **summary,
            "results_dir": str(getattr(results, "save_dir", output_dir)),
            "best_weights_path": str(resolve_best_weights_path(output_dir, args.run_name)),
        },
    )
    print(f"Training finished. Summary written to {output_dir / 'train-summary.json'}")


if __name__ == "__main__":
    main()
