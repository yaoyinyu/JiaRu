#!/usr/bin/env python3
"""Materialize a frozen reviewed snapshot as an evaluation-only YOLO dataset.

The source snapshot and formal training identities are treated only as inputs:
all hashes, polygons, split contents, and isolation claims are recomputed before
an output directory is committed.  Both the dataset and its external report are
staged transactionally and an existing target is never reused.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image
from shapely.geometry import Polygon


SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Materialize a frozen release-test evaluation dataset."
    )
    parser.add_argument("--snapshot-root")
    parser.add_argument("--output-dir")
    parser.add_argument(
        "--training-dataset-root", default="model/datasets/nail-texture-v1"
    )
    parser.add_argument(
        "--training-sources",
        default="model/datasets/nail-texture-v1/metadata/sources.csv",
    )
    parser.add_argument("--report", default="")
    parser.add_argument(
        "--verify-report",
        help="deeply replay an existing materialization report without writing output",
    )
    parser.add_argument(
        "--expected-dataset",
        help="optional dataset.yaml path that the verified report must bind",
    )
    return parser


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Unreadable JSON: {path}: {error}") from error
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
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def require_sha256(value: Any, field: str) -> str:
    digest = str(value or "")
    if not SHA256_PATTERN.fullmatch(digest):
        raise ValueError(f"Invalid {field}: {digest!r}")
    return digest


def safe_file_name(value: Any, field: str) -> str:
    file_name = str(value or "")
    if (
        not file_name
        or Path(file_name).name != file_name
        or file_name in {".", ".."}
        or any(separator in file_name for separator in ("/", "\\"))
    ):
        raise ValueError(f"Unsafe {field}: {file_name!r}")
    return file_name


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def require_nonempty_text(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"Missing {field}")
    return text


def training_evidence(
    dataset_root: Path, sources_path: Path
) -> tuple[list[dict[str, str]], set[str], set[str], set[str]]:
    if not dataset_root.is_dir():
        raise FileNotFoundError(f"Training dataset root is missing: {dataset_root}")
    if not sources_path.is_file():
        raise FileNotFoundError(f"Training sources are missing: {sources_path}")
    groups: set[str] = set()
    image_hashes: set[str] = set()
    file_names: set[str] = set()
    identities: list[dict[str, str]] = []
    with sources_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("Training sources are empty")
    for row_index, row in enumerate(rows, start=2):
        group = require_nonempty_text(
            row.get("sourceGroup"), f"training source row {row_index} sourceGroup"
        )
        image_ref = require_nonempty_text(
            row.get("imagePath"), f"training source row {row_index} imagePath"
        )
        image_path = Path(image_ref)
        if not image_path.is_absolute():
            image_path = (dataset_root / image_path).resolve()
        else:
            image_path = image_path.resolve()
        if not image_path.is_file():
            raise FileNotFoundError(
                f"Training source image is missing at row {row_index}: {image_path}"
            )
        file_name = safe_file_name(
            row.get("fileName") or image_path.name,
            f"training source row {row_index} fileName",
        )
        image_sha256 = sha256_path(image_path)
        declared_hash = str(row.get("imageSha256") or "").strip()
        if declared_hash and require_sha256(
            declared_hash, f"training source row {row_index} imageSha256"
        ) != image_sha256:
            raise ValueError(
                f"Training source row {row_index} image SHA-256 drift: {image_path}"
            )
        groups.add(group)
        image_hashes.add(image_sha256)
        file_names.add(file_name)
        identities.append(
            {
                "fileName": file_name,
                "sourceGroup": group,
                "imagePath": str(image_path),
                "imageSha256": image_sha256,
            }
        )
    identities.sort(
        key=lambda item: (
            item["fileName"],
            item["sourceGroup"],
            item["imagePath"],
        )
    )
    return identities, groups, image_hashes, file_names


def validate_polygons(
    document: dict[str, Any], expected_masks: int, file_name: str
) -> list[str]:
    image = document.get("image")
    annotations = document.get("annotations")
    if document.get("version") != "nail-texture-dataset/v1" or not isinstance(
        image, dict
    ):
        raise ValueError(f"{file_name}: unsupported annotation document")
    if image.get("fileName") != file_name:
        raise ValueError(f"{file_name}: annotation image fileName mismatch")
    width = int(image.get("width") or 0)
    height = int(image.get("height") or 0)
    if width <= 0 or height <= 0 or not isinstance(annotations, list):
        raise ValueError(f"{file_name}: invalid image dimensions or annotations")
    if expected_masks < 1 or len(annotations) != expected_masks:
        raise ValueError(
            f"{file_name}: expected {expected_masks} masks, found {len(annotations)}"
        )

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
                raise ValueError(
                    f"{file_name}: nail {index} point {point_index} is invalid"
                )
            try:
                x = float(point.get("x"))
                y = float(point.get("y"))
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"{file_name}: nail {index} point {point_index} is invalid"
                ) from error
            if x < 0 or y < 0 or x > width or y > height:
                raise ValueError(
                    f"{file_name}: nail {index} point {point_index} is out of bounds"
                )
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
            if overlap > 0:
                raise ValueError(
                    f"{file_name}: nails {first + 1}/{second + 1} overlap "
                    f"by {overlap:.12f} pixels"
                )
    return lines


def inventory(root: Path) -> list[dict[str, str]]:
    paths = [item for item in root.rglob("*") if item.is_file()]
    paths.sort(key=lambda item: item.relative_to(root).as_posix())
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "sha256": sha256_path(path),
        }
        for path in paths
    ]


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def ensure_safe_targets(
    snapshot_root: Path,
    dataset_root: Path,
    output_dir: Path,
    report_path: Path,
    input_files: list[Path],
) -> None:
    cwd = Path.cwd().resolve()
    if output_dir in {cwd, Path(output_dir.anchor)} or output_dir.parent == output_dir:
        raise ValueError(f"Unsafe output directory: {output_dir}")
    if output_dir.exists():
        raise ValueError(f"Output directory must not already exist: {output_dir}")
    if is_within(output_dir, snapshot_root) or is_within(snapshot_root, output_dir):
        raise ValueError("Output directory must be separate from the source snapshot")
    if is_within(output_dir, dataset_root) or is_within(dataset_root, output_dir):
        raise ValueError("Output directory must be separate from the training dataset")
    if report_path.exists():
        raise ValueError(f"Report target must not already exist: {report_path}")
    if is_within(report_path, output_dir):
        raise ValueError("Report target must not be inside the output directory")
    if report_path in {path.resolve() for path in input_files}:
        raise ValueError("Report target must not overwrite an input file")
    if is_within(report_path, snapshot_root) or is_within(report_path, dataset_root):
        raise ValueError("Report target must be separate from source inputs")


def assert_output_tree(
    root: Path, expected_images: dict[str, set[str]], expected_labels: dict[str, set[str]]
) -> None:
    for split in ("train", "val"):
        image_files = [item for item in (root / "images" / split).rglob("*") if item.is_file()]
        label_files = [item for item in (root / "labels" / split).rglob("*") if item.is_file()]
        if image_files or label_files:
            raise ValueError(f"Evaluation-only dataset has non-empty {split} split")
    for lane in ("core", "stress"):
        image_root = root / "images" / "test" / lane
        label_root = root / "labels" / "test" / lane
        actual_images = {
            item.relative_to(image_root).as_posix()
            for item in image_root.rglob("*")
            if item.is_file()
        }
        actual_labels = {
            item.relative_to(label_root).as_posix()
            for item in label_root.rglob("*")
            if item.is_file()
        }
        if actual_images != expected_images[lane]:
            raise ValueError(
                f"Evaluation image {lane} orphan/missing: "
                f"{sorted(actual_images ^ expected_images[lane])}"
            )
        if actual_labels != expected_labels[lane]:
            raise ValueError(
                f"Evaluation label {lane} orphan/missing: "
                f"{sorted(actual_labels ^ expected_labels[lane])}"
            )
    if not any(expected_images.values()):
        raise ValueError("Evaluation test split must not be empty")


def dataset_yaml(test_path: str) -> str:
    return "\n".join(
        [
            "path: .",
            "train: images/train",
            "val: images/val",
            f"test: {test_path}",
            "",
            "names:",
            "  0: nail_texture",
            "",
            "task: segment",
            "class_count: 1",
            "image_size: 512",
            "",
        ]
    )


def require_artifact(
    artifacts: dict[str, Any], key: str, expected_path: Path
) -> str:
    value = artifacts.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"Report artifact {key} is missing")
    reported_path = Path(str(value.get("path") or "")).resolve()
    if reported_path != expected_path.resolve():
        raise ValueError(
            f"Report artifact {key} path mismatch: {reported_path} != {expected_path}"
        )
    expected_sha256 = require_sha256(value.get("sha256"), f"artifact {key} sha256")
    if not expected_path.is_file():
        raise FileNotFoundError(f"Report artifact {key} is missing: {expected_path}")
    actual_sha256 = sha256_path(expected_path)
    if actual_sha256 != expected_sha256:
        raise ValueError(
            f"Report artifact {key} SHA-256 drift: "
            f"expected={expected_sha256} actual={actual_sha256}"
        )
    return actual_sha256


def verify_evaluation_report(
    report_path: Path | str, expected_dataset: Path | str | None = None
) -> dict[str, Any]:
    """Deeply replay a frozen evaluation report without trusting its PASS flag."""

    resolved_report = Path(report_path).resolve()
    if not resolved_report.is_file():
        raise FileNotFoundError(f"Evaluation report is missing: {resolved_report}")
    report_sha256 = sha256_path(resolved_report)
    report = load_json(resolved_report)
    if (
        report.get("schemaVersion") != 2
        or report.get("ok") is not True
        or report.get("status") != "PASS"
        or report.get("decision") != "evaluation_only_frozen_reviewed_snapshot"
        or report.get("trainingUse") != "prohibited"
    ):
        raise ValueError("Report is not a supported PASS frozen evaluation report")

    inputs = report.get("inputs")
    artifacts = report.get("artifacts")
    if not isinstance(inputs, dict) or not isinstance(artifacts, dict):
        raise ValueError("Report inputs/artifacts are missing")
    frozen_input = inputs.get("sourceFrozenManifest")
    training_input = inputs.get("trainingSources")
    if not isinstance(frozen_input, dict) or not isinstance(training_input, dict):
        raise ValueError("Report sourceFrozenManifest/trainingSources inputs are missing")

    manifest_path = Path(str(frozen_input.get("path") or "")).resolve()
    snapshot_root = manifest_path.parent
    dataset_root = Path(str(inputs.get("trainingDatasetRoot") or "")).resolve()
    sources_path = Path(str(training_input.get("path") or "")).resolve()
    output_dir = Path(str(report.get("outputDir") or "")).resolve()
    dataset_path = Path(str(report.get("datasetYaml") or "")).resolve()
    core_dataset_path = Path(str(report.get("coreDatasetYaml") or "")).resolve()
    stress_dataset_path = Path(str(report.get("stressDatasetYaml") or "")).resolve()
    evaluation_manifest_path = Path(
        str(report.get("evaluationManifest") or "")
    ).resolve()
    if dataset_path != output_dir / "dataset.yaml":
        raise ValueError("Report datasetYaml is not outputDir/dataset.yaml")
    if core_dataset_path != output_dir / "dataset.core.yaml":
        raise ValueError("Report coreDatasetYaml path mismatch")
    if stress_dataset_path != output_dir / "dataset.stress.yaml":
        raise ValueError("Report stressDatasetYaml path mismatch")
    if evaluation_manifest_path != output_dir / "evaluation-manifest.json":
        raise ValueError("Report evaluationManifest path mismatch")
    if expected_dataset is not None and Path(expected_dataset).resolve() != dataset_path:
        raise ValueError(
            f"Expected dataset mismatch: {Path(expected_dataset).resolve()} != {dataset_path}"
        )
    if not output_dir.is_dir():
        raise FileNotFoundError(f"Evaluation output directory is missing: {output_dir}")
    if Path(str(report.get("snapshotRoot") or "")).resolve() != snapshot_root:
        raise ValueError("Report snapshotRoot differs from source manifest parent")
    if is_within(output_dir, snapshot_root) or is_within(output_dir, dataset_root):
        raise ValueError("Reported output directory overlaps a source directory")
    if is_within(resolved_report, output_dir):
        raise ValueError("Evaluation report must remain external to the output directory")

    source_manifest_sha256 = require_sha256(
        frozen_input.get("sha256"), "source frozen manifest sha256"
    )
    if not manifest_path.is_file() or sha256_path(manifest_path) != source_manifest_sha256:
        raise ValueError("Source frozen manifest SHA-256 drift")
    if (
        report.get("sourceFrozenManifest") != str(manifest_path)
        or report.get("sourceFrozenManifestSha256") != source_manifest_sha256
    ):
        raise ValueError("Top-level source frozen manifest binding differs from inputs")
    source_items_sha256 = require_sha256(
        frozen_input.get("itemsSha256"), "source itemsSha256"
    )
    if report.get("sourceItemsSha256") != source_items_sha256:
        raise ValueError("Top-level sourceItemsSha256 differs from inputs")

    training_sources_sha256 = require_sha256(
        training_input.get("sha256"), "training sources sha256"
    )
    if not sources_path.is_file() or sha256_path(sources_path) != training_sources_sha256:
        raise ValueError("Training sources SHA-256 drift")
    (
        training_identities,
        training_groups,
        training_hashes,
        training_file_names,
    ) = training_evidence(dataset_root, sources_path)
    training_identities_sha256 = canonical_sha256(training_identities)
    if training_input.get("identitiesSha256") != training_identities_sha256:
        raise ValueError("Training identity aggregate SHA-256 drift")

    manifest = load_json(manifest_path)
    items = manifest.get("items")
    counts = manifest.get("counts")
    if (
        manifest.get("decision") != "frozen_reviewed_candidate_not_release_ready"
        or manifest.get("trainingUse") != "prohibited"
        or not isinstance(items, list)
        or not items
        or not isinstance(counts, dict)
    ):
        raise ValueError("Current frozen manifest is not an eligible non-empty snapshot")
    if manifest.get("itemsSha256") != source_items_sha256:
        raise ValueError("Current frozen manifest itemsSha256 differs from report")
    if canonical_sha256(items) != source_items_sha256:
        raise ValueError("Current frozen manifest itemsSha256 does not match items")
    if int(counts.get("images") or 0) != len(items):
        raise ValueError("Current frozen manifest image count mismatch")

    replay_records: list[dict[str, Any]] = []
    frozen_groups: set[str] = set()
    frozen_identity_groups: set[str] = set()
    frozen_hashes: set[str] = set()
    frozen_file_names: set[str] = set()
    seen_targets: set[str] = set()
    lane_counts = {"core": 0, "stress": 0}
    total_masks = 0
    expected_images = {"core": set(), "stress": set()}
    expected_labels = {"core": set(), "stress": set()}
    seen_label_targets: set[str] = set()
    for item_index, item in enumerate(items, start=1):
        if not isinstance(item, dict) or item.get("trainingUse") != "prohibited":
            raise ValueError(f"Snapshot item {item_index} is not training-prohibited")
        lane = str(item.get("lane") or "")
        if lane not in lane_counts:
            raise ValueError(f"Snapshot item {item_index} has unsupported lane: {lane}")
        file_name = safe_file_name(item.get("fileName"), "fileName")
        target_key = f"{lane}/{file_name}"
        if target_key in seen_targets:
            raise ValueError(f"Duplicate evaluation target: {target_key}")
        seen_targets.add(target_key)
        source_group = require_nonempty_text(
            item.get("sourceGroup"), f"snapshot item {item_index} sourceGroup"
        )
        parent_source_group = require_nonempty_text(
            item.get("parentSourceGroup"),
            f"snapshot item {item_index} parentSourceGroup",
        )
        image_path = snapshot_root / "images" / lane / file_name
        annotation_path = (
            snapshot_root / "annotations" / lane / f"{Path(file_name).stem}.json"
        )
        if not image_path.is_file() or not annotation_path.is_file():
            raise FileNotFoundError(f"Frozen pair is incomplete: {target_key}")
        image_sha256 = sha256_path(image_path)
        annotation_sha256 = sha256_path(annotation_path)
        if image_sha256 != require_sha256(
            item.get("imageSha256"), f"{target_key} imageSha256"
        ) or annotation_sha256 != require_sha256(
            item.get("annotationSha256"), f"{target_key} annotationSha256"
        ):
            raise ValueError(f"Frozen pair hash mismatch: {target_key}")
        pair_sha256 = canonical_sha256(
            {"imageSha256": image_sha256, "annotationSha256": annotation_sha256}
        )
        if pair_sha256 != require_sha256(
            item.get("imageAnnotationPairSha256"),
            f"{target_key} imageAnnotationPairSha256",
        ):
            raise ValueError(f"Frozen pair joint hash mismatch: {target_key}")
        document = load_json(annotation_path)
        document_image = document.get("image")
        if not isinstance(document_image, dict):
            raise ValueError(f"{file_name}: annotation image identity is missing")
        if str(document_image.get("sourceGroup") or "") != source_group:
            raise ValueError(f"{file_name}: annotation sourceGroup mismatch")
        width = int(item.get("width") or 0)
        height = int(item.get("height") or 0)
        if (
            int(document_image.get("width") or 0) != width
            or int(document_image.get("height") or 0) != height
        ):
            raise ValueError(f"{file_name}: annotation dimensions mismatch manifest")
        with Image.open(image_path) as image:
            actual_size = image.size
            image.verify()
        if actual_size != (width, height):
            raise ValueError(f"{file_name}: frozen image dimensions mismatch")
        mask_count = int(item.get("maskCount") or 0)
        lines = validate_polygons(document, mask_count, file_name)
        label_text = "\n".join(lines) + "\n"

        image_relative = f"images/test/{lane}/{file_name}"
        label_name = f"{Path(file_name).stem}.txt"
        label_relative = f"labels/test/{lane}/{label_name}"
        if label_relative in seen_label_targets:
            raise ValueError(f"Duplicate evaluation label target: {label_relative}")
        seen_label_targets.add(label_relative)
        image_target = output_dir / image_relative
        label_target = output_dir / label_relative
        if not image_target.is_file() or not label_target.is_file():
            raise FileNotFoundError(f"Materialized pair is incomplete: {target_key}")
        materialized_image_sha256 = sha256_path(image_target)
        materialized_label_sha256 = sha256_path(label_target)
        if materialized_image_sha256 != image_sha256:
            raise ValueError(f"Materialized image hash drift: {target_key}")
        if label_target.read_text(encoding="utf-8") != label_text:
            raise ValueError(f"Materialized label content drift: {target_key}")

        lane_counts[lane] += 1
        total_masks += mask_count
        frozen_groups.add(parent_source_group)
        frozen_identity_groups.update((source_group, parent_source_group))
        frozen_hashes.add(image_sha256)
        frozen_file_names.add(file_name)
        expected_images[lane].add(file_name)
        expected_labels[lane].add(label_name)
        replay_records.append(
            {
                "lane": lane,
                "sourceFileName": file_name,
                "materializedFileName": file_name,
                "sourceGroup": source_group,
                "parentSourceGroup": parent_source_group,
                "width": width,
                "height": height,
                "maskCount": mask_count,
                "sourceImage": str(image_path),
                "sourceAnnotation": str(annotation_path),
                "sourceImageSha256": image_sha256,
                "sourceAnnotationSha256": annotation_sha256,
                "sourceImageAnnotationPairSha256": pair_sha256,
                "materializedImage": image_relative,
                "materializedLabel": label_relative,
                "materializedImageSha256": materialized_image_sha256,
                "materializedLabelSha256": materialized_label_sha256,
            }
        )

    replay_records.sort(key=lambda item: (item["lane"], item["sourceFileName"]))
    if total_masks != int(counts.get("masks") or 0):
        raise ValueError("Current frozen manifest mask count mismatch")
    for lane, count_key in (("core", "coreImages"), ("stress", "stressImages")):
        if count_key in counts and int(counts.get(count_key) or 0) != lane_counts[lane]:
            raise ValueError(f"Current frozen manifest {count_key} count mismatch")

    group_overlap = sorted(frozen_identity_groups & training_groups)
    exact_hash_overlap = sorted(frozen_hashes & training_hashes)
    file_name_overlap = sorted(frozen_file_names & training_file_names)
    if group_overlap or exact_hash_overlap or file_name_overlap:
        raise ValueError(
            "Frozen evaluation identity overlaps training data: "
            f"sourceGroups={group_overlap} imageSha256={exact_hash_overlap} "
            f"fileNames={file_name_overlap}"
        )
    source_isolation = {
        "trainingIdentities": len(training_identities),
        "trainingIdentitiesSha256": training_identities_sha256,
        "trainingSourceGroups": len(training_groups),
        "trainingImageHashes": len(training_hashes),
        "trainingFileNames": len(training_file_names),
        "sourceGroupOverlap": group_overlap,
        "parentSourceGroupOverlap": sorted(frozen_groups & training_groups),
        "exactImageHashOverlap": exact_hash_overlap,
        "fileNameOverlap": file_name_overlap,
    }
    if report.get("sourceIsolation") != source_isolation:
        raise ValueError("Report sourceIsolation evidence differs from replay")
    if report.get("records") != replay_records:
        raise ValueError("Report records differ from replayed source/output identities")
    records_sha256 = canonical_sha256(replay_records)
    if report.get("recordsSha256") != records_sha256:
        raise ValueError("Report recordsSha256 mismatch")

    expected_counts = {
        "images": len(replay_records),
        "masks": total_masks,
        "coreImages": lane_counts["core"],
        "stressImages": lane_counts["stress"],
        "trainImages": 0,
        "validationImages": 0,
        "testImages": len(replay_records),
        "parentSourceGroups": len(frozen_groups),
    }
    if report.get("counts") != expected_counts:
        raise ValueError("Report counts differ from replay")
    assert_output_tree(output_dir, expected_images, expected_labels)
    expected_yaml = {
        dataset_path: dataset_yaml("images/test"),
        core_dataset_path: dataset_yaml("images/test/core"),
        stress_dataset_path: dataset_yaml("images/test/stress"),
    }
    for path, text in expected_yaml.items():
        if not path.is_file() or path.read_text(encoding="utf-8") != text:
            raise ValueError(f"Dataset YAML contract drift: {path}")

    dataset_yaml_sha256 = require_artifact(artifacts, "datasetYaml", dataset_path)
    require_artifact(artifacts, "coreDatasetYaml", core_dataset_path)
    require_artifact(artifacts, "stressDatasetYaml", stress_dataset_path)
    evaluation_manifest_sha256 = require_artifact(
        artifacts, "evaluationManifest", evaluation_manifest_path
    )
    evaluation_manifest = load_json(evaluation_manifest_path)
    expected_evaluation_manifest = {
        "schemaVersion": 2,
        "decision": "evaluation_only_frozen_reviewed_snapshot",
        "trainingUse": "prohibited",
        "sourceSnapshotId": manifest.get("snapshotId"),
        "sourceSnapshotManifest": {
            "path": str(manifest_path),
            "sha256": source_manifest_sha256,
        },
        "sourceItemsSha256": source_items_sha256,
        "counts": expected_counts,
        "sourceIsolation": source_isolation,
        "recordsSha256": records_sha256,
        "records": replay_records,
    }
    if evaluation_manifest != expected_evaluation_manifest:
        raise ValueError("Evaluation manifest differs from replay")

    file_records = inventory(output_dir)
    files_sha256 = canonical_sha256(file_records)
    expected_file_paths = {
        "dataset.yaml",
        "dataset.core.yaml",
        "dataset.stress.yaml",
        "evaluation-manifest.json",
        *(record["materializedImage"] for record in replay_records),
        *(record["materializedLabel"] for record in replay_records),
    }
    actual_file_paths = {record["path"] for record in file_records}
    if actual_file_paths != expected_file_paths:
        raise ValueError(
            "Evaluation output has unexpected or missing files: "
            f"{sorted(actual_file_paths ^ expected_file_paths)}"
        )
    if (
        report.get("file_records") != file_records
        or report.get("datasetFiles") != file_records
        or report.get("files_sha256") != files_sha256
        or report.get("datasetFilesSha256") != files_sha256
    ):
        raise ValueError("Recursive evaluation file inventory or aggregate SHA-256 drift")
    return {
        "ok": True,
        "reportPath": str(resolved_report),
        "reportSha256": report_sha256,
        "datasetYaml": str(dataset_path),
        "datasetYamlSha256": dataset_yaml_sha256,
        "evaluationManifestSha256": evaluation_manifest_sha256,
        "sourceItemsSha256": source_items_sha256,
        "filesSha256": files_sha256,
        "outputWritten": False,
    }


def materialize_from_args(args: argparse.Namespace) -> None:
    snapshot_root = Path(args.snapshot_root).resolve()
    output_dir = Path(args.output_dir).resolve()
    dataset_root = Path(args.training_dataset_root).resolve()
    sources_path = Path(args.training_sources).resolve()
    report_path = (
        Path(args.report).resolve()
        if args.report
        else output_dir.with_name(f"{output_dir.name}-report.json")
    )
    manifest_path = snapshot_root / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Frozen snapshot manifest is missing: {manifest_path}")
    ensure_safe_targets(
        snapshot_root,
        dataset_root,
        output_dir,
        report_path,
        [manifest_path, sources_path],
    )

    source_manifest_sha256 = sha256_path(manifest_path)
    training_sources_sha256 = sha256_path(sources_path)
    manifest = load_json(manifest_path)
    items = manifest.get("items")
    if manifest.get("decision") != "frozen_reviewed_candidate_not_release_ready":
        raise ValueError("Snapshot decision is not a frozen reviewed candidate")
    if (
        manifest.get("trainingUse") != "prohibited"
        or not isinstance(items, list)
        or not items
    ):
        raise ValueError(
            "Snapshot must be non-empty and trainingUse must be prohibited"
        )
    source_items_sha256 = require_sha256(
        manifest.get("itemsSha256"), "snapshot itemsSha256"
    )
    if canonical_sha256(items) != source_items_sha256:
        raise ValueError("Snapshot itemsSha256 mismatch")
    counts = manifest.get("counts")
    if not isinstance(counts, dict) or int(counts.get("images") or 0) != len(items):
        raise ValueError("Snapshot image count does not match manifest items")

    (
        training_identities,
        training_groups,
        training_hashes,
        training_file_names,
    ) = training_evidence(dataset_root, sources_path)

    prepared: list[dict[str, Any]] = []
    frozen_groups: set[str] = set()
    frozen_identity_groups: set[str] = set()
    frozen_hashes: set[str] = set()
    frozen_file_names: set[str] = set()
    seen_targets: set[str] = set()
    seen_label_targets: set[str] = set()
    lane_counts = {"core": 0, "stress": 0}
    total_masks = 0
    for item_index, item in enumerate(items, start=1):
        if not isinstance(item, dict) or item.get("trainingUse") != "prohibited":
            raise ValueError(f"Snapshot item {item_index} is not training-prohibited")
        lane = str(item.get("lane") or "")
        if lane not in lane_counts:
            raise ValueError(
                f"Snapshot item {item_index} has unsupported lane: {lane}"
            )
        file_name = safe_file_name(item.get("fileName"), "fileName")
        target_key = f"{lane}/{file_name}"
        if target_key in seen_targets:
            raise ValueError(f"Duplicate evaluation target: {target_key}")
        seen_targets.add(target_key)
        label_target_key = f"{lane}/{Path(file_name).stem}.txt"
        if label_target_key in seen_label_targets:
            raise ValueError(f"Duplicate evaluation label target: {label_target_key}")
        seen_label_targets.add(label_target_key)
        source_group = require_nonempty_text(
            item.get("sourceGroup"), f"snapshot item {item_index} sourceGroup"
        )
        parent_source_group = require_nonempty_text(
            item.get("parentSourceGroup"),
            f"snapshot item {item_index} parentSourceGroup",
        )
        annotation_name = f"{Path(file_name).stem}.json"
        image_path = snapshot_root / "images" / lane / file_name
        annotation_path = snapshot_root / "annotations" / lane / annotation_name
        if not image_path.is_file() or not annotation_path.is_file():
            raise FileNotFoundError(f"Frozen pair is incomplete: {lane}/{file_name}")
        image_sha256 = sha256_path(image_path)
        annotation_sha256 = sha256_path(annotation_path)
        if image_sha256 != require_sha256(
            item.get("imageSha256"), f"{target_key} imageSha256"
        ) or annotation_sha256 != require_sha256(
            item.get("annotationSha256"), f"{target_key} annotationSha256"
        ):
            raise ValueError(f"Frozen pair hash mismatch: {target_key}")
        pair_sha256 = canonical_sha256(
            {
                "imageSha256": image_sha256,
                "annotationSha256": annotation_sha256,
            }
        )
        if pair_sha256 != require_sha256(
            item.get("imageAnnotationPairSha256"),
            f"{target_key} imageAnnotationPairSha256",
        ):
            raise ValueError(f"Frozen pair joint hash mismatch: {target_key}")

        document = load_json(annotation_path)
        document_image = document.get("image")
        if not isinstance(document_image, dict):
            raise ValueError(f"{file_name}: annotation image identity is missing")
        if str(document_image.get("sourceGroup") or "") != source_group:
            raise ValueError(f"{file_name}: annotation sourceGroup mismatch")
        item_width = int(item.get("width") or 0)
        item_height = int(item.get("height") or 0)
        if (
            int(document_image.get("width") or 0) != item_width
            or int(document_image.get("height") or 0) != item_height
        ):
            raise ValueError(f"{file_name}: annotation dimensions mismatch manifest")
        with Image.open(image_path) as image:
            actual_size = image.size
            image.verify()
        if actual_size != (item_width, item_height):
            raise ValueError(f"{file_name}: frozen image dimensions mismatch")
        mask_count = int(item.get("maskCount") or 0)
        lines = validate_polygons(document, mask_count, file_name)

        lane_counts[lane] += 1
        total_masks += mask_count
        frozen_groups.add(parent_source_group)
        frozen_identity_groups.update((source_group, parent_source_group))
        frozen_hashes.add(image_sha256)
        frozen_file_names.add(file_name)
        prepared.append(
            {
                "lane": lane,
                "fileName": file_name,
                "sourceGroup": source_group,
                "parentSourceGroup": parent_source_group,
                "maskCount": mask_count,
                "width": item_width,
                "height": item_height,
                "sourceImage": image_path,
                "sourceAnnotation": annotation_path,
                "imageSha256": image_sha256,
                "annotationSha256": annotation_sha256,
                "imageAnnotationPairSha256": pair_sha256,
                "labelText": "\n".join(lines) + "\n",
            }
        )

    expected_masks = int(counts.get("masks") or 0)
    if total_masks != expected_masks:
        raise ValueError(
            f"Snapshot mask count mismatch: expected {expected_masks}, found {total_masks}"
        )
    for lane, count_key in (("core", "coreImages"), ("stress", "stressImages")):
        if count_key in counts and int(counts.get(count_key) or 0) != lane_counts[lane]:
            raise ValueError(f"Snapshot {count_key} count mismatch")

    group_overlap = sorted(frozen_identity_groups & training_groups)
    parent_group_overlap = sorted(frozen_groups & training_groups)
    exact_hash_overlap = sorted(frozen_hashes & training_hashes)
    file_name_overlap = sorted(frozen_file_names & training_file_names)
    if group_overlap or exact_hash_overlap or file_name_overlap:
        raise ValueError(
            "Frozen evaluation identity overlaps training data: "
            f"sourceGroups={group_overlap} imageSha256={exact_hash_overlap} "
            f"fileNames={file_name_overlap}"
        )

    prepared.sort(key=lambda item: (item["lane"], item["fileName"]))
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    report_temporary: Path | None = None
    output_committed = False
    report_committed = False
    try:
        temporary = Path(
            tempfile.mkdtemp(
                prefix=f".{output_dir.name}.tmp-", dir=str(output_dir.parent)
            )
        )
        report_handle, report_temporary_name = tempfile.mkstemp(
            prefix=f".{report_path.name}.tmp-", dir=str(report_path.parent)
        )
        os.close(report_handle)
        report_temporary = Path(report_temporary_name)
        for split in ("train", "val"):
            (temporary / "images" / split).mkdir(parents=True, exist_ok=True)
            (temporary / "labels" / split).mkdir(parents=True, exist_ok=True)
        for lane in ("core", "stress"):
            (temporary / "images" / "test" / lane).mkdir(parents=True, exist_ok=True)
            (temporary / "labels" / "test" / lane).mkdir(parents=True, exist_ok=True)

        records: list[dict[str, Any]] = []
        expected_images = {"core": set(), "stress": set()}
        expected_labels = {"core": set(), "stress": set()}
        for item in prepared:
            lane = item["lane"]
            file_name = item["fileName"]
            label_name = f"{Path(file_name).stem}.txt"
            image_relative = f"images/test/{lane}/{file_name}"
            label_relative = f"labels/test/{lane}/{label_name}"
            image_target = temporary / image_relative
            label_target = temporary / label_relative
            shutil.copyfile(item["sourceImage"], image_target)
            label_target.write_text(item["labelText"], encoding="utf-8")
            materialized_image_sha256 = sha256_path(image_target)
            materialized_label_sha256 = sha256_path(label_target)
            if materialized_image_sha256 != item["imageSha256"]:
                raise ValueError(f"Materialized image hash drift: {lane}/{file_name}")
            expected_images[lane].add(file_name)
            expected_labels[lane].add(label_name)
            records.append(
                {
                    "lane": lane,
                    "sourceFileName": file_name,
                    "materializedFileName": file_name,
                    "sourceGroup": item["sourceGroup"],
                    "parentSourceGroup": item["parentSourceGroup"],
                    "width": item["width"],
                    "height": item["height"],
                    "maskCount": item["maskCount"],
                    "sourceImage": str(item["sourceImage"]),
                    "sourceAnnotation": str(item["sourceAnnotation"]),
                    "sourceImageSha256": item["imageSha256"],
                    "sourceAnnotationSha256": item["annotationSha256"],
                    "sourceImageAnnotationPairSha256": item[
                        "imageAnnotationPairSha256"
                    ],
                    "materializedImage": image_relative,
                    "materializedLabel": label_relative,
                    "materializedImageSha256": materialized_image_sha256,
                    "materializedLabelSha256": materialized_label_sha256,
                }
            )

        dataset_paths = {
            "dataset.yaml": "images/test",
            "dataset.core.yaml": "images/test/core",
            "dataset.stress.yaml": "images/test/stress",
        }
        for name, test_path in dataset_paths.items():
            (temporary / name).write_text(dataset_yaml(test_path), encoding="utf-8")

        source_isolation = {
            "trainingIdentities": len(training_identities),
            "trainingIdentitiesSha256": canonical_sha256(training_identities),
            "trainingSourceGroups": len(training_groups),
            "trainingImageHashes": len(training_hashes),
            "trainingFileNames": len(training_file_names),
            "sourceGroupOverlap": group_overlap,
            "parentSourceGroupOverlap": parent_group_overlap,
            "exactImageHashOverlap": exact_hash_overlap,
            "fileNameOverlap": file_name_overlap,
        }
        evaluation_manifest = {
            "schemaVersion": 2,
            "decision": "evaluation_only_frozen_reviewed_snapshot",
            "trainingUse": "prohibited",
            "sourceSnapshotId": manifest.get("snapshotId"),
            "sourceSnapshotManifest": {
                "path": str(manifest_path),
                "sha256": source_manifest_sha256,
            },
            "sourceItemsSha256": source_items_sha256,
            "counts": {
                "images": len(records),
                "masks": total_masks,
                "coreImages": lane_counts["core"],
                "stressImages": lane_counts["stress"],
                "trainImages": 0,
                "validationImages": 0,
                "testImages": len(records),
                "parentSourceGroups": len(frozen_groups),
            },
            "sourceIsolation": source_isolation,
            "recordsSha256": canonical_sha256(records),
            "records": records,
        }
        evaluation_manifest_path = temporary / "evaluation-manifest.json"
        write_json(evaluation_manifest_path, evaluation_manifest)
        assert_output_tree(temporary, expected_images, expected_labels)

        file_records = inventory(temporary)
        files_sha256 = canonical_sha256(file_records)
        dataset_yaml_path = temporary / "dataset.yaml"
        core_yaml_path = temporary / "dataset.core.yaml"
        stress_yaml_path = temporary / "dataset.stress.yaml"
        report = {
            "schemaVersion": 2,
            "ok": True,
            "status": "PASS",
            "decision": "evaluation_only_frozen_reviewed_snapshot",
            "trainingUse": "prohibited",
            "inputs": {
                "sourceFrozenManifest": {
                    "path": str(manifest_path),
                    "sha256": source_manifest_sha256,
                    "itemsSha256": source_items_sha256,
                },
                "trainingDatasetRoot": str(dataset_root),
                "trainingSources": {
                    "path": str(sources_path),
                    "sha256": training_sources_sha256,
                    "identitiesSha256": canonical_sha256(training_identities),
                },
            },
            "snapshotRoot": str(snapshot_root),
            "sourceFrozenManifest": str(manifest_path),
            "sourceFrozenManifestSha256": source_manifest_sha256,
            "sourceItemsSha256": source_items_sha256,
            "outputDir": str(output_dir),
            "datasetYaml": str(output_dir / "dataset.yaml"),
            "coreDatasetYaml": str(output_dir / "dataset.core.yaml"),
            "stressDatasetYaml": str(output_dir / "dataset.stress.yaml"),
            "evaluationManifest": str(output_dir / "evaluation-manifest.json"),
            "counts": evaluation_manifest["counts"],
            "sourceIsolation": source_isolation,
            "artifacts": {
                "datasetYaml": {
                    "path": str(output_dir / "dataset.yaml"),
                    "sha256": sha256_path(dataset_yaml_path),
                },
                "coreDatasetYaml": {
                    "path": str(output_dir / "dataset.core.yaml"),
                    "sha256": sha256_path(core_yaml_path),
                },
                "stressDatasetYaml": {
                    "path": str(output_dir / "dataset.stress.yaml"),
                    "sha256": sha256_path(stress_yaml_path),
                },
                "evaluationManifest": {
                    "path": str(output_dir / "evaluation-manifest.json"),
                    "sha256": sha256_path(evaluation_manifest_path),
                },
            },
            "recordsSha256": canonical_sha256(records),
            "records": records,
            "file_records": file_records,
            "files_sha256": files_sha256,
            "datasetFiles": file_records,
            "datasetFilesSha256": files_sha256,
            "invariants": {
                "sourceFrozenManifestHashBound": True,
                "sourceItemsHashRecomputed": True,
                "sourceFilesHashRecomputed": True,
                "materializedImagesMatchFrozenManifest": True,
                "materializedLabelsHashBound": True,
                "fixedEvaluationOnlySplit": True,
                "testSplitNonEmpty": True,
                "trainSplitEmpty": True,
                "validationSplitEmpty": True,
                "coreStressNestedLayout": True,
                "validPolygons": True,
                "pairwiseZeroOverlap": True,
                "trainingIdentityIsolationRecomputed": True,
                "transactionalMaterialization": True,
                "targetsNotReused": True,
                "noOrphans": True,
            },
            "errors": [],
        }
        report_temporary.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        if inventory(temporary) != file_records:
            raise ValueError("Evaluation file inventory changed before commit")
        assert_output_tree(temporary, expected_images, expected_labels)

        os.replace(temporary, output_dir)
        output_committed = True
        os.replace(report_temporary, report_path)
        report_committed = True
        verify_evaluation_report(report_path, output_dir / "dataset.yaml")
    except Exception:
        if report_committed:
            report_path.unlink(missing_ok=True)
        if output_committed:
            shutil.rmtree(output_dir, ignore_errors=True)
        if temporary is not None:
            shutil.rmtree(temporary, ignore_errors=True)
        if report_temporary is not None:
            report_temporary.unlink(missing_ok=True)
        raise

    print(json.dumps(report, ensure_ascii=False, indent=2))


def main() -> None:
    args = build_parser().parse_args()
    if args.verify_report:
        if args.snapshot_root or args.output_dir or args.report:
            raise ValueError(
                "--verify-report cannot be combined with --snapshot-root, "
                "--output-dir, or --report"
            )
        result = verify_evaluation_report(
            args.verify_report,
            Path(args.expected_dataset).resolve() if args.expected_dataset else None,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if not args.snapshot_root or not args.output_dir:
        raise ValueError(
            "--snapshot-root and --output-dir are required for materialization"
        )
    if args.expected_dataset:
        raise ValueError("--expected-dataset requires --verify-report")
    materialize_from_args(args)


if __name__ == "__main__":
    main()
