from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType

from _training_common import (
    count_files,
    ensure_python_dependency,
    load_dataset_config,
    resolve_best_weights_path,
    resolve_training_run_dir,
    write_json,
    write_resolved_dataset_yaml,
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
    parser.add_argument("--candidate-mode", action="store_true", help="Require a deeply replayed candidate-input audit and mark this run as a release-candidate training attempt")
    parser.add_argument("--candidate-input-report", default="", help="Approved report from audit-candidate-training-input.py")
    parser.add_argument("--candidate-validation-report", default="", help="Deprecated legacy evidence; use --candidate-input-report")
    parser.add_argument("--dry-run", action="store_true", help="Validate config and print the resolved training plan")
    return parser


def parse_batch(value: str) -> int | float:
    normalized = value.strip().lower()
    if normalized == "auto":
        return -1
    try:
        numeric = float(normalized)
    except ValueError as error:
        raise ValueError("--batch must be auto, an integer, or a GPU-memory fraction") from error
    if numeric.is_integer():
        return int(numeric)
    if 0 < numeric < 1:
        return numeric
    raise ValueError("fractional --batch must be between 0 and 1")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def load_candidate_input_auditor() -> ModuleType:
    script_path = Path(__file__).with_name("audit-candidate-training-input.py")
    spec = importlib.util.spec_from_file_location(
        "audit_candidate_training_input", script_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load candidate training input auditor")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def candidate_input_validation(
    args: argparse.Namespace, dataset_yaml: Path, output_dir: Path
) -> dict[str, object] | None:
    if not args.candidate_mode:
        if args.candidate_input_report or args.candidate_validation_report:
            raise ValueError("candidate evidence requires --candidate-mode")
        return None
    if args.candidate_validation_report:
        raise ValueError(
            "--candidate-validation-report is legacy and cannot authorize candidate training; "
            "use --candidate-input-report"
        )
    if not args.candidate_input_report:
        raise ValueError("--candidate-mode requires --candidate-input-report")
    path = Path(args.candidate_input_report).resolve()
    auditor = load_candidate_input_auditor()
    report = auditor.verify_approved_report(path, dataset_yaml)
    counts = report.get("counts", {})
    if (
        int(counts.get("trainPositiveImages", -1)) < 100
        or int(counts.get("hardNegativeImages", -1)) < 100
        or int(counts.get("validationImages", -1)) < 30
        or int(counts.get("testImages", -1)) != 0
        or int(counts.get("orphanFiles", -1)) != 0
    ):
        raise ValueError("candidate training input count gate is not satisfied")
    dataset_root = Path(str(report.get("outputDir", ""))).resolve()
    if dataset_root != dataset_yaml.parent.resolve():
        raise ValueError("candidate training input dataset root does not match")
    if is_within(output_dir, dataset_root):
        raise ValueError("candidate training output must be outside the dataset root")
    inputs = report.get("inputs", {})
    validation_evidence = (
        inputs.get("validationDatasetYaml") if isinstance(inputs, dict) else None
    )
    if isinstance(validation_evidence, dict):
        validation_dataset = Path(str(validation_evidence.get("path", ""))).resolve()
        if is_within(output_dir, validation_dataset.parent):
            raise ValueError(
                "candidate training output must be outside the canonical validation dataset"
            )
    return {
        "path": str(path),
        "sha256": sha256(path),
        "decision": report["decision"],
        "materialization_report": inputs["materializationReport"],
        "dataset_files_sha256": report["datasetFilesSha256"],
        "all_roles_sha256": report["allRolesSha256"],
        "counts": counts,
    }


def main() -> None:
    args = build_parser().parse_args()
    batch = parse_batch(args.batch)
    dataset_yaml = Path(args.dataset).resolve()
    output_dir = Path(args.output_dir).resolve()
    config = load_dataset_config(dataset_yaml)
    candidate_input_evidence = candidate_input_validation(
        args, dataset_yaml, output_dir
    )
    runtime_dataset_yaml = output_dir / "resolved-dataset.yaml"

    summary = {
        "dataset_yaml": str(dataset_yaml),
        "dataset_root": str(config.dataset_root),
        "runtime_dataset_yaml": str(runtime_dataset_yaml),
        "train_images": count_files(config.dataset_root / config.train, (".jpg", ".jpeg", ".png", ".webp")),
        "val_images": count_files(config.dataset_root / config.val, (".jpg", ".jpeg", ".png", ".webp")),
        "test_images": count_files(config.dataset_root / config.test, (".jpg", ".jpeg", ".png", ".webp")),
        "task": config.task,
        "class_count": config.class_count,
        "names": config.names,
        "model": args.model,
        "epochs": args.epochs,
        "imgsz": args.imgsz,
        "batch": batch,
        "patience": args.patience,
        "device": args.device,
        "workers": args.workers,
        "run_name": args.run_name,
        "output_dir": str(output_dir),
        "run_dir": str(resolve_training_run_dir(output_dir, args.run_name)),
        "best_weights_path": str(resolve_best_weights_path(output_dir, args.run_name)),
        "training_intent": "candidate" if args.candidate_mode else "experiment",
        "candidate_input_evidence": candidate_input_evidence,
        "dry_run": args.dry_run,
    }

    if args.dry_run:
        print(__import__("json").dumps(summary, indent=2))
        return

    ultralytics = ensure_python_dependency("ultralytics", "pip install ultralytics")
    write_resolved_dataset_yaml(runtime_dataset_yaml, config)
    model = ultralytics.YOLO(args.model)
    output_dir.mkdir(parents=True, exist_ok=True)
    results = model.train(
        data=str(runtime_dataset_yaml),
        task="segment",
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=batch,
        patience=args.patience,
        device=args.device,
        workers=args.workers,
        project=str(output_dir),
        name=args.run_name,
    )
    results_dir = Path(getattr(results, "save_dir", output_dir)).resolve()
    actual_best_weights_path = results_dir / "weights" / "best.pt"
    if args.candidate_mode:
        # Re-run the full evidence chain after training so a dataset or upstream
        # mutation during the run cannot produce an eligible candidate summary.
        candidate_input_validation(args, dataset_yaml, output_dir)
    write_json(
        output_dir / "train-summary.json",
        {
            **summary,
            "results_dir": str(results_dir),
            "best_weights_path": str(actual_best_weights_path),
            "best_weights_sha256": (
                sha256(actual_best_weights_path)
                if actual_best_weights_path.is_file()
                else None
            ),
        },
    )
    print(f"Training finished. Summary written to {output_dir / 'train-summary.json'}")


if __name__ == "__main__":
    main()
