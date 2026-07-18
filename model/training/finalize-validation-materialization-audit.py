#!/usr/bin/env python3
"""Promote a fully materialized, source-isolated val split to calibration truth."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

from PIL import Image
from shapely.geometry import Polygon

from _training_common import load_dataset_config


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


def load_role_isolation_auditor() -> ModuleType:
    script = Path(__file__).with_name("audit-validation-role-isolation.py")
    spec = importlib.util.spec_from_file_location(
        "validation_role_isolation_auditor", script
    )
    if spec is None or spec.loader is None:
        raise ValueError(f"role-isolation auditor cannot be loaded: {script}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require_current_hash(path: Path, expected: Any, label: str) -> str:
    if not path.is_file():
        raise ValueError(f"{label} is missing: {path}")
    actual = sha256_file(path)
    if actual != expected:
        raise ValueError(
            f"{label} SHA-256 drift: expected={expected} actual={actual}"
        )
    return actual


def validate_polygon(
    raw: Any,
    label: str,
    bounds: tuple[float, float] | None = None,
) -> tuple[Polygon, list[tuple[float, float]]]:
    if not isinstance(raw, list) or len(raw) < 3:
        raise ValueError(f"{label} has fewer than 3 polygon points")
    coordinates: list[tuple[float, float]] = []
    for point_index, point in enumerate(raw, start=1):
        if (
            not isinstance(point, (list, tuple))
            or len(point) != 2
        ):
            raise ValueError(f"{label} point {point_index} is malformed")
        try:
            x, y = float(point[0]), float(point[1])
        except (TypeError, ValueError) as error:
            raise ValueError(f"{label} point {point_index} is not numeric") from error
        if bounds is not None and not (0 <= x <= bounds[0] and 0 <= y <= bounds[1]):
            raise ValueError(f"{label} point {point_index} is outside bounds")
        coordinates.append((x, y))
    shape = Polygon(coordinates)
    if shape.is_empty or not shape.is_valid or shape.area <= 0:
        raise ValueError(f"{label} has invalid polygon topology")
    return shape, coordinates


def reject_overlap(shapes: list[Polygon], label: str) -> None:
    for left_index, left in enumerate(shapes, start=1):
        for right_index in range(left_index + 1, len(shapes) + 1):
            overlap = left.intersection(shapes[right_index - 1]).area
            if overlap > 0:
                raise ValueError(
                    f"{label} polygons {left_index}/{right_index} overlap {overlap:.10f}"
                )


def annotation_yolo_lines(
    path: Path,
    file_name: str,
    source_group: str,
    image_path: Path,
    expected_masks: int,
) -> list[str]:
    annotation = read_json(path, f"{file_name} materialized annotation")
    image_meta = annotation.get("image")
    raw_annotations = annotation.get("annotations")
    if not isinstance(image_meta, dict) or not isinstance(raw_annotations, list):
        raise ValueError(f"{file_name}: annotation metadata or annotations are missing")
    if (
        image_meta.get("fileName") != file_name
        or image_meta.get("sourceGroup") != source_group
    ):
        raise ValueError(f"{file_name}: annotation identity differs from canonical truth")
    try:
        with Image.open(image_path) as image:
            image.verify()
        with Image.open(image_path) as image:
            width, height = image.size
    except Exception as error:
        raise ValueError(f"{file_name}: materialized image is unreadable: {error}") from error
    if image_meta.get("width") != width or image_meta.get("height") != height:
        raise ValueError(f"{file_name}: annotation dimensions differ from image")
    if len(raw_annotations) != expected_masks or expected_masks < 1:
        raise ValueError(f"{file_name}: annotation mask count differs")

    shapes: list[Polygon] = []
    lines: list[str] = []
    for index, item in enumerate(raw_annotations, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"{file_name}: annotation {index} is not an object")
        if item.get("label") not in (None, "nail_texture"):
            raise ValueError(f"{file_name}: annotation {index} has an invalid label")
        raw_points = item.get("polygon")
        if not isinstance(raw_points, list):
            raise ValueError(f"{file_name}: annotation {index} polygon is missing")
        points = [
            [point.get("x"), point.get("y")]
            if isinstance(point, dict)
            else point
            for point in raw_points
        ]
        shape, coordinates = validate_polygon(
            points, f"{file_name}: annotation {index}", (width, height)
        )
        shapes.append(shape)
        normalized = [
            value
            for x, y in coordinates
            for value in (f"{x / width:.8f}", f"{y / height:.8f}")
        ]
        lines.append(" ".join(["0", *normalized]))
    reject_overlap(shapes, f"{file_name}: annotation")
    return lines


def validate_yolo_label(
    path: Path, file_name: str, expected_lines: list[str]
) -> int:
    raw_lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if raw_lines != expected_lines:
        raise ValueError(f"{file_name}: YOLO label differs from canonical annotation")
    shapes: list[Polygon] = []
    for line_number, raw in enumerate(raw_lines, start=1):
        parts = raw.split()
        if not parts or parts[0] != "0":
            raise ValueError(f"{file_name}: label line {line_number} has an invalid class")
        try:
            values = [float(value) for value in parts[1:]]
        except ValueError as error:
            raise ValueError(
                f"{file_name}: label line {line_number} is not numeric"
            ) from error
        if (
            len(values) < 6
            or len(values) % 2
            or any(value < 0 or value > 1 for value in values)
        ):
            raise ValueError(
                f"{file_name}: label line {line_number} has invalid normalized coordinates"
            )
        shape, _ = validate_polygon(
            list(zip(values[0::2], values[1::2])),
            f"{file_name}: label line {line_number}",
            (1, 1),
        )
        shapes.append(shape)
    reject_overlap(shapes, f"{file_name}: YOLO label")
    return len(shapes)


def validate_truth_index(
    path: Path, document: dict[str, Any]
) -> list[dict[str, Any]]:
    if (
        document.get("ok") is not True
        or document.get("decision") != "approved_unique_validation_truth_index"
    ):
        raise ValueError("truth index is not approved")
    inputs = document.get("inputs")
    if not isinstance(inputs, dict) or inputs.get("truthRole") != "val":
        raise ValueError("truth index is not restricted to truthRole=val")
    if document.get("errors") not in (None, []) or document.get("conflicts") not in (
        None,
        [],
    ):
        raise ValueError("truth index contains errors or conflicts")
    truths = document.get("canonicalTruths")
    if not isinstance(truths, list) or len(truths) < 30:
        raise ValueError("truth index has fewer than 30 canonical validation images")
    summary = document.get("summary")
    if (
        not isinstance(summary, dict)
        or int(summary.get("uniqueImageCount", -1)) != len(truths)
        or int(summary.get("conflictingImageCount", -1)) != 0
    ):
        raise ValueError("truth index summary differs from canonical truths")
    file_names = [str(item.get("fileName", "")) for item in truths if isinstance(item, dict)]
    image_hashes = [str(item.get("imageSha256", "")) for item in truths if isinstance(item, dict)]
    if len(file_names) != len(truths) or "" in file_names or len(set(file_names)) != len(file_names):
        raise ValueError("truth index has missing or duplicate fileName")
    if "" in image_hashes or len(set(image_hashes)) != len(image_hashes):
        raise ValueError("truth index has missing or duplicate imageSha256")
    return sorted(truths, key=lambda item: str(item["fileName"]))


def validate_materialization(
    path: Path,
    document: dict[str, Any],
    dataset_path: Path,
    truth_index_path: Path,
    truth_index_hash: str,
    canonical_count: int,
) -> dict[str, dict[str, Any]]:
    if (
        document.get("ok") is not True
        or document.get("decision")
        != "canonical_validation_dataset_materialized_pending_role_isolation_audit"
    ):
        raise ValueError("materialization report is not approved")
    if document.get("trainingUse") != "prohibited":
        raise ValueError("materialization report does not keep validation training-prohibited")
    inputs = document.get("inputs")
    if (
        not isinstance(inputs, dict)
        or Path(str(inputs.get("truthIndex", ""))).resolve() != truth_index_path
        or inputs.get("truthIndexSha256") != truth_index_hash
        or inputs.get("truthRole") != "val"
    ):
        raise ValueError("materialization report truth-index binding drift")
    counts = document.get("counts")
    if (
        not isinstance(counts, dict)
        or int(counts.get("validationImages", -1)) != canonical_count
        or int(counts.get("validationAnnotations", -1)) != canonical_count
        or int(counts.get("validationLabels", -1)) != canonical_count
        or int(counts.get("trainImages", -1)) != 0
        or int(counts.get("testImages", -1)) != 0
        or int(counts.get("orphanFiles", -1)) != 0
    ):
        raise ValueError("materialization report does not prove complete val-only coverage")
    artifacts = document.get("artifacts")
    dataset_artifact = artifacts.get("datasetYaml") if isinstance(artifacts, dict) else None
    if (
        not isinstance(dataset_artifact, dict)
        or Path(str(dataset_artifact.get("path", ""))).resolve() != dataset_path
        or dataset_artifact.get("sha256") != sha256_file(dataset_path)
    ):
        raise ValueError("materialization report dataset binding drift")
    raw_records = document.get("records")
    if (
        not isinstance(raw_records, list)
        or len(raw_records) != canonical_count
        or document.get("recordsSha256") != canonical_sha256(raw_records)
    ):
        raise ValueError("materialization records are incomplete or hash-drifted")
    dataset_files = document.get("datasetFiles")
    if (
        not isinstance(dataset_files, list)
        or document.get("datasetFilesSha256") != canonical_sha256(dataset_files)
    ):
        raise ValueError("materialization datasetFiles are missing or hash-drifted")
    output_dir = Path(str(document.get("outputDir", ""))).resolve()
    seen_paths: set[str] = set()
    for index, item in enumerate(dataset_files, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"materialization dataset file {index} is malformed")
        relative = str(item.get("path", ""))
        if (
            not relative
            or relative in seen_paths
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
        ):
            raise ValueError(f"materialization dataset file {index} path is invalid")
        seen_paths.add(relative)
        require_current_hash(
            output_dir / relative,
            item.get("sha256"),
            f"materialization dataset file {relative}",
        )
    actual_paths = {
        artifact.relative_to(output_dir).as_posix()
        for artifact in output_dir.rglob("*")
        if artifact.is_file()
    }
    try:
        actual_paths.discard(path.relative_to(output_dir).as_posix())
    except ValueError:
        pass
    if actual_paths != seen_paths:
        missing = sorted(seen_paths - actual_paths)
        orphan = sorted(actual_paths - seen_paths)
        raise ValueError(
            "materialization datasetFiles differ from the current output tree: "
            f"missing={missing} orphan={orphan}"
        )
    records: dict[str, dict[str, Any]] = {}
    for item in raw_records:
        if not isinstance(item, dict):
            raise ValueError("materialization record must be an object")
        file_name = str(item.get("fileName", ""))
        if not file_name or file_name in records:
            raise ValueError("materialization records have missing or duplicate fileName")
        records[file_name] = item
    return records


def validate_role_isolation(
    path: Path,
    document: dict[str, Any],
    materialization_path: Path,
    materialization_hash: str,
    canonical_count: int,
) -> None:
    if (
        document.get("ok") is not True
        or document.get("status") != "PASS"
        or document.get("decision") != "approved_validation_role_isolation"
    ):
        raise ValueError("role-isolation report is not PASS")
    inputs = document.get("inputs")
    val_input = inputs.get("valMaterializationReport") if isinstance(inputs, dict) else None
    if (
        not isinstance(val_input, dict)
        or Path(str(val_input.get("path", ""))).resolve() != materialization_path
        or val_input.get("sha256") != materialization_hash
    ):
        raise ValueError("role-isolation materialization binding drift")
    required_inputs = {
        "valMaterializationReport",
        "trainTruthIndex",
        "frozenTestManifest",
    }
    if not isinstance(inputs, dict) or not required_inputs.issubset(inputs):
        raise ValueError("role-isolation report is missing required role inputs")
    for label, evidence in inputs.items():
        if not isinstance(evidence, dict):
            raise ValueError(f"role-isolation input {label} is malformed")
        evidence_path = Path(str(evidence.get("path", ""))).resolve()
        require_current_hash(
            evidence_path, evidence.get("sha256"), f"role-isolation input {label}"
        )

    auditor = load_role_isolation_auditor()
    val_path = Path(str(inputs["valMaterializationReport"]["path"])).resolve()
    train_path = Path(str(inputs["trainTruthIndex"]["path"])).resolve()
    frozen_path = Path(str(inputs["frozenTestManifest"]["path"])).resolve()
    roles = {
        "val": auditor.validate_val_materialization(
            val_path, read_json(val_path, "role-isolation val materialization")
        ),
        "train": auditor.validate_train_index(
            train_path, read_json(train_path, "role-isolation train truth index")
        ),
        "frozen-test": auditor.validate_frozen_test(
            frozen_path, read_json(frozen_path, "role-isolation frozen test")
        ),
    }
    hard_negative_input = inputs.get("hardNegativeManifest")
    if hard_negative_input is not None:
        hard_negative_path = Path(str(hard_negative_input["path"])).resolve()
        roles["hard-negative"] = auditor.validate_hard_negatives(
            hard_negative_path,
            read_json(hard_negative_path, "role-isolation hard negatives"),
        )
    recomputed_overlaps = auditor.pairwise_overlaps(roles)
    if any(recomputed_overlaps.values()):
        raise ValueError(
            f"role-isolation recomputation found cross-role overlap: {recomputed_overlaps}"
        )
    recomputed_roles = {
        role: {
            "images": len(records),
            "imageSha256": len({item["imageSha256"] for item in records}),
            "sourceGroups": len(
                {
                    group
                    for item in records
                    for group in item["sourceGroups"]
                }
            ),
            "identitiesSha256": canonical_sha256(records),
        }
        for role, records in sorted(roles.items())
    }
    if document.get("roles") != recomputed_roles:
        raise ValueError("role-isolation role summaries differ from recomputed identities")
    recomputed_all_roles_hash = canonical_sha256(
        {role: records for role, records in sorted(roles.items())}
    )
    if document.get("allRolesSha256") != recomputed_all_roles_hash:
        raise ValueError("role-isolation allRolesSha256 differs from recomputed identities")
    roles = document.get("roles")
    val_role = roles.get("val") if isinstance(roles, dict) else None
    if not isinstance(val_role, dict) or int(val_role.get("images", -1)) != canonical_count:
        raise ValueError("role-isolation val count differs from canonical truth")
    overlaps = document.get("overlaps")
    if (
        not isinstance(overlaps, dict)
        or overlaps.get("fileName") != []
        or overlaps.get("imageSha256") != []
        or overlaps.get("sourceGroup") != []
    ):
        raise ValueError("role-isolation report contains cross-role overlap")
    invariants = document.get("invariants")
    if (
        not isinstance(invariants, dict)
        or invariants.get("validationHasNoOrphans") is not True
        or invariants.get("fileNamesDisjointAcrossRoles") is not True
        or invariants.get("imageSha256DisjointAcrossRoles") is not True
        or invariants.get("sourceGroupsDisjointAcrossRoles") is not True
    ):
        raise ValueError("role-isolation invariants are incomplete")


def build(args: argparse.Namespace) -> dict[str, Any]:
    output_path = Path(args.output).resolve()
    dataset_path = Path(args.dataset).resolve()
    truth_index_path = Path(args.truth_index).resolve()
    materialization_path = Path(args.materialization_report).resolve()
    isolation_path = Path(args.role_isolation_report).resolve()
    direct_inputs = {
        dataset_path,
        truth_index_path,
        materialization_path,
        isolation_path,
    }
    if output_path in direct_inputs:
        raise ValueError("output must not overwrite any direct input")
    for path, label in (
        (dataset_path, "dataset"),
        (truth_index_path, "truth index"),
        (materialization_path, "materialization report"),
        (isolation_path, "role-isolation report"),
    ):
        if not path.is_file():
            raise ValueError(f"{label} is missing: {path}")
    input_hashes = {
        "datasetYaml": sha256_file(dataset_path),
        "truthIndex": sha256_file(truth_index_path),
        "materializationReport": sha256_file(materialization_path),
        "roleIsolationReport": sha256_file(isolation_path),
    }
    dataset = load_dataset_config(dataset_path)
    try:
        output_path.relative_to(dataset.dataset_root)
    except ValueError:
        pass
    else:
        raise ValueError("output must be outside the materialized dataset root")
    truth_index = read_json(truth_index_path, "truth index")
    materialization = read_json(materialization_path, "materialization report")
    isolation = read_json(isolation_path, "role-isolation report")
    truths = validate_truth_index(truth_index_path, truth_index)
    records = validate_materialization(
        materialization_path,
        materialization,
        dataset_path,
        truth_index_path,
        input_hashes["truthIndex"],
        len(truths),
    )
    if Path(str(materialization.get("outputDir", ""))).resolve() != dataset.dataset_root:
        raise ValueError("materialization outputDir differs from dataset root")
    validate_role_isolation(
        isolation_path,
        isolation,
        materialization_path,
        input_hashes["materializationReport"],
        len(truths),
    )

    if (
        dataset.train != "images/train"
        or dataset.val != "images/val"
        or dataset.test != "images/test"
    ):
        raise ValueError("dataset does not use the canonical split paths")
    split_path = dataset.dataset_root / "metadata" / "split.json"
    split = read_json(split_path, "split.json")
    canonical_names = [str(item["fileName"]) for item in truths]
    if split != {"train": [], "val": canonical_names, "test": []}:
        raise ValueError("split.json is not the exact canonical val-only split")

    image_root = dataset.dataset_root / dataset.val
    raw_image_root = dataset.dataset_root / "images" / "raw"
    annotation_root = dataset.dataset_root / "annotations" / "raw-json"
    label_root = dataset.dataset_root / "labels" / "val"
    converted_label_root = dataset.dataset_root / "labels-yolo-seg" / "val"
    expected_images = set(canonical_names)
    expected_stems = {Path(name).stem for name in canonical_names}
    actual_images = {
        path.name for path in image_root.iterdir() if path.is_file()
    }
    actual_raw_images = {
        path.name for path in raw_image_root.iterdir() if path.is_file()
    }
    actual_labels = {path.stem for path in label_root.glob("*.txt") if path.is_file()}
    actual_converted_labels = {
        path.stem for path in converted_label_root.glob("*.txt") if path.is_file()
    }
    actual_annotations = {
        path.stem for path in annotation_root.glob("*.json") if path.is_file()
    }
    if (
        actual_images != expected_images
        or actual_raw_images != expected_images
        or actual_labels != expected_stems
        or actual_converted_labels != expected_stems
        or actual_annotations != expected_stems
    ):
        raise ValueError("canonical image/annotation/label coverage has orphan or missing files")
    for split_name in ("train", "test"):
        split_image_root = dataset.dataset_root / "images" / split_name
        split_label_root = dataset.dataset_root / "labels" / split_name
        if (
            any(path.is_file() for path in split_image_root.iterdir())
            or any(path.is_file() for path in split_label_root.iterdir())
        ):
            raise ValueError(f"{split_name} split contains non-validation files")

    label_hashes: dict[str, str] = {}
    item_evidence: list[dict[str, Any]] = []
    mask_count = 0
    for truth in truths:
        file_name = str(truth["fileName"])
        stem = Path(file_name).stem
        record = records.get(file_name)
        if record is None:
            raise ValueError(f"{file_name}: missing materialization record")
        if (
            record.get("sourceGroup") != truth.get("sourceGroup")
            or record.get("sourceImageSha256") != truth.get("imageSha256")
            or record.get("sourceAnnotationSha256") != truth.get("annotationSha256")
            or int(record.get("completeMaskCount", -1))
            != int(truth.get("completeMaskCount", -2))
        ):
            raise ValueError(f"{file_name}: canonical/materialization identity drift")

        report_path = Path(str(truth.get("reportPath", ""))).resolve()
        require_current_hash(
            report_path, truth.get("reportSha256"), f"{file_name} final report"
        )
        final_report = read_json(report_path, f"{file_name} final report")
        final_inputs = final_report.get("inputs")
        final_item = final_report.get("item")
        if (
            final_report.get("ok") is not True
            or final_report.get("decision")
            != "approved_as_validation_truth_candidate_pending_dataset_materialization"
            or not isinstance(final_inputs, dict)
            or not isinstance(final_item, dict)
            or final_inputs.get("truthRole") != "val"
            or final_item.get("fileName") != file_name
            or final_item.get("sha256") != truth.get("imageSha256")
            or final_item.get("sourceGroup") != truth.get("sourceGroup")
            or int(final_item.get("completeMaskCount", -1))
            != int(truth.get("completeMaskCount", -2))
            or final_item.get("trainingUse") != "prohibited"
        ):
            raise ValueError(f"{file_name}: final report decision or identity drift")
        source_image = Path(str(record.get("sourceImage", ""))).resolve()
        source_annotation = Path(str(record.get("sourceAnnotation", ""))).resolve()
        if (
            source_image
            != Path(str(final_inputs.get("image", ""))).resolve()
            or source_annotation
            != Path(str(truth.get("annotationPath", ""))).resolve()
            or source_annotation
            != Path(str(final_inputs.get("annotation", ""))).resolve()
        ):
            raise ValueError(f"{file_name}: source paths differ from final truth")
        require_current_hash(
            source_image, truth.get("imageSha256"), f"{file_name} source image"
        )
        require_current_hash(
            source_annotation,
            truth.get("annotationSha256"),
            f"{file_name} source annotation",
        )
        raw_image = raw_image_root / file_name
        val_image = image_root / file_name
        annotation = annotation_root / f"{stem}.json"
        label = label_root / f"{stem}.txt"
        converted_label = converted_label_root / f"{stem}.txt"
        image_hash = str(truth["imageSha256"])
        annotation_hash = str(truth["annotationSha256"])
        if (
            record.get("materializedRawImageSha256") != image_hash
            or record.get("materializedValidationImageSha256") != image_hash
            or record.get("materializedAnnotationSha256") != annotation_hash
        ):
            raise ValueError(f"{file_name}: materialized image/annotation hash record drift")
        require_current_hash(raw_image, image_hash, f"{file_name} raw image")
        require_current_hash(val_image, image_hash, f"{file_name} val image")
        require_current_hash(
            annotation, annotation_hash, f"{file_name} materialized annotation"
        )
        expected_lines = annotation_yolo_lines(
            annotation,
            file_name,
            str(truth["sourceGroup"]),
            val_image,
            int(truth["completeMaskCount"]),
        )
        current_label_hash = require_current_hash(
            label,
            record.get("materializedValidationLabelSha256"),
            f"{file_name} val label",
        )
        require_current_hash(
            converted_label,
            record.get("materializedYoloLabelSha256"),
            f"{file_name} converted label",
        )
        if label.read_bytes() != converted_label.read_bytes():
            raise ValueError(f"{file_name}: converted and materialized labels differ")
        item_masks = validate_yolo_label(label, file_name, expected_lines)
        if item_masks != int(truth["completeMaskCount"]):
            raise ValueError(f"{file_name}: YOLO mask count differs from canonical truth")
        mask_count += item_masks
        label_hashes[label.name] = current_label_hash
        item_evidence.append(
            {
                "fileName": file_name,
                "sourceGroup": truth["sourceGroup"],
                "imageSha256": image_hash,
                "annotationSha256": annotation_hash,
                "labelSha256": current_label_hash,
                "completeMaskCount": item_masks,
            }
        )

    if set(records) != set(canonical_names):
        raise ValueError("materialization records contain orphan or missing canonical items")
    return {
        "schemaVersion": 1,
        "ok": True,
        "status": "PASS",
        "decision": "approved_as_calibration_truth",
        "calibrationTruthEligible": True,
        "trainingUse": "prohibited",
        "validationUse": "approved-source-isolated-calibration-truth",
        "inputs": {
            "datasetYaml": str(dataset_path),
            "datasetYamlSha256": input_hashes["datasetYaml"],
            "datasetRoot": str(dataset.dataset_root),
            "truthIndex": str(truth_index_path),
            "truthIndexSha256": input_hashes["truthIndex"],
            "materializationReport": str(materialization_path),
            "materializationReportSha256": input_hashes["materializationReport"],
            "roleIsolationReport": str(isolation_path),
            "roleIsolationReportSha256": input_hashes["roleIsolationReport"],
            "split": "val",
        },
        "counts": {
            "expectedImages": len(truths),
            "reviewedImages": len(truths),
            "pass": len(truths),
            "rework": 0,
            "exclude": 0,
            "validationMasks": mask_count,
            "invalidPolygons": 0,
            "overlapPairs": 0,
            "orphanFiles": 0,
        },
        "labelSha256": dict(sorted(label_hashes.items())),
        "itemsSha256": canonical_sha256(item_evidence),
        "items": item_evidence,
        "invariants": {
            "minimumValidationImages": 30,
            "canonicalTruthCoverageComplete": True,
            "allInputsHashBound": True,
            "allImagesAnnotationsAndLabelsHashBound": True,
            "polygonTopologyValid": True,
            "pairwisePolygonOverlapZero": True,
            "roleIsolationPassed": True,
            "trainingUseProhibited": True,
        },
        "errors": [],
    }


def input_evidence(args: argparse.Namespace) -> dict[str, dict[str, str | None]]:
    values = {
        "datasetYaml": args.dataset,
        "truthIndex": args.truth_index,
        "materializationReport": args.materialization_report,
        "roleIsolationReport": args.role_isolation_report,
    }
    result: dict[str, dict[str, str | None]] = {}
    for label, raw in values.items():
        path = Path(raw).resolve()
        result[label] = {
            "path": str(path),
            "sha256": sha256_file(path) if path.is_file() else None,
        }
    return result


def validate_output_target(args: argparse.Namespace) -> None:
    output_path = Path(args.output).resolve()
    direct_inputs = {
        Path(args.dataset).resolve(),
        Path(args.truth_index).resolve(),
        Path(args.materialization_report).resolve(),
        Path(args.role_isolation_report).resolve(),
    }
    if output_path in direct_inputs:
        raise ValueError("output must not overwrite any direct input")
    dataset_path = Path(args.dataset).resolve()
    if dataset_path.is_file():
        dataset = load_dataset_config(dataset_path)
        try:
            output_path.relative_to(dataset.dataset_root)
        except ValueError:
            pass
        else:
            raise ValueError("output must be outside the materialized dataset root")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Finalize a materialized, source-isolated validation split."
    )
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--truth-index", required=True)
    parser.add_argument("--materialization-report", required=True)
    parser.add_argument("--role-isolation-report", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    try:
        validate_output_target(args)
    except Exception as error:
        print(
            json.dumps(
                {
                    "ok": False,
                    "status": "HOLD",
                    "decision": "rejected_as_calibration_truth",
                    "calibrationTruthEligible": False,
                    "errors": [str(error)],
                    "output": str(output),
                    "outputWritten": False,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        raise SystemExit(1)
    try:
        report = build(args)
    except Exception as error:
        report = {
            "schemaVersion": 1,
            "ok": False,
            "status": "HOLD",
            "decision": "rejected_as_calibration_truth",
            "calibrationTruthEligible": False,
            "trainingUse": "prohibited",
            "validationUse": "prohibited",
            "inputs": input_evidence(args),
            "counts": {
                "expectedImages": 0,
                "reviewedImages": 0,
                "pass": 0,
                "rework": 0,
                "exclude": 0,
            },
            "labelSha256": {},
            "errors": [str(error)],
        }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "status": report["status"],
                "decision": report["decision"],
                "calibrationTruthEligible": report["calibrationTruthEligible"],
                "counts": report["counts"],
                "errors": report["errors"],
                "output": str(output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
