#!/usr/bin/env python3
"""Independently audit a complete materialized candidate-training dataset."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import re
from itertools import combinations
from pathlib import Path
from types import ModuleType
from typing import Any

from PIL import Image, UnidentifiedImageError
from shapely.geometry import Polygon

from _training_common import load_dataset_config


APPROVED_MATERIALIZATION = "approved_canonical_candidate_dataset_materialization"
APPROVED_DECISION = "approved_candidate_training_input"
HOLD_DECISION = "hold_candidate_training_input"
ROLES = ("train-positive", "hard-negative", "val")
SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
FORMAL_MINIMUM_POSITIVE_IMAGES = 100
FORMAL_MINIMUM_HARD_NEGATIVE_IMAGES = 100
FORMAL_MINIMUM_VALIDATION_IMAGES = 30
IMAGE_FORMAT_BY_SUFFIX = {
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
    ".webp": "WEBP",
}
MINIMUM_HARD_NEGATIVE_SIDE = 320


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


def require_sha256(value: Any, label: str) -> str:
    normalized = str(value or "")
    if not SHA256_PATTERN.fullmatch(normalized):
        raise ValueError(f"{label} is missing or is not a SHA-256")
    return normalized


def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def load_role_auditor() -> ModuleType:
    path = Path(__file__).with_name("audit-validation-role-isolation.py")
    spec = importlib.util.spec_from_file_location("validation_role_isolation", path)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load role-isolation auditor: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def evidence_path(
    inputs: dict[str, Any], key: str, label: str
) -> tuple[Path, str]:
    evidence = inputs.get(key)
    if not isinstance(evidence, dict):
        raise ValueError(f"materialization input {key} is missing")
    path = Path(str(evidence.get("path", ""))).resolve()
    expected = require_sha256(evidence.get("sha256"), f"{label} SHA-256")
    if not path.is_file() or sha256_file(path) != expected:
        raise ValueError(f"{label} is missing or hash-drifted: {path}")
    return path, expected


def safe_relative(value: Any, label: str) -> Path:
    raw = str(value or "")
    path = Path(raw)
    if (
        not raw
        or path.is_absolute()
        or ".." in path.parts
        or any(part in ("", ".") for part in path.parts)
    ):
        raise ValueError(f"{label} has an invalid relative path: {raw!r}")
    return path


def require_current_hash(path: Path, expected: Any, label: str) -> str:
    digest = require_sha256(expected, f"{label} expected hash")
    if not path.is_file() or sha256_file(path) != digest:
        raise ValueError(f"{label} is missing or hash-drifted: {path}")
    return digest


def validate_decodable_hard_negative(
    path: Path, file_name: str, label: str
) -> tuple[int, int, str]:
    try:
        with Image.open(path) as image:
            image_format = str(image.format or "").upper()
            width, height = image.size
            image.verify()
        with Image.open(path) as image:
            image.load()
            if image.size != (width, height):
                raise ValueError(f"{label} dimensions changed while decoding: {file_name}")
    except (OSError, SyntaxError, UnidentifiedImageError) as error:
        raise ValueError(
            f"{label} cannot be fully decoded: {file_name}: {error}"
        ) from error
    expected_format = IMAGE_FORMAT_BY_SUFFIX.get(Path(file_name).suffix.lower())
    if expected_format is None or image_format != expected_format:
        raise ValueError(
            f"{label} format {image_format or 'UNKNOWN'} does not match extension: {file_name}"
        )
    if min(width, height) < MINIMUM_HARD_NEGATIVE_SIDE:
        raise ValueError(
            f"{label} dimensions {width}x{height} are below the "
            f"{MINIMUM_HARD_NEGATIVE_SIDE}px minimum: {file_name}"
        )
    return width, height, image_format


def validate_dataset_inventory(
    report_path: Path,
    output_dir: Path,
    dataset_files: list[Any],
) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, item in enumerate(dataset_files, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"dataset file {index} must be an object")
        relative_path = safe_relative(item.get("path"), f"dataset file {index}")
        artifact = (output_dir / relative_path).resolve()
        if not is_within(artifact, output_dir):
            raise ValueError(f"dataset file {index} escapes outputDir")
        relative = artifact.relative_to(output_dir).as_posix()
        if relative in seen:
            raise ValueError(f"datasetFiles contains duplicate path: {relative}")
        seen.add(relative)
        digest = require_current_hash(artifact, item.get("sha256"), relative)
        normalized.append({"path": relative, "sha256": digest})

    actual = {
        artifact.resolve().relative_to(output_dir).as_posix()
        for artifact in output_dir.rglob("*")
        if artifact.is_file() and artifact.resolve() != report_path
    }
    if actual != seen:
        raise ValueError(
            "datasetFiles differ from current output tree: "
            f"missing={sorted(seen - actual)} orphan={sorted(actual - seen)}"
        )
    return normalized


def validate_polygon_label(path: Path, expected_masks: int, label: str) -> int:
    shapes: list[Polygon] = []
    for line_number, raw in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not raw.strip():
            continue
        parts = raw.split()
        if len(parts) < 7 or parts[0] != "0" or (len(parts) - 1) % 2:
            raise ValueError(f"{label}:{line_number} is not a class-0 segmentation row")
        try:
            coordinates = [float(value) for value in parts[1:]]
        except ValueError as error:
            raise ValueError(f"{label}:{line_number} has non-numeric coordinates") from error
        if any(not math.isfinite(value) or value < 0 or value > 1 for value in coordinates):
            raise ValueError(f"{label}:{line_number} has invalid normalized coordinates")
        shape = Polygon(list(zip(coordinates[0::2], coordinates[1::2])))
        if shape.is_empty or not shape.is_valid or shape.area <= 0:
            raise ValueError(f"{label}:{line_number} has invalid polygon topology")
        shapes.append(shape)
    if len(shapes) != expected_masks:
        raise ValueError(
            f"{label} mask count differs: expected={expected_masks} actual={len(shapes)}"
        )
    for left_index, right_index in combinations(range(len(shapes)), 2):
        overlap = shapes[left_index].intersection(shapes[right_index]).area
        if overlap > 0:
            raise ValueError(
                f"{label}:{left_index + 1}/{right_index + 1} overlap {overlap:.12f}"
            )
    return len(shapes)


def annotation_yolo_text(
    document: dict[str, Any],
    file_name: str,
    source_group: str,
    expected_masks: int,
) -> str:
    """Independently reproduce the canonical annotation-to-YOLO conversion."""
    image = document.get("image")
    if not isinstance(image, dict):
        raise ValueError(f"{file_name}: annotation image metadata is missing")
    if image.get("fileName") != file_name or image.get("sourceGroup") != source_group:
        raise ValueError(f"{file_name}: annotation identity differs")
    width = image.get("width")
    height = image.get("height")
    if (
        not isinstance(width, int)
        or isinstance(width, bool)
        or width <= 0
        or not isinstance(height, int)
        or isinstance(height, bool)
        or height <= 0
    ):
        raise ValueError(f"{file_name}: annotation dimensions are invalid")
    annotations = document.get("annotations")
    if not isinstance(annotations, list) or len(annotations) != expected_masks:
        raise ValueError(f"{file_name}: annotation mask count differs")
    shapes: list[Polygon] = []
    lines: list[str] = []
    for index, annotation in enumerate(annotations, start=1):
        if not isinstance(annotation, dict) or annotation.get("label") not in (
            None,
            "nail_texture",
        ):
            raise ValueError(f"{file_name}: annotation {index} is invalid")
        points = annotation.get("polygon")
        if not isinstance(points, list) or len(points) < 3:
            raise ValueError(f"{file_name}: annotation {index} polygon is invalid")
        coordinates: list[tuple[float, float]] = []
        for point in points:
            if not isinstance(point, dict) or "x" not in point or "y" not in point:
                raise ValueError(f"{file_name}: annotation {index} point is invalid")
            try:
                x = float(point["x"])
                y = float(point["y"])
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"{file_name}: annotation {index} point is non-numeric"
                ) from error
            if (
                not math.isfinite(x)
                or not math.isfinite(y)
                or x < 0
                or x > width
                or y < 0
                or y > height
            ):
                raise ValueError(f"{file_name}: annotation {index} point is outside image")
            coordinates.append((x, y))
        shape = Polygon(coordinates)
        if shape.is_empty or not shape.is_valid or shape.area <= 0:
            raise ValueError(f"{file_name}: annotation {index} topology is invalid")
        shapes.append(shape)
        normalized = [
            value
            for x, y in coordinates
            for value in (f"{x / width:.8f}", f"{y / height:.8f}")
        ]
        lines.append(" ".join(["0", *normalized]))
    for left, right in combinations(range(len(shapes)), 2):
        if shapes[left].intersection(shapes[right]).area > 0:
            raise ValueError(f"{file_name}: source annotation polygons overlap")
    return "\n".join(lines) + "\n"


def record_identity(item: dict[str, Any], index: int) -> dict[str, Any]:
    file_name = str(item.get("fileName", ""))
    if not file_name or Path(file_name).name != file_name:
        raise ValueError(f"record {index} has an invalid fileName")
    role = str(item.get("role", ""))
    if role not in ROLES:
        raise ValueError(f"record {index} has an invalid role: {role}")
    expected_split = "val" if role == "val" else "train"
    if item.get("split") != expected_split:
        raise ValueError(f"record {index} role/split binding is invalid")
    source_group = str(item.get("sourceGroup", "")).strip()
    groups = item.get("sourceGroups")
    if not source_group or not isinstance(groups, list):
        raise ValueError(f"record {index} source groups are missing")
    normalized_groups = sorted(
        {str(group).strip() for group in groups if str(group).strip()}
    )
    if not normalized_groups or source_group not in normalized_groups:
        raise ValueError(f"record {index} sourceGroups do not include sourceGroup")
    image_hash = require_sha256(item.get("imageSha256"), f"record {index} imageSha256")
    if item.get("sourceImageSha256") != image_hash:
        raise ValueError(f"record {index} source image identity drift")
    return {
        "fileName": file_name,
        "imageSha256": image_hash,
        "sourceGroup": source_group,
        "sourceGroups": normalized_groups,
        "role": role,
        "split": expected_split,
    }


def reject_duplicate_identities(records: list[dict[str, Any]]) -> None:
    for field in ("fileName", "imageSha256"):
        values = [str(item[field]) for item in records]
        duplicate = sorted({value for value in values if values.count(value) > 1})
        if duplicate:
            raise ValueError(f"materialization contains duplicate {field}: {duplicate}")


def normalized_upstream_identity(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "fileName": str(item["fileName"]),
        "imageSha256": str(item["imageSha256"]),
        "sourceGroups": sorted(str(group) for group in item["sourceGroups"]),
    }


def identity_sort_key(item: dict[str, Any]) -> tuple[str, str, tuple[str, ...]]:
    return (
        str(item["fileName"]),
        str(item["imageSha256"]),
        tuple(str(group) for group in item["sourceGroups"]),
    )


def compare_role_to_upstream(
    role: str,
    materialized: list[dict[str, Any]],
    upstream: list[dict[str, Any]],
) -> None:
    left = sorted(
        [normalized_upstream_identity(item) for item in materialized],
        key=identity_sort_key,
    )
    right = sorted(
        [normalized_upstream_identity(item) for item in upstream],
        key=identity_sort_key,
    )
    if left != right:
        raise ValueError(f"{role} records do not exactly match approved upstream identities")


def validate_validation_audit(
    dataset_path: Path,
    document: dict[str, Any],
    minimum_images: int,
) -> list[dict[str, Any]]:
    if (
        document.get("ok") is not True
        or document.get("status") != "PASS"
        or document.get("decision") != "approved_as_calibration_truth"
        or document.get("calibrationTruthEligible") is not True
        or document.get("trainingUse") != "prohibited"
    ):
        raise ValueError("validation final audit is not approved_as_calibration_truth")
    inputs = document.get("inputs")
    if (
        not isinstance(inputs, dict)
        or inputs.get("split") != "val"
        or Path(str(inputs.get("datasetYaml", ""))).resolve() != dataset_path
        or inputs.get("datasetYamlSha256") != sha256_file(dataset_path)
    ):
        raise ValueError("validation final audit dataset binding has drifted")
    required_input_paths = ("truthIndex", "materializationReport", "roleIsolationReport")
    if any(not str(inputs.get(key, "")).strip() for key in required_input_paths):
        raise ValueError("validation final audit is missing canonical evidence inputs")
    for key in required_input_paths:
        require_current_hash(
            Path(str(inputs[key])).resolve(),
            inputs.get(f"{key}Sha256"),
            f"validation audit input {key}",
        )
    items = document.get("items")
    if not isinstance(items, list) or len(items) < minimum_images:
        raise ValueError(f"validation final audit has fewer than {minimum_images} items")
    if document.get("itemsSha256") != canonical_sha256(items):
        raise ValueError("validation final audit items SHA-256 drift")
    counts = document.get("counts")
    if (
        not isinstance(counts, dict)
        or int(counts.get("expectedImages", -1)) != len(items)
        or int(counts.get("reviewedImages", -1)) != len(items)
        or int(counts.get("pass", -1)) != len(items)
        or int(counts.get("rework", -1)) != 0
        or int(counts.get("exclude", -1)) != 0
        or int(counts.get("invalidPolygons", -1)) != 0
        or int(counts.get("overlapPairs", -1)) != 0
        or int(counts.get("orphanFiles", -1)) != 0
    ):
        raise ValueError("validation final audit does not prove complete clean coverage")
    label_hashes = document.get("labelSha256")
    if not isinstance(label_hashes, dict):
        raise ValueError("validation final audit labelSha256 map is missing")
    invariants = document.get("invariants")
    required_invariants = (
        "canonicalTruthCoverageComplete",
        "allInputsHashBound",
        "allImagesAnnotationsAndLabelsHashBound",
        "polygonTopologyValid",
        "pairwisePolygonOverlapZero",
        "roleIsolationPassed",
        "trainingUseProhibited",
    )
    if not isinstance(invariants, dict) or any(
        invariants.get(key) is not True for key in required_invariants
    ):
        raise ValueError("validation final audit invariants are incomplete")

    dataset = load_dataset_config(dataset_path)
    if dataset.val != "images/val":
        raise ValueError("validation truth dataset does not use images/val")
    records: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    seen_hashes: set[str] = set()
    mask_total = 0
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"validation audit item {index} must be an object")
        file_name = str(item.get("fileName", ""))
        source_group = str(item.get("sourceGroup", "")).strip()
        image_hash = require_sha256(
            item.get("imageSha256"), f"validation item {index} imageSha256"
        )
        label_hash = require_sha256(
            item.get("labelSha256"), f"validation item {index} labelSha256"
        )
        if not file_name or Path(file_name).name != file_name or not source_group:
            raise ValueError(f"validation audit item {index} identity is invalid")
        if file_name in seen_names or image_hash in seen_hashes:
            raise ValueError("validation final audit contains duplicate identities")
        seen_names.add(file_name)
        seen_hashes.add(image_hash)
        image_path = dataset.dataset_root / "images" / "val" / file_name
        label_path = dataset.dataset_root / "labels" / "val" / f"{Path(file_name).stem}.txt"
        annotation_path = (
            dataset.dataset_root
            / "annotations"
            / "raw-json"
            / f"{Path(file_name).stem}.json"
        )
        require_current_hash(image_path, image_hash, f"validation image {file_name}")
        require_current_hash(label_path, label_hash, f"validation label {file_name}")
        annotation_hash = require_current_hash(
            annotation_path,
            item.get("annotationSha256"),
            f"validation annotation {file_name}",
        )
        if label_hashes.get(label_path.name) != label_hash:
            raise ValueError(f"validation label hash map differs for {file_name}")
        masks = int(item.get("completeMaskCount", -1))
        if masks <= 0:
            raise ValueError(f"validation item has no complete masks: {file_name}")
        validate_polygon_label(label_path, masks, f"validation truth {file_name}")
        expected_label = annotation_yolo_text(
            read_json(annotation_path, f"validation annotation {file_name}"),
            file_name,
            source_group,
            masks,
        )
        if label_path.read_text(encoding="utf-8") != expected_label:
            raise ValueError(f"validation label differs from annotation: {file_name}")
        mask_total += masks
        records.append(
            {
                "fileName": file_name,
                "imageSha256": image_hash,
                "sourceGroups": [source_group],
                "sourceLabel": str(label_path),
                "sourceLabelSha256": label_hash,
                "sourceAnnotation": str(annotation_path),
                "sourceAnnotationSha256": annotation_hash,
                "maskCount": masks,
            }
        )
    if int(counts.get("validationMasks", -1)) != mask_total:
        raise ValueError("validation final audit mask count differs from current labels")
    if set(label_hashes) != {
        f"{Path(item['fileName']).stem}.txt" for item in records
    }:
        raise ValueError("validation final audit label hash coverage differs")
    return records


def pairwise_overlaps(
    roles: dict[str, list[dict[str, Any]]]
) -> dict[str, list[dict[str, Any]]]:
    overlaps: dict[str, list[dict[str, Any]]] = {
        "fileName": [],
        "imageSha256": [],
        "sourceGroup": [],
    }
    for left_role, right_role in combinations(sorted(roles), 2):
        left = roles[left_role]
        right = roles[right_role]
        for field in ("fileName", "imageSha256"):
            values = sorted(
                {str(item[field]) for item in left}
                & {str(item[field]) for item in right}
            )
            if values:
                overlaps[field].append(
                    {"roles": [left_role, right_role], "values": values}
                )
        groups = sorted(
            {group for item in left for group in item["sourceGroups"]}
            & {group for item in right for group in item["sourceGroups"]}
        )
        if groups:
            overlaps["sourceGroup"].append(
                {"roles": [left_role, right_role], "values": groups}
            )
    return overlaps


def validate_split_and_sources(
    split_path: Path,
    sources_path: Path,
    records: list[dict[str, Any]],
) -> None:
    split = read_json(split_path, "candidate split")
    if set(split) != {"train", "val", "test"}:
        raise ValueError("split.json must contain only train, val, and test")
    expected = {
        "train": sorted(item["fileName"] for item in records if item["split"] == "train"),
        "val": sorted(item["fileName"] for item in records if item["split"] == "val"),
        "test": [],
    }
    for name in ("train", "val", "test"):
        values = split.get(name)
        if not isinstance(values, list) or len(values) != len(set(map(str, values))):
            raise ValueError(f"split {name} is malformed or contains duplicates")
        if sorted(map(str, values)) != expected[name]:
            raise ValueError(f"split {name} differs from materialized records")

    with sources_path.open("r", encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    expected_rows = sorted(
        [
            {
                "fileName": item["fileName"],
                "role": item["role"],
                "split": item["split"],
                "sourceGroup": str(item["sourceGroup"]),
                "imageSha256": item["imageSha256"],
            }
            for item in records
        ],
        key=lambda item: (item["split"], item["fileName"]),
    )
    actual_rows = sorted(
        [
            {key: str(row.get(key, "")) for key in expected_rows[0]}
            for row in rows
        ],
        key=lambda item: (item["split"], item["fileName"]),
    ) if expected_rows else []
    if actual_rows != expected_rows:
        raise ValueError("sources-isolation.csv differs from materialized records")


def validate_dataset_tree_allow_list(
    dataset_files: list[dict[str, str]], records: list[dict[str, Any]]
) -> None:
    expected = {
        "dataset.yaml",
        "metadata/split.json",
        "metadata/sources-isolation.csv",
    }
    label_paths: set[str] = set()
    for item in records:
        image_relative = f"images/{item['split']}/{item['fileName']}"
        label_relative = (
            f"labels/{item['split']}/{Path(str(item['fileName'])).stem}.txt"
        )
        if label_relative in label_paths:
            raise ValueError(f"candidate records have a label-stem collision: {label_relative}")
        label_paths.add(label_relative)
        expected.add(image_relative)
        expected.add(label_relative)
    actual = {str(item["path"]) for item in dataset_files}
    if actual != expected:
        raise ValueError(
            "candidate dataset tree contains missing or unexpected files: "
            f"missing={sorted(expected - actual)} unexpected={sorted(actual - expected)}"
        )


def build(args: argparse.Namespace) -> dict[str, Any]:
    report_path = Path(args.materialization_report).resolve()
    materialization = read_json(report_path, "candidate materialization report")
    if (
        materialization.get("schemaVersion") != 1
        or materialization.get("ok") is not True
        or materialization.get("status") != "PASS"
        or materialization.get("decision") != APPROVED_MATERIALIZATION
        or materialization.get("candidateTrainingEligible") is not True
        or materialization.get("trainingUse")
        != "permitted-for-candidate-training-only"
    ):
        raise ValueError("candidate materialization report is not approved")
    if materialization.get("errors") not in (None, []):
        raise ValueError("candidate materialization report contains errors")

    output_dir = Path(str(materialization.get("outputDir", ""))).resolve()
    dataset_path = Path(str(materialization.get("datasetYaml", ""))).resolve()
    if not output_dir.is_dir() or dataset_path != output_dir / "dataset.yaml":
        raise ValueError("candidate materialization outputDir/datasetYaml binding is invalid")
    dataset = load_dataset_config(dataset_path)
    if dataset.dataset_root != output_dir:
        raise ValueError("dataset.yaml root differs from materialization outputDir")
    if (
        dataset.train != "images/train"
        or dataset.val != "images/val"
        or dataset.test != "images/test"
        or dataset.task != "segment"
        or dataset.class_count != 1
        or dataset.names != {0: "nail_texture"}
    ):
        raise ValueError("candidate dataset.yaml has an unsafe training contract")

    inputs = materialization.get("inputs")
    if not isinstance(inputs, dict):
        raise ValueError("candidate materialization inputs are missing")
    train_index_path, train_index_hash = evidence_path(
        inputs, "trainingTruthIndex", "training truth index"
    )
    hard_manifest_path, hard_manifest_hash = evidence_path(
        inputs, "hardNegativeManifest", "hard-negative manifest"
    )
    validation_dataset_path, validation_dataset_hash = evidence_path(
        inputs, "validationDatasetYaml", "validation dataset YAML"
    )
    validation_audit_path, validation_audit_hash = evidence_path(
        inputs, "validationFinalAudit", "validation final audit"
    )
    frozen_path, frozen_hash = evidence_path(
        inputs, "frozenTestManifest", "frozen test manifest"
    )

    artifacts = materialization.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValueError("materialization artifacts are missing")
    artifact_paths: dict[str, Path] = {}
    for key, expected_path in {
        "datasetYaml": dataset_path,
        "splitJson": output_dir / "metadata" / "split.json",
        "sourcesIsolationCsv": output_dir / "metadata" / "sources-isolation.csv",
    }.items():
        evidence = artifacts.get(key)
        if not isinstance(evidence, dict):
            raise ValueError(f"materialization artifact {key} is missing")
        path = Path(str(evidence.get("path", ""))).resolve()
        if path != expected_path:
            raise ValueError(f"materialization artifact {key} path differs")
        require_current_hash(path, evidence.get("sha256"), f"artifact {key}")
        artifact_paths[key] = path

    dataset_files = materialization.get("datasetFiles")
    if (
        not isinstance(dataset_files, list)
        or materialization.get("datasetFilesSha256") != canonical_sha256(dataset_files)
    ):
        raise ValueError("materialization datasetFiles are missing or hash-drifted")
    normalized_files = validate_dataset_inventory(
        report_path, output_dir, dataset_files
    )
    if normalized_files != dataset_files:
        raise ValueError("datasetFiles are not canonical normalized records")

    auditor = load_role_auditor()
    train_document = read_json(train_index_path, "training truth index")
    train_upstream = auditor.validate_train_index(train_index_path, train_document)
    hard_document = read_json(hard_manifest_path, "hard-negative manifest")
    hard_upstream = auditor.validate_hard_negatives(
        hard_manifest_path, hard_document
    )
    raw_hard_items = hard_document.get("items")
    if not isinstance(raw_hard_items, list):
        raise ValueError("hard-negative manifest items are missing")
    hard_item_by_name = {
        str(item.get("fileName", "")): item
        for item in raw_hard_items
        if isinstance(item, dict)
    }
    validation_upstream = validate_validation_audit(
        validation_dataset_path,
        read_json(validation_audit_path, "validation final audit"),
        args.minimum_validation_images,
    )
    frozen_upstream = auditor.validate_frozen_test(
        frozen_path, read_json(frozen_path, "frozen test manifest")
    )
    if len(train_upstream) < args.minimum_positive_images:
        raise ValueError(
            f"approved positive image count {len(train_upstream)} is below "
            f"{args.minimum_positive_images}"
        )
    if len(hard_upstream) < args.minimum_hard_negative_images:
        raise ValueError(
            f"formal hard-negative image count {len(hard_upstream)} is below "
            f"{args.minimum_hard_negative_images}"
        )
    raw_train_truths = train_document.get("canonicalTruths")
    if not isinstance(raw_train_truths, list):
        raise ValueError("training truth index canonicalTruths are missing")
    train_truth_by_name = {
        str(item.get("fileName", "")): item
        for item in raw_train_truths
        if isinstance(item, dict)
    }
    validation_by_name = {
        str(item["fileName"]): item for item in validation_upstream
    }

    raw_records = materialization.get("records")
    if (
        not isinstance(raw_records, list)
        or materialization.get("recordsSha256") != canonical_sha256(raw_records)
    ):
        raise ValueError("materialization records are missing or hash-drifted")
    identities: list[dict[str, Any]] = []
    materialized_by_role: dict[str, list[dict[str, Any]]] = {
        role: [] for role in ROLES
    }
    mask_counts = {role: 0 for role in ROLES}
    empty_negative_labels = 0
    for index, item in enumerate(raw_records, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"record {index} must be an object")
        identity = record_identity(item, index)
        identities.append(identity)
        role = identity["role"]
        split = identity["split"]
        file_name = identity["fileName"]
        source_image = Path(str(item.get("sourceImage", ""))).resolve()
        require_current_hash(
            source_image, item.get("sourceImageSha256"), f"source image {file_name}"
        )
        image_path = output_dir / "images" / split / file_name
        require_current_hash(
            image_path, item.get("materializedImageSha256"), f"image {file_name}"
        )
        if item.get("materializedImageSha256") != identity["imageSha256"]:
            raise ValueError(f"materialized image identity differs: {file_name}")
        label_path = output_dir / "labels" / split / f"{Path(file_name).stem}.txt"
        label_hash = require_current_hash(
            label_path, item.get("materializedLabelSha256"), f"label {file_name}"
        )
        mask_count = int(item.get("maskCount", -1))
        if role == "hard-negative":
            if (
                mask_count != 0
                or item.get("sourceLabel") is not None
                or item.get("sourceLabelSha256") is not None
                or item.get("sourceAnnotation") is not None
                or item.get("sourceAnnotationSha256") is not None
                or item.get("finalReport") is not None
                or item.get("finalReportSha256") is not None
                or label_path.read_bytes() != b""
            ):
                raise ValueError(f"hard-negative label is not byte-empty: {file_name}")
            source_image_info = validate_decodable_hard_negative(
                source_image, file_name, "source hard-negative image"
            )
            materialized_image_info = validate_decodable_hard_negative(
                image_path, file_name, "materialized hard-negative image"
            )
            if materialized_image_info != source_image_info:
                raise ValueError(
                    f"materialized hard-negative decode identity differs: {file_name}"
                )
            upstream_item = hard_item_by_name.get(file_name)
            if not isinstance(upstream_item, dict):
                raise ValueError(f"upstream hard-negative item is missing: {file_name}")
            if (
                upstream_item.get("width"),
                upstream_item.get("height"),
                upstream_item.get("imageFormat"),
            ) != source_image_info:
                raise ValueError(
                    f"hard-negative dimensions/format differ from approved manifest: {file_name}"
                )
            empty_negative_labels += 1
        elif role == "train-positive":
            if mask_count <= 0:
                raise ValueError(f"positive record has no masks: {file_name}")
            if item.get("sourceLabel") is not None or item.get("sourceLabelSha256") is not None:
                raise ValueError(f"training record must be annotation-derived: {file_name}")
            truth = train_truth_by_name.get(file_name)
            if not isinstance(truth, dict):
                raise ValueError(f"training truth is missing: {file_name}")
            source_annotation = Path(str(item.get("sourceAnnotation", ""))).resolve()
            if source_annotation != Path(str(truth.get("annotationPath", ""))).resolve():
                raise ValueError(f"training source annotation path differs: {file_name}")
            annotation_hash = require_current_hash(
                source_annotation,
                item.get("sourceAnnotationSha256"),
                f"training source annotation {file_name}",
            )
            if annotation_hash != truth.get("annotationSha256"):
                raise ValueError(f"training source annotation hash differs: {file_name}")
            final_report = Path(str(item.get("finalReport", ""))).resolve()
            if final_report != Path(str(truth.get("reportPath", ""))).resolve():
                raise ValueError(f"training final report path differs: {file_name}")
            report_hash = require_current_hash(
                final_report, item.get("finalReportSha256"), f"training final report {file_name}"
            )
            if report_hash != truth.get("reportSha256"):
                raise ValueError(f"training final report hash differs: {file_name}")
            expected_label = annotation_yolo_text(
                read_json(source_annotation, f"training annotation {file_name}"),
                file_name,
                str(item["sourceGroup"]),
                mask_count,
            )
            if label_path.read_text(encoding="utf-8") != expected_label:
                raise ValueError(f"training label differs from approved annotation: {file_name}")
            validate_polygon_label(label_path, mask_count, file_name)
        else:
            if mask_count <= 0:
                raise ValueError(f"validation record has no masks: {file_name}")
            source = validation_by_name.get(file_name)
            if source is None:
                raise ValueError(f"validation source is missing: {file_name}")
            source_label = Path(str(item.get("sourceLabel", ""))).resolve()
            source_annotation = Path(str(item.get("sourceAnnotation", ""))).resolve()
            if (
                source_label != Path(str(source["sourceLabel"])).resolve()
                or source_annotation != Path(str(source["sourceAnnotation"])).resolve()
            ):
                raise ValueError(f"validation source paths differ: {file_name}")
            source_label_hash = require_current_hash(
                source_label, item.get("sourceLabelSha256"), f"validation source label {file_name}"
            )
            source_annotation_hash = require_current_hash(
                source_annotation,
                item.get("sourceAnnotationSha256"),
                f"validation source annotation {file_name}",
            )
            if (
                source_label_hash != source["sourceLabelSha256"]
                or source_annotation_hash != source["sourceAnnotationSha256"]
                or source_label_hash != label_hash
                or source_label.read_bytes() != label_path.read_bytes()
            ):
                raise ValueError(f"materialized validation evidence differs: {file_name}")
            final_report = Path(str(item.get("finalReport", ""))).resolve()
            if final_report != validation_audit_path:
                raise ValueError(f"validation final report path differs: {file_name}")
            if require_current_hash(
                final_report,
                item.get("finalReportSha256"),
                f"validation final report {file_name}",
            ) != validation_audit_hash:
                raise ValueError(f"validation final report hash differs: {file_name}")
            validate_polygon_label(label_path, mask_count, file_name)
        mask_counts[role] += mask_count
        materialized_by_role[role].append(identity)
    reject_duplicate_identities(identities)
    validate_dataset_tree_allow_list(normalized_files, identities)

    compare_role_to_upstream(
        "train-positive", materialized_by_role["train-positive"], train_upstream
    )
    compare_role_to_upstream(
        "hard-negative", materialized_by_role["hard-negative"], hard_upstream
    )
    compare_role_to_upstream("val", materialized_by_role["val"], validation_upstream)

    roles_for_isolation = {
        **materialized_by_role,
        "frozen-test": frozen_upstream,
    }
    overlaps = pairwise_overlaps(roles_for_isolation)
    if any(overlaps.values()):
        raise ValueError(f"candidate roles are not source-isolated: {overlaps}")

    validate_split_and_sources(
        artifact_paths["splitJson"], artifact_paths["sourcesIsolationCsv"], identities
    )
    counts = materialization.get("counts")
    recomputed_counts = {
        "trainImages": len(materialized_by_role["train-positive"])
        + len(materialized_by_role["hard-negative"]),
        "trainPositiveImages": len(materialized_by_role["train-positive"]),
        "hardNegativeImages": len(materialized_by_role["hard-negative"]),
        "validationImages": len(materialized_by_role["val"]),
        "testImages": 0,
        "positiveMasks": mask_counts["train-positive"],
        "validationMasks": mask_counts["val"],
        "emptyHardNegativeLabels": empty_negative_labels,
        "orphanFiles": 0,
    }
    if counts != recomputed_counts:
        raise ValueError("materialization counts differ from current dataset")
    if recomputed_counts["trainPositiveImages"] < args.minimum_positive_images:
        raise ValueError("materialized positive image count is below minimum")
    if recomputed_counts["hardNegativeImages"] < args.minimum_hard_negative_images:
        raise ValueError("materialized hard-negative image count is below minimum")
    if recomputed_counts["validationImages"] < args.minimum_validation_images:
        raise ValueError("materialized validation image count is below minimum")
    if any((output_dir / "images" / "test").iterdir()) or any(
        (output_dir / "labels" / "test").iterdir()
    ):
        raise ValueError("candidate dataset test split is not empty")

    normalized_roles = {
        role: sorted(
            [normalized_upstream_identity(item) for item in materialized_by_role[role]],
            key=identity_sort_key,
        )
        for role in ROLES
    }
    recomputed_role_summary = {
        role: {
            "images": len(normalized_roles[role]),
            "masks": mask_counts[role],
            "sourceGroups": len(
                {group for item in normalized_roles[role] for group in item["sourceGroups"]}
            ),
            "identitiesSha256": canonical_sha256(normalized_roles[role]),
        }
        for role in ROLES
    }
    if materialization.get("roles") != recomputed_role_summary:
        raise ValueError("materialization role summaries differ from recomputed identities")
    materialization_invariants = materialization.get("invariants")
    required_materialization_invariants = (
        "allInputsHashBoundAndCurrent",
        "formalHardNegativeManifestOnly",
        "hardNegativeLabelsEmpty",
        "testSplitEmpty",
        "fileNamesDisjointAcrossRoles",
        "imageSha256DisjointAcrossRoles",
        "sourceGroupsDisjointAcrossRoles",
        "frozenTestIsolationChecked",
        "noOrphans",
        "transactionalMaterialization",
    )
    if (
        not isinstance(materialization_invariants, dict)
        or any(
            materialization_invariants.get(key) is not True
            for key in required_materialization_invariants
        )
        or int(materialization_invariants.get("minimumPositiveImages", -1))
        < FORMAL_MINIMUM_POSITIVE_IMAGES
        or int(materialization_invariants.get("minimumHardNegativeImages", -1))
        < FORMAL_MINIMUM_HARD_NEGATIVE_IMAGES
        or int(materialization_invariants.get("minimumValidationImages", -1))
        < FORMAL_MINIMUM_VALIDATION_IMAGES
    ):
        raise ValueError("materialization invariants do not prove the formal candidate gate")
    if materialization.get("overlaps") != {
        "fileName": [], "imageSha256": [], "sourceGroup": []
    }:
        raise ValueError("materialization self-reports non-canonical overlap evidence")
    all_role_identities = {
        **normalized_roles,
        "frozen-test": sorted(
            [normalized_upstream_identity(item) for item in frozen_upstream],
            key=identity_sort_key,
        ),
    }
    if materialization.get("allRolesSha256") != canonical_sha256(all_role_identities):
        raise ValueError("materialization allRolesSha256 differs from recomputed identities")

    # Re-read every mutable evidence source after all semantic checks. This closes
    # the window in which a late file addition or upstream edit could otherwise
    # become an unreported orphan between audit and report emission.
    validate_dataset_inventory(report_path, output_dir, dataset_files)
    for path, expected, label in (
        (train_index_path, train_index_hash, "training truth index"),
        (hard_manifest_path, hard_manifest_hash, "hard-negative manifest"),
        (validation_dataset_path, validation_dataset_hash, "validation dataset YAML"),
        (validation_audit_path, validation_audit_hash, "validation final audit"),
        (frozen_path, frozen_hash, "frozen test manifest"),
    ):
        require_current_hash(path, expected, label)

    input_evidence = {
        "materializationReport": {
            "path": str(report_path),
            "sha256": sha256_file(report_path),
        },
        **{key: dict(value) for key, value in inputs.items()},
    }
    return {
        "schemaVersion": 1,
        "ok": True,
        "status": "PASS",
        "decision": APPROVED_DECISION,
        "validationBridgeEligible": True,
        "candidateTrainingEligible": True,
        "trainingUse": "approved-for-candidate-training-only",
        "inputs": input_evidence,
        "outputDir": str(output_dir),
        "datasetYaml": str(dataset_path),
        "counts": recomputed_counts,
        "roles": recomputed_role_summary,
        "overlaps": overlaps,
        "allRolesSha256": canonical_sha256(all_role_identities),
        "datasetFilesSha256": canonical_sha256(dataset_files),
        "invariants": {
            "minimumPositiveImages": args.minimum_positive_images,
            "minimumHardNegativeImages": args.minimum_hard_negative_images,
            "minimumValidationImages": args.minimum_validation_images,
            "approvedPositiveAllowListExact": True,
            "formalHardNegativeAllowListExact": True,
            "validationBoundToApprovedCalibrationTruth": True,
            "testSplitEmpty": True,
            "validPositivePolygons": True,
            "pairwisePositivePolygonOverlapZero": True,
            "hardNegativeLabelsByteEmpty": True,
            "fileNameImageSha256AndSourceGroupIsolation": True,
            "allInputsAndDatasetFilesHashBound": True,
            "noOrphans": True,
        },
        "errors": [],
    }


def probe_validation_bridge(materialization_path: Path) -> tuple[bool, int]:
    """Recompute only the independently reusable validation bridge gate."""
    try:
        document = read_json(materialization_path, "candidate materialization report")
        inputs = document.get("inputs")
        if not isinstance(inputs, dict):
            return False, 0
        dataset_path, _ = evidence_path(
            inputs, "validationDatasetYaml", "validation dataset YAML"
        )
        audit_path, _ = evidence_path(
            inputs, "validationFinalAudit", "validation final audit"
        )
        records = validate_validation_audit(
            dataset_path,
            read_json(audit_path, "validation final audit"),
            FORMAL_MINIMUM_VALIDATION_IMAGES,
        )
        return True, len(records)
    except Exception:
        return False, 0


def verify_approved_report(
    report_path: str | Path,
    dataset_yaml: str | Path | None = None,
) -> dict[str, Any]:
    """Deep-replay a stored PASS report for callers such as train-yolo-seg.py.

    The function never trusts the stored PASS fields: it reloads the bound
    materialization report and all upstream evidence, then recomputes the full
    candidate-input audit from current bytes before comparing the two reports.
    """
    path = Path(report_path).resolve()
    stored = read_json(path, "candidate training input audit")
    if (
        stored.get("schemaVersion") != 1
        or stored.get("ok") is not True
        or stored.get("status") != "PASS"
        or stored.get("decision") != APPROVED_DECISION
        or stored.get("validationBridgeEligible") is not True
        or stored.get("candidateTrainingEligible") is not True
    ):
        raise ValueError("candidate training input audit is not an approved PASS")
    inputs = stored.get("inputs")
    evidence = inputs.get("materializationReport") if isinstance(inputs, dict) else None
    if not isinstance(evidence, dict):
        raise ValueError("candidate training input audit lacks materialization evidence")
    materialization_path = Path(str(evidence.get("path", ""))).resolve()
    require_current_hash(
        materialization_path,
        evidence.get("sha256"),
        "candidate materialization report",
    )
    replay_args = argparse.Namespace(
        materialization_report=str(materialization_path),
        minimum_positive_images=FORMAL_MINIMUM_POSITIVE_IMAGES,
        minimum_hard_negative_images=FORMAL_MINIMUM_HARD_NEGATIVE_IMAGES,
        minimum_validation_images=FORMAL_MINIMUM_VALIDATION_IMAGES,
        output=str(path),
    )
    recomputed = build(replay_args)
    if dataset_yaml is not None:
        expected_dataset = Path(dataset_yaml).resolve()
        if Path(str(recomputed.get("datasetYaml", ""))).resolve() != expected_dataset:
            raise ValueError("approved candidate input report belongs to another dataset")
    if stored != recomputed:
        raise ValueError("stored candidate training input report differs from deep replay")
    return recomputed


def protect_output_path(args: argparse.Namespace) -> None:
    output = Path(args.output).resolve()
    materialization_path = Path(args.materialization_report).resolve()
    if output == materialization_path:
        raise ValueError("output must not overwrite the materialization report")
    if output.exists() and output.is_dir():
        raise ValueError("output must not be an existing directory")
    if not materialization_path.is_file():
        return
    document = read_json(materialization_path, "candidate materialization report")
    output_dir = Path(str(document.get("outputDir", ""))).resolve()
    if is_within(output, output_dir):
        raise ValueError("output must be outside the materialized dataset root")
    direct_inputs = {materialization_path}
    inputs = document.get("inputs")
    if isinstance(inputs, dict):
        for evidence in inputs.values():
            if isinstance(evidence, dict) and str(evidence.get("path", "")).strip():
                direct_inputs.add(Path(str(evidence["path"])).resolve())
    if output in direct_inputs:
        raise ValueError("output must not overwrite any direct input")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit a complete canonical candidate-training input dataset."
    )
    parser.add_argument("--materialization-report", required=True)
    parser.add_argument(
        "--minimum-positive-images",
        type=int,
        default=FORMAL_MINIMUM_POSITIVE_IMAGES,
    )
    parser.add_argument(
        "--minimum-hard-negative-images",
        type=int,
        default=FORMAL_MINIMUM_HARD_NEGATIVE_IMAGES,
    )
    parser.add_argument(
        "--minimum-validation-images",
        type=int,
        default=FORMAL_MINIMUM_VALIDATION_IMAGES,
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if min(
        args.minimum_positive_images,
        args.minimum_hard_negative_images,
        args.minimum_validation_images,
    ) <= 0:
        raise ValueError("minimum image counts must be positive")
    args.minimum_positive_images = max(
        FORMAL_MINIMUM_POSITIVE_IMAGES, args.minimum_positive_images
    )
    args.minimum_hard_negative_images = max(
        FORMAL_MINIMUM_HARD_NEGATIVE_IMAGES,
        args.minimum_hard_negative_images,
    )
    args.minimum_validation_images = max(
        FORMAL_MINIMUM_VALIDATION_IMAGES, args.minimum_validation_images
    )
    output = Path(args.output).resolve()
    try:
        protect_output_path(args)
    except Exception as error:
        print(
            json.dumps(
                {
                    "ok": False,
                    "status": "HOLD",
                    "decision": HOLD_DECISION,
                    "validationBridgeEligible": False,
                    "candidateTrainingEligible": False,
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
        materialization_path = Path(args.materialization_report).resolve()
        validation_bridge_eligible, validation_images = probe_validation_bridge(
            materialization_path
        )
        report = {
            "schemaVersion": 1,
            "ok": False,
            "status": "HOLD",
            "decision": HOLD_DECISION,
            "validationBridgeEligible": validation_bridge_eligible,
            "candidateTrainingEligible": False,
            "trainingUse": "prohibited",
            "inputs": {
                "materializationReport": {
                    "path": str(materialization_path),
                    "sha256": (
                        sha256_file(materialization_path)
                        if materialization_path.is_file()
                        else None
                    ),
                }
            },
            "counts": {
                "trainPositiveImages": 0,
                "hardNegativeImages": 0,
                "validationImages": validation_images,
                "testImages": 0,
            },
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
                "validationBridgeEligible": report["validationBridgeEligible"],
                "candidateTrainingEligible": report["candidateTrainingEligible"],
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
