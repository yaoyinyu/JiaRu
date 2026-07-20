from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from _training_common import (
    ensure_python_dependency,
    load_dataset_config,
    resolve_best_weights_path,
    write_json,
    write_resolved_dataset_yaml,
)


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


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


def expected_split_stems(dataset_root: Path, split_path: str) -> list[str]:
    image_root = (dataset_root / split_path).resolve()
    if not image_root.is_dir():
        raise ValueError(f"evaluation split image directory is missing: {image_root}")
    stems = sorted(
        path.stem
        for path in image_root.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )
    if not stems or len(stems) != len(set(stems)):
        raise ValueError("evaluation split has no images or duplicate image stems")
    return stems


def prediction_records(
    artifacts_dir: Path, expected_stems: list[str]
) -> list[dict[str, Any]]:
    labels_root = artifacts_dir / "labels"
    labels = {
        path.stem: path
        for path in sorted(labels_root.glob("*.txt"))
        if path.is_file()
    } if labels_root.is_dir() else {}
    unknown = sorted(set(labels) - set(expected_stems))
    if unknown:
        raise ValueError(f"prediction labels contain unknown split images: {unknown}")
    records: list[dict[str, Any]] = []
    for stem in expected_stems:
        path = labels.get(stem)
        if path is None:
            records.append(
                {"stem": stem, "path": None, "sha256": None, "prediction_count": 0}
            )
            continue
        count = sum(
            1
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        if count <= 0:
            raise ValueError(f"prediction label is empty; record zero explicitly instead: {stem}")
        records.append(
            {
                "stem": stem,
                "path": path.relative_to(artifacts_dir).as_posix(),
                "sha256": sha256_file(path),
                "prediction_count": count,
            }
        )
    return records


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
    if not args.dry_run and not weights.is_file():
        raise FileNotFoundError(f"model weights are missing: {weights}")
    dataset_yaml_sha256 = sha256_file(dataset_yaml)
    weights_sha256 = sha256_file(weights) if weights.is_file() else None
    runtime_dataset_yaml = output.parent / "resolved-dataset.yaml"

    summary = {
        "dataset_yaml": str(dataset_yaml),
        "dataset_root": str(config.dataset_root),
        "dataset_yaml_sha256": dataset_yaml_sha256,
        "runtime_dataset_yaml": str(runtime_dataset_yaml),
        "weights": str(weights),
        "weights_sha256": weights_sha256,
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
    artifact_paths = sorted(
        item
        for item in resolved_artifacts_dir.rglob("*")
        if item.is_file() and item.name != "evaluation-artifacts.json"
    )
    artifact_files = [item.relative_to(resolved_artifacts_dir).as_posix() for item in artifact_paths]
    file_records = [
        {"path": item.relative_to(resolved_artifacts_dir).as_posix(), "sha256": sha256_file(item)}
        for item in artifact_paths
    ]
    split_path = str(getattr(config, args.split))
    explicit_prediction_records = prediction_records(
        resolved_artifacts_dir,
        expected_split_stems(config.dataset_root, split_path),
    )
    artifact_index_path = resolved_artifacts_dir / "evaluation-artifacts.json"
    artifact_index = {
        "schema_version": 1,
        "split": args.split,
        "artifacts_dir": str(resolved_artifacts_dir),
        "files": artifact_files,
        "file_records": file_records,
        "files_sha256": canonical_sha256(file_records),
        "prediction_records": explicit_prediction_records,
        "prediction_records_sha256": canonical_sha256(explicit_prediction_records),
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
            "index_sha256": sha256_file(artifact_index_path),
            "files_sha256": artifact_index["files_sha256"],
            "counts": artifact_index["counts"],
        },
    }
    write_json(output, payload)
    print(f"Evaluation finished. Metrics written to {output}")


if __name__ == "__main__":
    main()
