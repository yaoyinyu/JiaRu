from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from dataclasses import replace
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


def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def inventory_tree(root: Path) -> tuple[list[dict[str, str]], str]:
    if not root.is_dir():
        raise ValueError(f"dataset root is missing: {root}")
    records = [
        {"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)}
        for path in sorted(item for item in root.rglob("*") if item.is_file())
    ]
    return records, canonical_sha256(records)


def copy_source_file(source: Path, target: Path) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return "copy"


def resolve_split_roots(dataset_root: Path, split_path: str) -> tuple[Path, Path]:
    relative = Path(split_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"evaluation split path is unsafe: {split_path}")
    image_root = (dataset_root / relative).resolve()
    if not is_within(image_root, dataset_root):
        raise ValueError(f"evaluation image root escapes dataset: {image_root}")
    parts = list(relative.parts)
    try:
        images_index = parts.index("images")
    except ValueError:
        label_relative = Path("labels") / relative.name
    else:
        parts[images_index] = "labels"
        label_relative = Path(*parts)
    label_root = (dataset_root / label_relative).resolve()
    if not is_within(label_root, dataset_root):
        raise ValueError(f"evaluation label root escapes dataset: {label_root}")
    return image_root, label_root


def materialize_runtime_dataset(
    dataset_root: Path,
    split_path: str,
    split_name: str,
    runtime_root: Path,
) -> tuple[list[str], list[dict[str, str]]]:
    image_root, label_root = resolve_split_roots(dataset_root, split_path)
    image_paths = sorted(
        path
        for path in image_root.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )
    stems = [path.stem for path in image_paths]
    if not stems or len(stems) != len(set(stems)):
        raise ValueError("evaluation split has no images or duplicate image stems")
    records: list[dict[str, str]] = []
    for image_path in image_paths:
        relative = image_path.relative_to(image_root)
        label_path = label_root / relative.with_suffix(".txt")
        if not label_path.is_file():
            raise ValueError(f"evaluation label is missing: {label_path}")
        runtime_image = runtime_root / "images" / split_name / relative
        runtime_label = runtime_root / "labels" / split_name / relative.with_suffix(".txt")
        image_mode = copy_source_file(image_path, runtime_image)
        label_mode = copy_source_file(label_path, runtime_label)
        records.append(
            {
                "stem": image_path.stem,
                "sourceImage": str(image_path),
                "sourceImageSha256": sha256_file(image_path),
                "runtimeImage": runtime_image.relative_to(runtime_root).as_posix(),
                "runtimeImageSha256": sha256_file(runtime_image),
                "imageMaterialization": image_mode,
                "sourceLabel": str(label_path),
                "sourceLabelSha256": sha256_file(label_path),
                "runtimeLabel": runtime_label.relative_to(runtime_root).as_posix(),
                "runtimeLabelSha256": sha256_file(runtime_label),
                "labelMaterialization": label_mode,
            }
        )
    return sorted(stems), records


def expected_split_stems(dataset_root: Path, split_path: str) -> list[str]:
    image_root, _ = resolve_split_roots(dataset_root, split_path)
    if not image_root.is_dir():
        raise ValueError(f"evaluation split image directory is missing: {image_root}")
    stems = sorted(
        path.stem
        for path in image_root.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )
    if not stems or len(stems) != len(set(stems)):
        raise ValueError("evaluation split has no images or duplicate image stems")
    return stems


def prediction_records(
    artifacts_dir: Path, expected_stems: list[str]
) -> list[dict[str, Any]]:
    labels_root = artifacts_dir / "labels"
    label_paths = sorted(labels_root.rglob("*.txt")) if labels_root.is_dir() else []
    if len({path.stem for path in label_paths}) != len(label_paths):
        raise ValueError("prediction labels contain duplicate stems")
    labels = {path.stem: path for path in label_paths if path.is_file()}
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
    runtime_dataset_root = output.parent / "evaluation-runtime-dataset"
    runtime_dataset_yaml = runtime_dataset_root / "dataset.yaml"
    split_path = str(getattr(config, args.split))
    split_stems = expected_split_stems(config.dataset_root, split_path)

    summary = {
        "dataset_yaml": str(dataset_yaml),
        "dataset_root": str(config.dataset_root),
        "dataset_yaml_sha256": dataset_yaml_sha256,
        "runtime_dataset_yaml": str(runtime_dataset_yaml),
        "runtime_dataset_root": str(runtime_dataset_root),
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

    protected_outputs = (output, artifacts_dir, runtime_dataset_root)
    if any(is_within(item, config.dataset_root) for item in protected_outputs):
        raise ValueError("evaluation outputs must be outside the immutable source dataset root")
    for existing, label in (
        (output, "metrics output"),
        (runtime_dataset_root, "runtime dataset directory"),
        (artifacts_dir, "evaluation artifact directory"),
    ):
        if existing.exists():
            raise ValueError(f"{label} must not already exist: {existing}")

    source_inventory_before, source_inventory_sha256 = inventory_tree(config.dataset_root)
    for kind in ("images", "labels"):
        for split in ("train", "val", "test"):
            (runtime_dataset_root / kind / split).mkdir(parents=True, exist_ok=True)
    runtime_stems, runtime_records = materialize_runtime_dataset(
        config.dataset_root,
        split_path,
        args.split,
        runtime_dataset_root,
    )
    if runtime_stems != split_stems:
        raise ValueError("runtime dataset stems differ from the selected source split")
    runtime_config = replace(
        config,
        dataset_root=runtime_dataset_root,
        train="images/train",
        val="images/val",
        test="images/test",
    )
    write_resolved_dataset_yaml(runtime_dataset_yaml, runtime_config)
    source_inventory_after_materialization, source_hash_after_materialization = inventory_tree(
        config.dataset_root
    )
    if (
        source_inventory_after_materialization != source_inventory_before
        or source_hash_after_materialization != source_inventory_sha256
    ):
        raise ValueError("source dataset changed while materializing the runtime evaluation copy")

    ultralytics = ensure_python_dependency("ultralytics", "pip install ultralytics")
    model = ultralytics.YOLO(str(weights))
    artifacts_dir.parent.mkdir(parents=True, exist_ok=True)
    try:
        metrics = model.val(
            data=str(runtime_dataset_yaml),
            split=args.split,
            imgsz=args.imgsz,
            device=args.device,
            project=str(artifacts_dir.parent),
            name=artifacts_dir.name,
            exist_ok=False,
            plots=True,
            save_json=True,
            save_txt=True,
            save_conf=True,
        )
    finally:
        source_inventory_after, source_inventory_sha256_after = inventory_tree(
            config.dataset_root
        )
        if (
            source_inventory_after != source_inventory_before
            or source_inventory_sha256_after != source_inventory_sha256
        ):
            raise ValueError("immutable source dataset inventory or file hash changed during evaluation")
    runtime_inventory, runtime_inventory_sha256 = inventory_tree(runtime_dataset_root)
    resolved_artifacts_dir = Path(getattr(metrics, "save_dir", artifacts_dir)).resolve()
    if resolved_artifacts_dir != artifacts_dir:
        raise ValueError(
            "evaluation output directory drifted from the requested fresh artifact directory"
        )
    artifact_paths = list(
        item
        for item in resolved_artifacts_dir.rglob("*")
        if item.is_file() and item.name != "evaluation-artifacts.json"
    )
    artifact_paths.sort(
        key=lambda item: item.relative_to(resolved_artifacts_dir).as_posix()
    )
    artifact_files = [item.relative_to(resolved_artifacts_dir).as_posix() for item in artifact_paths]
    file_records = [
        {"path": item.relative_to(resolved_artifacts_dir).as_posix(), "sha256": sha256_file(item)}
        for item in artifact_paths
    ]
    explicit_prediction_records = prediction_records(
        resolved_artifacts_dir,
        split_stems,
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
        "source_dataset_inventory_sha256_before": source_inventory_sha256,
        "source_dataset_inventory_sha256_after": source_inventory_sha256_after,
        "source_dataset_unchanged": True,
        "runtime_dataset_inventory_sha256": runtime_inventory_sha256,
        "runtime_dataset_files": len(runtime_inventory),
        "runtime_materialization_records_sha256": canonical_sha256(runtime_records),
        "runtime_materialization_records": runtime_records,
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
