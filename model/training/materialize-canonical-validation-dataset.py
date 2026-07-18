#!/usr/bin/env python3
"""Materialize a deterministic, validation-only dataset from canonical truths.

The truth index is the sole sample allow-list. Role manifests and neighboring
files are deliberately not scanned, so excluded or unfinished role entries
cannot enter the dataset.
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


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
EXPECTED_INDEX_DECISION = "approved_unique_validation_truth_index"
EXPECTED_TRUTH_DECISION = (
    "approved_as_validation_truth_candidate_pending_dataset_materialization"
)
SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")


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


def read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is unreadable JSON: {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object: {path}")
    return value


def require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise ValueError(f"{label} is missing: {path}")


def require_hash(path: Path, expected: str, label: str) -> None:
    require_file(path, label)
    actual = sha256_file(path)
    if actual != expected:
        raise ValueError(
            f"{label} SHA-256 drift: expected={expected} actual={actual}: {path}"
        )


def parse_polygon(
    raw: Any, width: int, height: int, label: str
) -> tuple[Polygon, list[tuple[float, float]]]:
    if not isinstance(raw, list) or len(raw) < 3:
        raise ValueError(f"{label} polygon must contain at least 3 points")
    coordinates: list[tuple[float, float]] = []
    for point_index, point in enumerate(raw, start=1):
        if not isinstance(point, dict) or "x" not in point or "y" not in point:
            raise ValueError(f"{label} point {point_index} is invalid")
        try:
            x = float(point["x"])
            y = float(point["y"])
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"{label} point {point_index} is not numeric"
            ) from error
        if not 0 <= x <= width or not 0 <= y <= height:
            raise ValueError(f"{label} point {point_index} is outside the image")
        coordinates.append((x, y))
    shape = Polygon(coordinates)
    if shape.is_empty or not shape.is_valid or shape.area <= 0:
        raise ValueError(f"{label} polygon has invalid topology")
    return shape, coordinates


def validate_annotation(
    document: dict[str, Any],
    file_name: str,
    source_group: str,
    expected_masks: int,
    image_path: Path,
) -> tuple[list[str], int, int]:
    image_meta = document.get("image")
    if not isinstance(image_meta, dict):
        raise ValueError(f"{file_name}: annotation image metadata is missing")
    if image_meta.get("fileName") != file_name:
        raise ValueError(f"{file_name}: annotation fileName differs")
    if image_meta.get("sourceGroup") != source_group:
        raise ValueError(f"{file_name}: annotation sourceGroup differs")

    try:
        with Image.open(image_path) as image:
            image.verify()
        with Image.open(image_path) as image:
            width, height = image.size
    except Exception as error:
        raise ValueError(f"{file_name}: source image is unreadable: {error}") from error
    if image_meta.get("width") != width or image_meta.get("height") != height:
        raise ValueError(f"{file_name}: annotation dimensions differ from source image")

    raw_annotations = document.get("annotations")
    if not isinstance(raw_annotations, list):
        raise ValueError(f"{file_name}: annotations must be an array")
    if len(raw_annotations) != expected_masks or expected_masks < 1:
        raise ValueError(
            f"{file_name}: annotation count {len(raw_annotations)} "
            f"differs from canonical completeMaskCount {expected_masks}"
        )

    shapes: list[Polygon] = []
    yolo_lines: list[str] = []
    for index, annotation in enumerate(raw_annotations, start=1):
        if not isinstance(annotation, dict):
            raise ValueError(f"{file_name}: annotation {index} must be an object")
        if annotation.get("label") not in (None, "nail_texture"):
            raise ValueError(
                f"{file_name}: annotation {index} must use label nail_texture"
            )
        shape, coordinates = parse_polygon(
            annotation.get("polygon"), width, height, f"{file_name}: nail {index}"
        )
        shapes.append(shape)
        normalized = [
            value
            for x, y in coordinates
            for value in (f"{x / width:.8f}", f"{y / height:.8f}")
        ]
        yolo_lines.append(" ".join(["0", *normalized]))

    for left_index, left in enumerate(shapes, start=1):
        for right_index in range(left_index + 1, len(shapes) + 1):
            overlap = left.intersection(shapes[right_index - 1]).area
            if overlap > 1e-6:
                raise ValueError(
                    f"{file_name}: nails {left_index}/{right_index} overlap "
                    f"{overlap:.8f} pixels"
                )
    return yolo_lines, width, height


def validate_index(index: dict[str, Any], minimum_images: int) -> list[dict[str, Any]]:
    if index.get("ok") is not True or index.get("decision") != EXPECTED_INDEX_DECISION:
        raise ValueError("truth index is not an approved unique validation truth index")
    inputs = index.get("inputs")
    if not isinstance(inputs, dict) or inputs.get("truthRole") != "val":
        raise ValueError("truth index is not restricted to truthRole=val")
    if index.get("errors") not in (None, []):
        raise ValueError("truth index contains errors")
    if index.get("conflicts") not in (None, []):
        raise ValueError("truth index contains conflicting truths")

    truths = index.get("canonicalTruths")
    if not isinstance(truths, list):
        raise ValueError("truth index canonicalTruths must be an array")
    if len(truths) < minimum_images:
        raise ValueError(
            f"canonical validation truth count {len(truths)} is below {minimum_images}"
        )
    summary = index.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("truth index summary is missing")
    if int(summary.get("uniqueImageCount", -1)) != len(truths):
        raise ValueError("truth index uniqueImageCount differs from canonicalTruths")
    if int(summary.get("conflictingImageCount", -1)) != 0:
        raise ValueError("truth index reports conflicting images")

    file_names: list[str] = []
    image_hashes: list[str] = []
    label_stems: list[str] = []
    complete_mask_count = 0
    for index_number, truth in enumerate(truths, start=1):
        if not isinstance(truth, dict):
            raise ValueError(f"canonical truth {index_number} must be an object")
        file_name = str(truth.get("fileName", ""))
        image_hash = str(truth.get("imageSha256", ""))
        source_group = str(truth.get("sourceGroup", ""))
        mask_count = truth.get("completeMaskCount")
        if (
            not file_name
            or Path(file_name).name != file_name
            or Path(file_name).suffix.lower() not in IMAGE_SUFFIXES
        ):
            raise ValueError(f"canonical truth {index_number} has invalid fileName")
        if not SHA256_PATTERN.fullmatch(image_hash):
            raise ValueError(f"{file_name}: imageSha256 is invalid")
        if not source_group:
            raise ValueError(f"{file_name}: sourceGroup is empty")
        if (
            not isinstance(mask_count, int)
            or isinstance(mask_count, bool)
            or mask_count < 1
        ):
            raise ValueError(f"{file_name}: completeMaskCount is invalid")
        file_names.append(file_name)
        image_hashes.append(image_hash)
        label_stems.append(Path(file_name).stem)
        complete_mask_count += mask_count
    for label, values in (
        ("fileName", file_names),
        ("image SHA-256", image_hashes),
        ("label stem", label_stems),
    ):
        duplicates = sorted({value for value in values if values.count(value) > 1})
        if duplicates:
            raise ValueError(f"duplicate canonical {label}: {duplicates}")
    if int(summary.get("completeMaskCount", -1)) != complete_mask_count:
        raise ValueError("truth index completeMaskCount differs from canonicalTruths")
    return sorted(truths, key=lambda item: str(item["fileName"]))


def validate_truth(
    truth: dict[str, Any],
) -> tuple[Path, Path, dict[str, Any], list[str], int, int]:
    file_name = str(truth["fileName"])
    report_path = Path(str(truth.get("reportPath", ""))).resolve()
    report_hash = str(truth.get("reportSha256", ""))
    if truth.get("reportName") != report_path.name:
        raise ValueError(f"{file_name}: final report name differs from its path")
    require_hash(report_path, report_hash, f"{file_name}: final report")
    report = read_json(report_path, f"{file_name}: final report")
    if report.get("ok") is not True or report.get("decision") != EXPECTED_TRUTH_DECISION:
        raise ValueError(f"{file_name}: final report is not an approved validation truth")
    report_inputs = report.get("inputs")
    report_item = report.get("item")
    if not isinstance(report_inputs, dict) or not isinstance(report_item, dict):
        raise ValueError(f"{file_name}: final report inputs/item are missing")
    if report_inputs.get("truthRole") != "val":
        raise ValueError(f"{file_name}: final report is not truthRole=val")

    expected_identity = {
        "fileName": file_name,
        "sha256": truth.get("imageSha256"),
        "sourceGroup": truth.get("sourceGroup"),
        "completeMaskCount": truth.get("completeMaskCount"),
    }
    actual_identity = {
        key: report_item.get(key) for key in expected_identity
    }
    if actual_identity != expected_identity:
        raise ValueError(f"{file_name}: final report identity differs from canonical truth")
    if report_item.get("trainingUse") != "prohibited":
        raise ValueError(f"{file_name}: validation truth is not training-prohibited")

    image_path = Path(str(report_inputs.get("image", ""))).resolve()
    image_hash = str(truth["imageSha256"])
    if report_inputs.get("imageSha256") != image_hash:
        raise ValueError(f"{file_name}: final report image hash differs")
    require_hash(image_path, image_hash, f"{file_name}: source image")
    if image_path.name != file_name:
        raise ValueError(f"{file_name}: final report image path has a different name")

    annotation_path = Path(str(truth.get("annotationPath", ""))).resolve()
    annotation_hash = str(truth.get("annotationSha256", ""))
    if (
        Path(str(report_inputs.get("annotation", ""))).resolve() != annotation_path
        or report_inputs.get("annotationSha256") != annotation_hash
    ):
        raise ValueError(f"{file_name}: final report annotation evidence differs")
    require_hash(annotation_path, annotation_hash, f"{file_name}: annotation")
    annotation = read_json(annotation_path, f"{file_name}: annotation")
    lines, width, height = validate_annotation(
        annotation,
        file_name,
        str(truth.get("sourceGroup", "")),
        int(truth.get("completeMaskCount", 0)),
        image_path,
    )
    return image_path, annotation_path, annotation, lines, width, height


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def inventory_digest(root: Path, excluded: set[Path] | None = None) -> tuple[str, list[dict[str, str]]]:
    excluded = excluded or set()
    records: list[dict[str, str]] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if path in excluded:
            continue
        records.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": sha256_file(path),
            }
        )
    return canonical_sha256(records), records


def assert_no_orphans(root: Path, file_names: list[str]) -> None:
    expected_images = set(file_names)
    expected_annotations = {f"{Path(name).stem}.json" for name in file_names}
    expected_labels = {f"{Path(name).stem}.txt" for name in file_names}
    checks = (
        (root / "images" / "raw", expected_images),
        (root / "images" / "val", expected_images),
        (root / "annotations" / "raw-json", expected_annotations),
        (root / "labels-yolo-seg" / "val", expected_labels),
        (root / "labels" / "val", expected_labels),
    )
    for folder, expected in checks:
        actual = {path.name for path in folder.iterdir() if path.is_file()}
        if actual != expected:
            raise ValueError(
                f"orphan or missing materialized files in {folder}: "
                f"missing={sorted(expected - actual)} orphan={sorted(actual - expected)}"
            )
    for kind in ("images", "labels", "labels-yolo-seg"):
        for split in ("train", "test"):
            folder = root / kind / split
            actual = [path.name for path in folder.iterdir() if path.is_file()]
            if actual:
                raise ValueError(f"validation-only dataset has orphan {split} files: {actual}")


def materialize(
    truth_index_path: Path,
    output_dir: Path,
    minimum_images: int,
) -> dict[str, Any]:
    if output_dir.exists():
        raise ValueError(f"output directory must not already exist: {output_dir}")
    require_file(truth_index_path, "truth index")
    index_hash = sha256_file(truth_index_path)
    index = read_json(truth_index_path, "truth index")
    truths = validate_index(index, minimum_images)

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{output_dir.name}.tmp-", dir=str(output_dir.parent)
        )
    )
    try:
        for folder in (
            temporary / "images" / "raw",
            temporary / "annotations" / "raw-json",
            *(temporary / "images" / split for split in ("train", "val", "test")),
            *(temporary / "labels" / split for split in ("train", "val", "test")),
            *(
                temporary / "labels-yolo-seg" / split
                for split in ("train", "val", "test")
            ),
            temporary / "metadata",
        ):
            folder.mkdir(parents=True, exist_ok=True)

        records: list[dict[str, Any]] = []
        total_masks = 0
        for truth in truths:
            file_name = str(truth["fileName"])
            stem = Path(file_name).stem
            (
                image_path,
                annotation_path,
                annotation,
                yolo_lines,
                width,
                height,
            ) = validate_truth(truth)
            raw_image_target = temporary / "images" / "raw" / file_name
            val_image_target = temporary / "images" / "val" / file_name
            annotation_target = (
                temporary / "annotations" / "raw-json" / f"{stem}.json"
            )
            converted_label = temporary / "labels-yolo-seg" / "val" / f"{stem}.txt"
            val_label = temporary / "labels" / "val" / f"{stem}.txt"
            shutil.copyfile(image_path, raw_image_target)
            shutil.copyfile(image_path, val_image_target)
            annotation_bytes = annotation_path.read_bytes()
            annotation_target.write_bytes(annotation_bytes)
            label_text = "\n".join(yolo_lines) + "\n"
            converted_label.write_text(label_text, encoding="utf-8")
            val_label.write_text(label_text, encoding="utf-8")
            total_masks += len(yolo_lines)
            records.append(
                {
                    "fileName": file_name,
                    "sourceGroup": truth["sourceGroup"],
                    "completeMaskCount": len(yolo_lines),
                    "width": width,
                    "height": height,
                    "finalReport": str(Path(str(truth["reportPath"])).resolve()),
                    "finalReportSha256": truth["reportSha256"],
                    "sourceImage": str(image_path),
                    "sourceImageSha256": truth["imageSha256"],
                    "sourceAnnotation": str(annotation_path),
                    "sourceAnnotationSha256": truth["annotationSha256"],
                    "materializedRawImageSha256": sha256_file(raw_image_target),
                    "materializedValidationImageSha256": sha256_file(val_image_target),
                    "materializedAnnotationSha256": sha256_file(annotation_target),
                    "materializedYoloLabelSha256": sha256_file(converted_label),
                    "materializedValidationLabelSha256": sha256_file(val_label),
                }
            )

        file_names = [str(truth["fileName"]) for truth in truths]
        split = {"train": [], "val": file_names, "test": []}
        split_path = temporary / "metadata" / "split.json"
        write_json(split_path, split)
        sources_path = temporary / "metadata" / "sources-isolation.csv"
        with sources_path.open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(
                target,
                fieldnames=["fileName", "sourceGroup", "imageSha256"],
                lineterminator="\n",
            )
            writer.writeheader()
            for truth in truths:
                writer.writerow(
                    {
                        "fileName": truth["fileName"],
                        "sourceGroup": truth["sourceGroup"],
                        "imageSha256": truth["imageSha256"],
                    }
                )
        dataset_path = temporary / "dataset.yaml"
        dataset_path.write_text(
            "\n".join(
                [
                    "path: .",
                    "train: images/train",
                    "val: images/val",
                    "test: images/test",
                    "",
                    "names:",
                    "  0: nail_texture",
                    "",
                    "task: segment",
                    "class_count: 1",
                    "image_size: 640",
                    "",
                    "metadata:",
                    "  dataset_version: canonical-validation-dataset/v1",
                    "  split_source: metadata/split.json",
                    "  sources_isolation: metadata/sources-isolation.csv",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        assert_no_orphans(temporary, file_names)
        dataset_files_sha256, dataset_files = inventory_digest(temporary)
        report_path = temporary / "metadata" / "materialization-report.json"
        report = {
            "schemaVersion": 1,
            "ok": True,
            "decision": "canonical_validation_dataset_materialized_pending_role_isolation_audit",
            "trainingUse": "prohibited",
            "validationUse": "prohibited-until-role-isolation-audit",
            "inputs": {
                "truthIndex": str(truth_index_path),
                "truthIndexSha256": index_hash,
                "truthRole": "val",
            },
            "outputDir": str(output_dir),
            "datasetYaml": str(output_dir / "dataset.yaml"),
            "counts": {
                "validationImages": len(records),
                "validationAnnotations": len(records),
                "validationLabels": len(records),
                "validationMasks": total_masks,
                "trainImages": 0,
                "testImages": 0,
                "orphanFiles": 0,
            },
            "artifacts": {
                "datasetYaml": {
                    "path": str(output_dir / "dataset.yaml"),
                    "sha256": sha256_file(dataset_path),
                },
                "splitJson": {
                    "path": str(output_dir / "metadata" / "split.json"),
                    "sha256": sha256_file(split_path),
                },
                "sourcesIsolationCsv": {
                    "path": str(
                        output_dir / "metadata" / "sources-isolation.csv"
                    ),
                    "sha256": sha256_file(sources_path),
                },
            },
            "recordsSha256": canonical_sha256(records),
            "datasetFilesSha256": dataset_files_sha256,
            "datasetFiles": dataset_files,
            "records": records,
            "invariants": {
                "canonicalTruthsAreSoleAllowList": True,
                "fixedValidationOnlySplit": True,
                "uniqueFileNames": True,
                "uniqueImageSha256": True,
                "validPolygons": True,
                "pairwiseZeroOverlap": True,
                "noOrphans": True,
                "transactionalMaterialization": True,
            },
            "errors": [],
        }
        write_json(report_path, report)
        os.replace(temporary, output_dir)
        return report
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Materialize a validation-only dataset from canonical validation truths."
    )
    parser.add_argument("--truth-index", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--minimum-images", type=int, default=30)
    args = parser.parse_args()
    if args.minimum_images < 30:
        raise ValueError("--minimum-images cannot weaken the formal 30-image gate")
    truth_index_path = Path(args.truth_index).resolve()
    output_dir = Path(args.output_dir).resolve()
    report = materialize(truth_index_path, output_dir, args.minimum_images)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "decision": report["decision"],
                "counts": report["counts"],
                "recordsSha256": report["recordsSha256"],
                "datasetFilesSha256": report["datasetFilesSha256"],
                "outputDir": report["outputDir"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
