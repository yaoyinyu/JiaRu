#!/usr/bin/env python3
"""Materialize a frozen reviewed snapshot as an evaluation-only YOLO dataset.

The tool never changes the frozen snapshot and never assigns an item to a
training or validation split. It independently verifies snapshot hashes,
polygon validity, pairwise zero-overlap, and source isolation from the formal
training dataset before replacing the derived evaluation directory.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from PIL import Image
from shapely.geometry import Polygon


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Materialize a frozen release-test evaluation dataset.")
    parser.add_argument("--snapshot-root", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--training-dataset-root", default="model/datasets/nail-texture-v1")
    parser.add_argument("--training-sources", default="model/datasets/nail-texture-v1/metadata/sources.csv")
    parser.add_argument("--report", default="")
    return parser


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected an object: {path}")
    return value


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def safe_file_name(value: Any, field: str) -> str:
    file_name = str(value or "")
    if not file_name or Path(file_name).name != file_name or file_name in {".", ".."}:
        raise ValueError(f"Unsafe {field}: {file_name!r}")
    return file_name


def training_evidence(dataset_root: Path, sources_path: Path) -> tuple[set[str], set[str]]:
    if not sources_path.is_file():
        raise FileNotFoundError(f"Training sources are missing: {sources_path}")
    groups: set[str] = set()
    image_hashes: set[str] = set()
    with sources_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("Training sources are empty")
    for row_index, row in enumerate(rows, start=2):
        group = str(row.get("sourceGroup") or "").strip()
        image_ref = str(row.get("imagePath") or "").strip()
        if not group or not image_ref:
            raise ValueError(f"Training source row {row_index} lacks sourceGroup or imagePath")
        image_path = Path(image_ref)
        if not image_path.is_absolute():
            image_path = dataset_root / image_path
        if not image_path.is_file():
            raise FileNotFoundError(f"Training source image is missing at row {row_index}: {image_path}")
        groups.add(group)
        image_hashes.add(sha256_path(image_path))
    return groups, image_hashes


def validate_polygons(document: dict[str, Any], expected_masks: int, file_name: str) -> list[str]:
    image = document.get("image")
    annotations = document.get("annotations")
    if document.get("version") != "nail-texture-dataset/v1" or not isinstance(image, dict):
        raise ValueError(f"{file_name}: unsupported annotation document")
    if image.get("fileName") != file_name:
        raise ValueError(f"{file_name}: annotation image fileName mismatch")
    width = int(image.get("width") or 0)
    height = int(image.get("height") or 0)
    if width <= 0 or height <= 0 or not isinstance(annotations, list):
        raise ValueError(f"{file_name}: invalid image dimensions or annotations")
    if len(annotations) != expected_masks:
        raise ValueError(f"{file_name}: expected {expected_masks} masks, found {len(annotations)}")

    lines: list[str] = []
    polygons: list[Polygon] = []
    for index, annotation in enumerate(annotations, start=1):
        points = annotation.get("polygon") if isinstance(annotation, dict) else None
        if not isinstance(points, list) or len(points) < 3:
            raise ValueError(f"{file_name}: nail {index} has fewer than three points")
        coords: list[tuple[float, float]] = []
        normalized: list[str] = []
        for point_index, point in enumerate(points, start=1):
            if not isinstance(point, dict):
                raise ValueError(f"{file_name}: nail {index} point {point_index} is invalid")
            x = float(point.get("x"))
            y = float(point.get("y"))
            if x < 0 or y < 0 or x > width or y > height:
                raise ValueError(f"{file_name}: nail {index} point {point_index} is out of bounds")
            coords.append((x, y))
            normalized.extend((f"{x / width:.8f}", f"{y / height:.8f}"))
        polygon = Polygon(coords)
        if not polygon.is_valid or polygon.area <= 0:
            raise ValueError(f"{file_name}: nail {index} polygon is invalid")
        polygons.append(polygon)
        lines.append(" ".join(["0", *normalized]))

    for first in range(len(polygons)):
        for second in range(first + 1, len(polygons)):
            overlap = polygons[first].intersection(polygons[second]).area
            if overlap > 1e-6:
                raise ValueError(
                    f"{file_name}: nails {first + 1}/{second + 1} overlap by {overlap:.6f} pixels"
                )
    return lines


def ensure_safe_output(output_dir: Path) -> None:
    cwd = Path.cwd().resolve()
    if output_dir == cwd or output_dir == output_dir.anchor or output_dir.parent == output_dir:
        raise ValueError(f"Unsafe output directory: {output_dir}")


def main() -> None:
    args = build_parser().parse_args()
    snapshot_root = Path(args.snapshot_root).resolve()
    output_dir = Path(args.output_dir).resolve()
    dataset_root = Path(args.training_dataset_root).resolve()
    sources_path = Path(args.training_sources).resolve()
    report_path = Path(args.report).resolve() if args.report else output_dir.with_name(f"{output_dir.name}-report.json")
    ensure_safe_output(output_dir)

    manifest_path = snapshot_root / "manifest.json"
    manifest = load_json(manifest_path)
    items = manifest.get("items")
    if manifest.get("decision") != "frozen_reviewed_candidate_not_release_ready":
        raise ValueError("Snapshot decision is not a frozen reviewed candidate")
    if manifest.get("trainingUse") != "prohibited" or not isinstance(items, list) or not items:
        raise ValueError("Snapshot must be non-empty and trainingUse must be prohibited")
    if canonical_sha256(items) != manifest.get("itemsSha256"):
        raise ValueError("Snapshot itemsSha256 mismatch")
    if int((manifest.get("counts") or {}).get("images") or 0) != len(items):
        raise ValueError("Snapshot image count does not match manifest items")

    training_groups, training_hashes = training_evidence(dataset_root, sources_path)
    frozen_groups = {str(item.get("parentSourceGroup") or "") for item in items if isinstance(item, dict)}
    group_overlap = sorted(frozen_groups & training_groups)
    if group_overlap:
        raise ValueError(f"Frozen parent source groups overlap training data: {group_overlap}")

    temporary = output_dir.with_name(f"{output_dir.name}.tmp")
    if temporary.exists():
        shutil.rmtree(temporary)
    (temporary / "images" / "test" / "core").mkdir(parents=True)
    (temporary / "images" / "test" / "stress").mkdir(parents=True)
    (temporary / "images" / "empty").mkdir(parents=True)
    (temporary / "labels" / "test" / "core").mkdir(parents=True)
    (temporary / "labels" / "test" / "stress").mkdir(parents=True)
    (temporary / "labels" / "empty").mkdir(parents=True)

    records: list[dict[str, Any]] = []
    frozen_hashes: set[str] = set()
    seen_targets: set[str] = set()
    total_masks = 0
    try:
        for item_index, item in enumerate(items, start=1):
            if not isinstance(item, dict) or item.get("trainingUse") != "prohibited":
                raise ValueError(f"Snapshot item {item_index} is not training-prohibited")
            lane = str(item.get("lane") or "")
            if lane not in {"core", "stress"}:
                raise ValueError(f"Snapshot item {item_index} has unsupported lane: {lane}")
            file_name = safe_file_name(item.get("fileName"), "fileName")
            annotation_name = f"{Path(file_name).stem}.json"
            image_path = snapshot_root / "images" / lane / file_name
            annotation_path = snapshot_root / "annotations" / lane / annotation_name
            if not image_path.is_file() or not annotation_path.is_file():
                raise FileNotFoundError(f"Frozen pair is incomplete: {lane}/{file_name}")
            image_sha256 = sha256_path(image_path)
            annotation_sha256 = sha256_path(annotation_path)
            if image_sha256 != item.get("imageSha256") or annotation_sha256 != item.get("annotationSha256"):
                raise ValueError(f"Frozen pair hash mismatch: {lane}/{file_name}")
            if canonical_sha256({"imageSha256": image_sha256, "annotationSha256": annotation_sha256}) != item.get("imageAnnotationPairSha256"):
                raise ValueError(f"Frozen pair joint hash mismatch: {lane}/{file_name}")
            if image_sha256 in training_hashes:
                raise ValueError(f"Frozen image exactly duplicates formal training data: {lane}/{file_name}")
            frozen_hashes.add(image_sha256)

            document = load_json(annotation_path)
            if str((document.get("image") or {}).get("sourceGroup") or "") != str(item.get("sourceGroup") or ""):
                raise ValueError(f"{file_name}: annotation sourceGroup mismatch")
            with Image.open(image_path) as image:
                actual_size = image.size
                image.verify()
            if actual_size != (int(item.get("width") or 0), int(item.get("height") or 0)):
                raise ValueError(f"{file_name}: frozen image dimensions mismatch")

            mask_count = int(item.get("maskCount") or 0)
            lines = validate_polygons(document, mask_count, file_name)
            target_name = file_name
            target_key = f"{lane}/{target_name}"
            if target_key in seen_targets:
                raise ValueError(f"Duplicate evaluation target: {target_key}")
            seen_targets.add(target_key)
            label_name = f"{Path(target_name).stem}.txt"
            image_target = temporary / "images" / "test" / lane / target_name
            label_target = temporary / "labels" / "test" / lane / label_name
            shutil.copy2(image_path, image_target)
            label_target.write_text("\n".join(lines) + "\n", encoding="utf-8")
            total_masks += mask_count
            records.append({
                "lane": lane,
                "sourceFileName": file_name,
                "materializedFileName": target_name,
                "parentSourceGroup": item.get("parentSourceGroup"),
                "maskCount": mask_count,
                "sourceImageSha256": image_sha256,
                "sourceAnnotationSha256": annotation_sha256,
                "materializedImageSha256": sha256_path(image_target),
                "materializedLabelSha256": sha256_path(label_target),
            })

        expected_masks = int((manifest.get("counts") or {}).get("masks") or 0)
        if total_masks != expected_masks:
            raise ValueError(f"Snapshot mask count mismatch: expected {expected_masks}, found {total_masks}")
        def dataset_yaml(test_path: str) -> str:
            return "\n".join([
                "path: .",
                "train: images/empty",
                "val: images/empty",
                f"test: {test_path}",
                "",
                "names:",
                "  0: nail_texture",
                "",
                "task: segment",
                "class_count: 1",
                "image_size: 512",
                "",
            ])

        yaml = dataset_yaml("images/test")
        (temporary / "dataset.yaml").write_text(yaml, encoding="utf-8")
        (temporary / "dataset.core.yaml").write_text(dataset_yaml("images/test/core"), encoding="utf-8")
        (temporary / "dataset.stress.yaml").write_text(dataset_yaml("images/test/stress"), encoding="utf-8")
        evaluation_manifest = {
            "schemaVersion": 1,
            "decision": "evaluation_only_frozen_reviewed_snapshot",
            "trainingUse": "prohibited",
            "sourceSnapshotId": manifest.get("snapshotId"),
            "sourceItemsSha256": manifest.get("itemsSha256"),
            "counts": {"images": len(records), "masks": total_masks, "parentSourceGroups": len(frozen_groups)},
            "sourceIsolation": {
                "trainingSourceGroups": len(training_groups),
                "trainingImageHashes": len(training_hashes),
                "parentSourceGroupOverlap": group_overlap,
                "exactImageHashOverlap": sorted(frozen_hashes & training_hashes),
            },
            "recordsSha256": canonical_sha256(records),
            "records": records,
        }
        (temporary / "evaluation-manifest.json").write_text(
            json.dumps(evaluation_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        if output_dir.exists():
            shutil.rmtree(output_dir)
        temporary.replace(output_dir)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise

    report = {
        "ok": True,
        "decision": "evaluation_only_frozen_reviewed_snapshot",
        "trainingUse": "prohibited",
        "snapshotRoot": str(snapshot_root),
        "outputDir": str(output_dir),
        "datasetYaml": str(output_dir / "dataset.yaml"),
        "coreDatasetYaml": str(output_dir / "dataset.core.yaml"),
        "stressDatasetYaml": str(output_dir / "dataset.stress.yaml"),
        "evaluationManifest": str(output_dir / "evaluation-manifest.json"),
        "counts": {"images": len(records), "masks": total_masks, "parentSourceGroups": len(frozen_groups)},
        "sourceIsolation": {
            "trainingSourceGroups": len(training_groups),
            "trainingImageHashes": len(training_hashes),
            "parentSourceGroupOverlap": group_overlap,
            "exactImageHashOverlap": sorted(frozen_hashes & training_hashes),
        },
        "recordsSha256": canonical_sha256(records),
        "errors": [],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
