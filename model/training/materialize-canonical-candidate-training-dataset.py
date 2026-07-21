#!/usr/bin/env python3
"""Materialize a hash-bound candidate-training YOLO segmentation dataset.

All approval, quantity, identity-isolation, and current-file checks happen
before the transactional output directory is created.  The materializer does
not promote candidate or incomplete hard-negative evidence.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
import re
import shutil
import tempfile
from itertools import combinations
from pathlib import Path
from types import ModuleType
from typing import Any


SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
ROLE_ORDER = ("train-positive", "hard-negative", "val")


def load_sibling(name: str) -> ModuleType:
    path = Path(__file__).resolve().with_name(name)
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load sibling module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ROLE_AUDITOR = load_sibling("audit-validation-role-isolation.py")
VAL_MATERIALIZER = load_sibling("materialize-canonical-validation-dataset.py")


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


def require_file_hash(path: Path, expected: Any, label: str) -> str:
    expected_hash = str(expected or "")
    if not SHA256_PATTERN.fullmatch(expected_hash):
        raise ValueError(f"{label} expected SHA-256 is invalid")
    if not path.is_file():
        raise ValueError(f"{label} is missing: {path}")
    actual = sha256_file(path)
    if actual != expected_hash:
        raise ValueError(
            f"{label} SHA-256 drift: expected={expected_hash} actual={actual}: {path}"
        )
    return actual


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def require_base_image_name(value: Any, label: str) -> str:
    file_name = str(value or "")
    if (
        not file_name
        or Path(file_name).name != file_name
        or any(separator in file_name for separator in ("/", "\\"))
        or Path(file_name).suffix.lower() not in IMAGE_SUFFIXES
    ):
        raise ValueError(f"{label} has invalid fileName: {file_name!r}")
    return file_name


def read_dataset_yaml(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key in {"path", "train", "val", "test"}:
            values[key] = value.strip().strip("'\"")
    expected = {
        "path": ".",
        "train": "images/train",
        "val": "images/val",
        "test": "images/test",
    }
    if values != expected:
        raise ValueError(f"validation dataset split paths are not canonical: {values}")
    return values


def validate_training_truths(
    index_path: Path, document: dict[str, Any], minimum: int
) -> tuple[list[dict[str, Any]], int]:
    identities = ROLE_AUDITOR.validate_train_index(index_path, document)
    truths = document.get("canonicalTruths")
    if not isinstance(truths, list) or len(truths) < minimum:
        raise ValueError(
            f"training truth index has only {len(truths) if isinstance(truths, list) else 0} "
            f"images; formal gate requires at least {minimum}"
        )
    summary = document.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("training truth index summary is missing")
    if int(summary.get("conflictingImageCount", -1)) != 0:
        raise ValueError("training truth index reports conflicts")

    identity_by_name = {item["fileName"]: item for item in identities}
    prepared: list[dict[str, Any]] = []
    total_masks = 0
    for number, truth in enumerate(truths, start=1):
        if not isinstance(truth, dict):
            raise ValueError(f"training truth {number} must be an object")
        file_name = require_base_image_name(truth.get("fileName"), f"training truth {number}")
        identity = identity_by_name.get(file_name)
        if identity is None:
            raise ValueError(f"{file_name}: training identity is missing")
        report_path = Path(str(truth.get("reportPath", ""))).resolve()
        report = read_json(report_path, f"{file_name} final report")
        inputs = report.get("inputs")
        item = report.get("item")
        if not isinstance(inputs, dict) or not isinstance(item, dict):
            raise ValueError(f"{file_name}: final report inputs/item are missing")
        mask_count = truth.get("completeMaskCount")
        if (
            not isinstance(mask_count, int)
            or isinstance(mask_count, bool)
            or mask_count < 1
            or item.get("completeMaskCount") != mask_count
        ):
            raise ValueError(f"{file_name}: completeMaskCount is invalid or drifted")
        image_path = Path(str(inputs.get("image", ""))).resolve()
        annotation_path = Path(str(truth.get("annotationPath", ""))).resolve()
        annotation_hash = str(truth.get("annotationSha256", ""))
        if (
            Path(str(inputs.get("annotation", ""))).resolve() != annotation_path
            or inputs.get("annotationSha256") != annotation_hash
        ):
            raise ValueError(f"{file_name}: annotation evidence differs from final report")
        require_file_hash(annotation_path, annotation_hash, f"{file_name} annotation")
        annotation = read_json(annotation_path, f"{file_name} annotation")
        yolo_lines, _, _ = VAL_MATERIALIZER.validate_annotation(
            annotation,
            file_name,
            str(truth.get("sourceGroup", "")),
            mask_count,
            image_path,
        )
        total_masks += mask_count
        prepared.append(
            {
                "fileName": file_name,
                "role": "train-positive",
                "split": "train",
                "sourceGroup": str(truth["sourceGroup"]),
                "sourceGroups": list(identity["sourceGroups"]),
                "imageSha256": str(truth["imageSha256"]),
                "maskCount": mask_count,
                "sourceImage": image_path,
                "sourceLabel": None,
                "sourceAnnotation": annotation_path,
                "sourceAnnotationSha256": annotation_hash,
                "labelText": "\n".join(yolo_lines) + "\n",
                "finalReport": report_path,
                "finalReportSha256": str(truth["reportSha256"]),
            }
        )
    if int(summary.get("completeMaskCount", -1)) != total_masks:
        raise ValueError("training truth completeMaskCount summary drift")
    return sorted(prepared, key=lambda item: item["fileName"]), total_masks


def validate_hard_negatives(
    manifest_path: Path, document: dict[str, Any], minimum: int
) -> list[dict[str, Any]]:
    identities = ROLE_AUDITOR.validate_hard_negatives(manifest_path, document)
    items = document.get("items")
    if not isinstance(items, list) or len(items) < minimum:
        raise ValueError(
            f"hard-negative manifest has only {len(items) if isinstance(items, list) else 0} "
            f"images; formal gate requires at least {minimum}"
        )
    identity_by_name = {item["fileName"]: item for item in identities}
    prepared: list[dict[str, Any]] = []
    for number, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"hard-negative item {number} must be an object")
        file_name = require_base_image_name(
            item.get("fileName") or item.get("materializedFileName"),
            f"hard-negative item {number}",
        )
        identity = identity_by_name.get(file_name)
        if identity is None:
            raise ValueError(f"{file_name}: hard-negative identity is missing")
        if item.get("trainingUse") not in (None, "permitted"):
            raise ValueError(f"{file_name}: hard-negative item trainingUse is not permitted")
        path_value = item.get("imagePath") or item.get("sourceImage")
        image_path = (
            Path(str(path_value)).resolve()
            if path_value
            else (manifest_path.parent / "images" / file_name).resolve()
        )
        prepared.append(
            {
                "fileName": file_name,
                "role": "hard-negative",
                "split": "train",
                "sourceGroup": str(item.get("sourceGroup") or identity["sourceGroups"][0]),
                "sourceGroups": list(identity["sourceGroups"]),
                "imageSha256": identity["imageSha256"],
                "maskCount": 0,
                "sourceImage": image_path,
                "sourceLabel": None,
                "sourceAnnotation": None,
                "sourceAnnotationSha256": None,
                "labelText": "",
                "finalReport": None,
                "finalReportSha256": None,
            }
        )
    return sorted(prepared, key=lambda entry: entry["fileName"])


def validate_materialization_inventory(
    report_path: Path, document: dict[str, Any], dataset_root: Path
) -> None:
    if (
        document.get("ok") is not True
        or document.get("decision")
        != "canonical_validation_dataset_materialized_pending_role_isolation_audit"
        or document.get("trainingUse") != "prohibited"
        or Path(str(document.get("outputDir", ""))).resolve() != dataset_root
    ):
        raise ValueError("validation materialization report is not canonical")
    files = document.get("datasetFiles")
    if (
        not isinstance(files, list)
        or document.get("datasetFilesSha256") != canonical_sha256(files)
    ):
        raise ValueError("validation materialization datasetFiles SHA-256 drift")
    expected_paths: set[str] = set()
    for number, item in enumerate(files, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"validation dataset file {number} is malformed")
        relative = str(item.get("path", ""))
        candidate = (dataset_root / relative).resolve()
        if (
            not relative
            or relative in expected_paths
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
            or not is_within(candidate, dataset_root)
        ):
            raise ValueError(f"validation dataset file {number} path is invalid")
        expected_paths.add(relative)
        require_file_hash(candidate, item.get("sha256"), f"validation dataset file {relative}")
    actual_paths = {
        path.resolve().relative_to(dataset_root).as_posix()
        for path in dataset_root.rglob("*")
        if path.is_file() and path.resolve() != report_path.resolve()
    }
    if actual_paths != expected_paths:
        raise ValueError(
            "validation dataset inventory drift: "
            f"missing={sorted(expected_paths - actual_paths)} "
            f"orphan={sorted(actual_paths - expected_paths)}"
        )


def validate_validation_dataset(
    dataset_yaml: Path,
    audit_path: Path,
    audit: dict[str, Any],
    minimum: int,
) -> tuple[list[dict[str, Any]], int]:
    dataset_hash = sha256_file(dataset_yaml)
    dataset_root = dataset_yaml.parent.resolve()
    if (
        audit.get("ok") is not True
        or audit.get("status") != "PASS"
        or audit.get("decision") != "approved_as_calibration_truth"
        or audit.get("calibrationTruthEligible") is not True
        or audit.get("trainingUse") != "prohibited"
    ):
        raise ValueError("validation final audit is not approved calibration truth")
    inputs = audit.get("inputs")
    if not isinstance(inputs, dict):
        raise ValueError("validation final audit inputs are missing")
    if not {"truthIndex", "materializationReport", "roleIsolationReport"}.issubset(inputs):
        raise ValueError("validation final audit is missing canonical evidence inputs")
    if (
        Path(str(inputs.get("datasetYaml", ""))).resolve() != dataset_yaml
        or inputs.get("datasetYamlSha256") != dataset_hash
        or Path(str(inputs.get("datasetRoot", ""))).resolve() != dataset_root
        or inputs.get("split") != "val"
    ):
        raise ValueError("validation final audit dataset binding drift")
    for key, expected in inputs.items():
        if not key.endswith("Sha256"):
            continue
        path_key = key[: -len("Sha256")]
        path_value = inputs.get(path_key)
        if isinstance(path_value, str) and path_value:
            require_file_hash(Path(path_value).resolve(), expected, f"validation audit input {path_key}")
    counts = audit.get("counts")
    if not isinstance(counts, dict):
        raise ValueError("validation final audit counts are missing")
    validation_images = int(counts.get("pass", -1))
    if (
        validation_images < minimum
        or int(counts.get("expectedImages", -1)) != validation_images
        or int(counts.get("reviewedImages", -1)) != validation_images
        or any(int(counts.get(key, -1)) != 0 for key in (
            "rework", "exclude", "invalidPolygons", "overlapPairs", "orphanFiles"
        ))
    ):
        raise ValueError("validation final audit does not satisfy the formal clean gate")
    invariants = audit.get("invariants")
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
    items = audit.get("items")
    if (
        not isinstance(items, list)
        or len(items) != validation_images
        or audit.get("itemsSha256") != canonical_sha256(items)
    ):
        raise ValueError("validation final audit items are missing or hash-drifted")
    read_dataset_yaml(dataset_yaml)
    split_path = dataset_root / "metadata" / "split.json"
    split = read_json(split_path, "validation split.json")
    expected_names = [str(item.get("fileName", "")) for item in items if isinstance(item, dict)]
    if len(expected_names) != len(items) or split != {"train": [], "val": expected_names, "test": []}:
        raise ValueError("validation split.json differs from final-audit items")
    materialization_path = Path(str(inputs.get("materializationReport", ""))).resolve()
    materialization = read_json(materialization_path, "validation materialization report")
    validate_materialization_inventory(materialization_path, materialization, dataset_root)

    prepared: list[dict[str, Any]] = []
    total_masks = 0
    seen_names: set[str] = set()
    seen_hashes: set[str] = set()
    for number, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"validation item {number} must be an object")
        file_name = require_base_image_name(item.get("fileName"), f"validation item {number}")
        image_hash = str(item.get("imageSha256", ""))
        source_group = str(item.get("sourceGroup", ""))
        if file_name in seen_names or image_hash in seen_hashes or not source_group:
            raise ValueError(f"validation item {file_name} has duplicate or missing identity")
        seen_names.add(file_name)
        seen_hashes.add(image_hash)
        image_path = dataset_root / "images" / "val" / file_name
        label_path = dataset_root / "labels" / "val" / f"{Path(file_name).stem}.txt"
        annotation_path = dataset_root / "annotations" / "raw-json" / f"{Path(file_name).stem}.json"
        require_file_hash(image_path, image_hash, f"{file_name} validation image")
        require_file_hash(label_path, item.get("labelSha256"), f"{file_name} validation label")
        require_file_hash(annotation_path, item.get("annotationSha256"), f"{file_name} validation annotation")
        mask_count = item.get("completeMaskCount")
        if not isinstance(mask_count, int) or isinstance(mask_count, bool) or mask_count < 1:
            raise ValueError(f"{file_name}: validation completeMaskCount is invalid")
        label_text = label_path.read_text(encoding="utf-8")
        if len([line for line in label_text.splitlines() if line.strip()]) != mask_count:
            raise ValueError(f"{file_name}: validation label mask count drift")
        total_masks += mask_count
        prepared.append(
            {
                "fileName": file_name,
                "role": "val",
                "split": "val",
                "sourceGroup": source_group,
                "sourceGroups": [source_group],
                "imageSha256": image_hash,
                "maskCount": mask_count,
                "sourceImage": image_path,
                "sourceLabel": label_path,
                "sourceAnnotation": annotation_path,
                "sourceAnnotationSha256": str(item["annotationSha256"]),
                "labelText": label_text,
                "finalReport": audit_path,
                "finalReportSha256": sha256_file(audit_path),
            }
        )
    if int(counts.get("validationMasks", -1)) != total_masks:
        raise ValueError("validation final audit mask count drift")
    return sorted(prepared, key=lambda entry: entry["fileName"]), total_masks


def role_identity(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "fileName": entry["fileName"],
        "imageSha256": entry["imageSha256"],
        "sourceGroups": sorted(set(entry["sourceGroups"])),
    }


def validate_isolation(
    roles: dict[str, list[dict[str, Any]]]
) -> tuple[dict[str, Any], dict[str, Any]]:
    identities = {
        role: sorted((role_identity(item) for item in entries), key=lambda item: (
            item["fileName"], item["imageSha256"], item["sourceGroups"]
        ))
        for role, entries in sorted(roles.items())
    }
    for role, entries in identities.items():
        for field in ("fileName", "imageSha256"):
            values = [item[field] for item in entries]
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate {field} within role {role}")
    overlaps: dict[str, list[dict[str, Any]]] = {
        "fileName": [], "imageSha256": [], "sourceGroup": []
    }
    for left, right in combinations(sorted(identities), 2):
        for field in ("fileName", "imageSha256"):
            values = sorted(
                {item[field] for item in identities[left]}
                & {item[field] for item in identities[right]}
            )
            if values:
                overlaps[field].append({"roles": [left, right], "values": values})
        groups_left = {g for item in identities[left] for g in item["sourceGroups"]}
        groups_right = {g for item in identities[right] for g in item["sourceGroups"]}
        values = sorted(groups_left & groups_right)
        if values:
            overlaps["sourceGroup"].append({"roles": [left, right], "values": values})
    errors = [
        f"cross-role {field} overlap: {item['roles']} -> {item['values']}"
        for field, entries in overlaps.items() for item in entries
    ]
    if errors:
        raise ValueError("; ".join(errors))
    return identities, overlaps


def validate_label_stems(entries: list[dict[str, Any]]) -> None:
    seen: dict[str, str] = {}
    for item in entries:
        stem = Path(item["fileName"]).stem
        if stem in seen:
            raise ValueError(
                f"YOLO label stem collision: {seen[stem]} and {item['fileName']}"
            )
        seen[stem] = item["fileName"]


def preflight_output(output_dir: Path, input_paths: list[Path], val_root: Path) -> None:
    if output_dir.exists():
        raise ValueError(f"output directory must not already exist: {output_dir}")
    for path in input_paths:
        if output_dir == path or is_within(path, output_dir):
            raise ValueError("output directory must not equal or contain any input")
    if is_within(output_dir, val_root):
        raise ValueError("output directory must not be inside the validation dataset root")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.tmp-", dir=str(path.parent)
    )
    os.close(handle)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def protect_report_output(args: argparse.Namespace) -> Path | None:
    if not args.report_output:
        return None
    report = Path(args.report_output).resolve()
    inputs = [
        Path(value).resolve()
        for value in (
            args.training_truth_index,
            args.hard_negative_manifest,
            args.validation_dataset,
            args.validation_final_audit,
            args.frozen_test_manifest,
        )
        if value
    ]
    output_dir = Path(args.output_dir).resolve()
    if report in inputs:
        raise ValueError("--report-output must not overwrite any input")
    if is_within(report, output_dir):
        raise ValueError("--report-output must not be located inside --output-dir")
    if report.exists():
        raise ValueError(f"--report-output must not already exist: {report}")
    return report


def failure_evidence(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    values = {
        "trainingTruthIndex": args.training_truth_index,
        "hardNegativeManifest": args.hard_negative_manifest,
        "validationDatasetYaml": args.validation_dataset,
        "validationFinalAudit": args.validation_final_audit,
        "frozenTestManifest": args.frozen_test_manifest,
    }
    inputs: dict[str, Any] = {}
    documents: dict[str, dict[str, Any]] = {}
    for label, value in values.items():
        if not value:
            continue
        path = Path(value).resolve()
        inputs[label] = {
            "path": str(path),
            "sha256": sha256_file(path) if path.is_file() else None,
        }
        if path.is_file() and path.suffix.lower() == ".json":
            try:
                documents[label] = read_json(path, label)
            except ValueError:
                pass
    train = documents.get("trainingTruthIndex", {})
    hard = documents.get("hardNegativeManifest", {})
    validation = documents.get("validationFinalAudit", {})
    hard_items = hard.get("items")
    if not isinstance(hard_items, list):
        hard_items = hard.get("candidateItems")
    if not isinstance(hard_items, list):
        hard_items = hard.get("candidates")
    observed = {
        "trainPositiveImages": (
            train.get("summary", {}).get("uniqueImageCount")
            if isinstance(train.get("summary"), dict)
            else None
        ),
        "hardNegativeImages": len(hard_items) if isinstance(hard_items, list) else None,
        "validationImages": (
            validation.get("counts", {}).get("pass")
            if isinstance(validation.get("counts"), dict)
            else None
        ),
    }
    return inputs, observed


def inventory(root: Path, excluded: set[Path] | None = None) -> list[dict[str, str]]:
    excluded = {path.resolve() for path in (excluded or set())}
    return [
        {
            "path": path.resolve().relative_to(root.resolve()).as_posix(),
            "sha256": sha256_file(path),
        }
        for path in sorted(item for item in root.rglob("*") if item.is_file())
        if path.resolve() not in excluded
    ]


def assert_output_tree(root: Path, entries: list[dict[str, Any]]) -> None:
    for split in ("train", "val", "test"):
        expected = {item["fileName"] for item in entries if item["split"] == split}
        actual = {path.name for path in (root / "images" / split).iterdir() if path.is_file()}
        if actual != expected:
            raise ValueError(f"output image {split} orphan/missing: {sorted(actual ^ expected)}")
        expected_labels = {f"{Path(name).stem}.txt" for name in expected}
        actual_labels = {path.name for path in (root / "labels" / split).iterdir() if path.is_file()}
        if actual_labels != expected_labels:
            raise ValueError(f"output label {split} orphan/missing: {sorted(actual_labels ^ expected_labels)}")


def materialize(args: argparse.Namespace) -> dict[str, Any]:
    training_index_path = Path(args.training_truth_index).resolve()
    hard_manifest_path = Path(args.hard_negative_manifest).resolve()
    validation_yaml = Path(args.validation_dataset).resolve()
    validation_audit_path = Path(args.validation_final_audit).resolve()
    frozen_path = Path(args.frozen_test_manifest).resolve() if args.frozen_test_manifest else None
    output_dir = Path(args.output_dir).resolve()
    mandatory = {
        "trainingTruthIndex": training_index_path,
        "hardNegativeManifest": hard_manifest_path,
        "validationDatasetYaml": validation_yaml,
        "validationFinalAudit": validation_audit_path,
    }
    if frozen_path is not None:
        mandatory["frozenTestManifest"] = frozen_path
    for label, path in mandatory.items():
        if not path.is_file():
            raise ValueError(f"{label} is missing: {path}")
    preflight_output(output_dir, list(mandatory.values()), validation_yaml.parent.resolve())

    input_evidence = {
        label: {"path": str(path), "sha256": sha256_file(path)}
        for label, path in mandatory.items()
    }
    train_document = read_json(training_index_path, "training truth index")
    hard_document = read_json(hard_manifest_path, "hard-negative manifest")
    val_audit = read_json(validation_audit_path, "validation final audit")
    positives, positive_masks = validate_training_truths(
        training_index_path, train_document, args.minimum_positive_images
    )
    hard_negatives = validate_hard_negatives(
        hard_manifest_path, hard_document, args.minimum_hard_negative_images
    )
    validation, validation_masks = validate_validation_dataset(
        validation_yaml, validation_audit_path, val_audit, args.minimum_validation_images
    )
    materialized_roles: dict[str, list[dict[str, Any]]] = {
        "train-positive": positives,
        "hard-negative": hard_negatives,
        "val": validation,
    }
    isolation_roles = dict(materialized_roles)
    frozen_identities: list[dict[str, Any]] = []
    if frozen_path is not None:
        frozen_document = read_json(frozen_path, "frozen test manifest")
        frozen_identities = ROLE_AUDITOR.validate_frozen_test(frozen_path, frozen_document)
        isolation_roles["frozen-test"] = frozen_identities
    identities, overlaps = validate_isolation(isolation_roles)
    entries = [item for role in ROLE_ORDER for item in materialized_roles[role]]
    validate_label_stems(entries)

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.tmp-", dir=str(output_dir.parent)))
    try:
        for split in ("train", "val", "test"):
            (temporary / "images" / split).mkdir(parents=True, exist_ok=True)
            (temporary / "labels" / split).mkdir(parents=True, exist_ok=True)
        (temporary / "metadata").mkdir(parents=True, exist_ok=True)
        records: list[dict[str, Any]] = []
        for item in entries:
            image_target = temporary / "images" / item["split"] / item["fileName"]
            label_target = temporary / "labels" / item["split"] / f"{Path(item['fileName']).stem}.txt"
            shutil.copyfile(item["sourceImage"], image_target)
            label_target.write_text(item["labelText"], encoding="utf-8")
            records.append(
                {
                    "fileName": item["fileName"],
                    "role": item["role"],
                    "split": item["split"],
                    "sourceGroup": item["sourceGroup"],
                    "sourceGroups": sorted(set(item["sourceGroups"])),
                    "imageSha256": item["imageSha256"],
                    "maskCount": item["maskCount"],
                    "sourceImage": str(item["sourceImage"]),
                    "sourceImageSha256": item["imageSha256"],
                    "sourceLabel": str(item["sourceLabel"]) if item["sourceLabel"] else None,
                    "sourceLabelSha256": sha256_file(item["sourceLabel"]) if item["sourceLabel"] else None,
                    "sourceAnnotation": str(item["sourceAnnotation"]) if item["sourceAnnotation"] else None,
                    "sourceAnnotationSha256": item["sourceAnnotationSha256"],
                    "finalReport": str(item["finalReport"]) if item["finalReport"] else None,
                    "finalReportSha256": item["finalReportSha256"],
                    "materializedImageSha256": sha256_file(image_target),
                    "materializedLabelSha256": sha256_file(label_target),
                }
            )
        train_names = [item["fileName"] for item in entries if item["split"] == "train"]
        val_names = [item["fileName"] for item in entries if item["split"] == "val"]
        split = {"train": train_names, "val": val_names, "test": []}
        split_path = temporary / "metadata" / "split.json"
        write_json(split_path, split)
        sources_path = temporary / "metadata" / "sources-isolation.csv"
        with sources_path.open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(
                target,
                fieldnames=["fileName", "role", "split", "sourceGroup", "imageSha256"],
                lineterminator="\n",
            )
            writer.writeheader()
            for record in records:
                writer.writerow({key: record[key] for key in writer.fieldnames})
        dataset_path = temporary / "dataset.yaml"
        dataset_path.write_text(
            "\n".join([
                "path: .", "train: images/train", "val: images/val", "test: images/test", "",
                "names:", "  0: nail_texture", "", "task: segment", "class_count: 1",
                "image_size: 640", "", "metadata:",
                "  dataset_version: canonical-candidate-training-dataset/v1",
                "  split_source: metadata/split.json",
                "  sources_isolation: metadata/sources-isolation.csv", "",
            ]),
            encoding="utf-8",
        )
        assert_output_tree(temporary, entries)
        report_path = temporary / "metadata" / "materialization-report.json"
        dataset_files = inventory(temporary)
        role_summaries = {
            role: {
                "images": len(materialized_roles[role]),
                "masks": sum(item["maskCount"] for item in materialized_roles[role]),
                "sourceGroups": len({group for item in identities[role] for group in item["sourceGroups"]}),
                "identitiesSha256": canonical_sha256(identities[role]),
            }
            for role in ROLE_ORDER
        }
        report = {
            "schemaVersion": 1,
            "ok": True,
            "status": "PASS",
            "decision": "approved_canonical_candidate_dataset_materialization",
            "candidateTrainingEligible": True,
            "trainingUse": "permitted-for-candidate-training-only",
            "inputs": input_evidence,
            "outputDir": str(output_dir),
            "datasetYaml": str(output_dir / "dataset.yaml"),
            "counts": {
                "trainImages": len(train_names),
                "trainPositiveImages": len(positives),
                "hardNegativeImages": len(hard_negatives),
                "validationImages": len(validation),
                "testImages": 0,
                "positiveMasks": positive_masks,
                "validationMasks": validation_masks,
                "emptyHardNegativeLabels": len(hard_negatives),
                "orphanFiles": 0,
            },
            "roles": role_summaries,
            "overlaps": overlaps,
            "allRolesSha256": canonical_sha256({role: identities[role] for role in sorted(identities)}),
            "artifacts": {
                "datasetYaml": {"path": str(output_dir / "dataset.yaml"), "sha256": sha256_file(dataset_path)},
                "splitJson": {"path": str(output_dir / "metadata" / "split.json"), "sha256": sha256_file(split_path)},
                "sourcesIsolationCsv": {"path": str(output_dir / "metadata" / "sources-isolation.csv"), "sha256": sha256_file(sources_path)},
            },
            "recordsSha256": canonical_sha256(records),
            "datasetFilesSha256": canonical_sha256(dataset_files),
            "datasetFiles": dataset_files,
            "records": records,
            "invariants": {
                "minimumPositiveImages": args.minimum_positive_images,
                "minimumHardNegativeImages": args.minimum_hard_negative_images,
                "minimumValidationImages": args.minimum_validation_images,
                "allInputsHashBoundAndCurrent": True,
                "formalHardNegativeManifestOnly": True,
                "hardNegativeLabelsEmpty": True,
                "testSplitEmpty": True,
                "fileNamesDisjointAcrossRoles": True,
                "imageSha256DisjointAcrossRoles": True,
                "sourceGroupsDisjointAcrossRoles": True,
                "frozenTestIsolationChecked": frozen_path is not None,
                "noOrphans": True,
                "transactionalMaterialization": True,
            },
            "errors": [],
        }
        write_json(report_path, report)
        if inventory(temporary, {report_path}) != dataset_files:
            raise ValueError("dataset file inventory changed after report creation")
        assert_output_tree(temporary, entries)
        os.replace(temporary, output_dir)
        return report
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize the canonical candidate-training YOLO dataset.")
    parser.add_argument("--training-truth-index", required=True)
    parser.add_argument("--hard-negative-manifest", required=True)
    parser.add_argument("--validation-dataset", required=True, help="canonical validation dataset.yaml")
    parser.add_argument("--validation-final-audit", required=True)
    parser.add_argument("--frozen-test-manifest")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--report-output",
        help="optional external PASS/HOLD evidence; never written inside output-dir",
    )
    parser.add_argument("--minimum-positive-images", type=int, default=100)
    parser.add_argument("--minimum-hard-negative-images", type=int, default=100)
    parser.add_argument("--minimum-validation-images", type=int, default=30)
    args = parser.parse_args()
    if args.minimum_positive_images < 100:
        raise ValueError("--minimum-positive-images cannot weaken the formal 100-image gate")
    if args.minimum_hard_negative_images < 100:
        raise ValueError("--minimum-hard-negative-images cannot weaken the formal 100-image gate")
    if args.minimum_validation_images < 30:
        raise ValueError("--minimum-validation-images cannot weaken the formal 30-image gate")
    report_output: Path | None = None
    try:
        report_output = protect_report_output(args)
        report = materialize(args)
    except Exception as error:
        hold_inputs, observed_counts = failure_evidence(args)
        hold = {
            "ok": False,
            "status": "HOLD",
            "decision": "hold_canonical_candidate_dataset_materialization",
            "candidateTrainingEligible": False,
            "outputDir": str(Path(args.output_dir).resolve()),
            "inputs": hold_inputs,
            "observedCounts": observed_counts,
            "requiredCounts": {
                "trainPositiveImages": max(100, args.minimum_positive_images),
                "hardNegativeImages": max(100, args.minimum_hard_negative_images),
                "validationImages": max(30, args.minimum_validation_images),
            },
            "errors": [str(error)],
        }
        if report_output is not None:
            write_json_atomic(report_output, hold)
            hold["reportOutput"] = str(report_output)
        print(json.dumps(hold, ensure_ascii=False, indent=2))
        raise SystemExit(1)
    if report_output is not None:
        write_json_atomic(report_output, report)
    print(json.dumps({
        "ok": True,
        "status": report["status"],
        "decision": report["decision"],
        "counts": report["counts"],
        "recordsSha256": report["recordsSha256"],
        "datasetFilesSha256": report["datasetFilesSha256"],
        "outputDir": report["outputDir"],
        "reportOutput": str(report_output) if report_output else None,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
