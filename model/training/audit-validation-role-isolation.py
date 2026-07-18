#!/usr/bin/env python3
"""Audit file-name, image-hash, and source-group isolation across data roles."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from itertools import combinations
from pathlib import Path
from typing import Any


SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
FROZEN_TEST_LANES = {"core", "stress"}


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


def require_hash(value: Any, label: str) -> str:
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


def require_identity(
    file_name: Any,
    image_hash: Any,
    source_groups: list[Any],
    label: str,
) -> dict[str, Any]:
    normalized_name = str(file_name or "")
    if not normalized_name or Path(normalized_name).name != normalized_name:
        raise ValueError(f"{label} fileName is missing or invalid")
    normalized_hash = require_hash(image_hash, f"{label} imageSha256")
    groups = sorted(
        {
            group.strip()
            for group in source_groups
            if isinstance(group, str) and group.strip()
        }
    )
    if not groups:
        raise ValueError(f"{label} sourceGroup is missing")
    return {
        "fileName": normalized_name,
        "imageSha256": normalized_hash,
        "sourceGroups": groups,
    }


def reject_duplicate_identities(role: str, records: list[dict[str, Any]]) -> None:
    for field in ("fileName", "imageSha256"):
        values = [str(item[field]) for item in records]
        duplicates = sorted({value for value in values if values.count(value) > 1})
        if duplicates:
            raise ValueError(f"{role} contains duplicate {field}: {duplicates}")


def reject_seen_identity(
    role: str,
    identity: dict[str, Any],
    seen_names: set[str],
    seen_hashes: set[str],
) -> None:
    file_name = str(identity["fileName"])
    image_hash = str(identity["imageSha256"])
    if file_name in seen_names:
        raise ValueError(f"{role} contains duplicate fileName: {file_name}")
    if image_hash in seen_hashes:
        raise ValueError(f"{role} contains duplicate imageSha256: {image_hash}")
    seen_names.add(file_name)
    seen_hashes.add(image_hash)


def validate_val_materialization(
    path: Path, document: dict[str, Any]
) -> list[dict[str, Any]]:
    if (
        document.get("ok") is not True
        or document.get("decision")
        != "canonical_validation_dataset_materialized_pending_role_isolation_audit"
    ):
        raise ValueError("val materialization report is not PASS")
    if (
        document.get("trainingUse") != "prohibited"
        or document.get("validationUse")
        != "prohibited-until-role-isolation-audit"
    ):
        raise ValueError("val materialization report has an unsafe role state")
    counts = document.get("counts")
    if not isinstance(counts, dict):
        raise ValueError("val materialization counts are missing")
    validation_images = int(counts.get("validationImages", -1))
    if validation_images < 30:
        raise ValueError(f"val materialization has only {validation_images} images")
    if int(counts.get("orphanFiles", -1)) != 0:
        raise ValueError("val materialization reports orphan files")
    if int(counts.get("trainImages", -1)) != 0 or int(counts.get("testImages", -1)) != 0:
        raise ValueError("val materialization is not validation-only")
    invariants = document.get("invariants")
    if (
        not isinstance(invariants, dict)
        or invariants.get("canonicalTruthsAreSoleAllowList") is not True
        or invariants.get("fixedValidationOnlySplit") is not True
        or invariants.get("noOrphans") is not True
    ):
        raise ValueError("val materialization invariants are incomplete")

    raw_records = document.get("records")
    if not isinstance(raw_records, list) or len(raw_records) != validation_images:
        raise ValueError("val materialization records do not match image count")
    if document.get("recordsSha256") != canonical_sha256(raw_records):
        raise ValueError("val materialization records SHA-256 drift")
    dataset_files = document.get("datasetFiles")
    if not isinstance(dataset_files, list):
        raise ValueError("val materialization datasetFiles are missing")
    if document.get("datasetFilesSha256") != canonical_sha256(dataset_files):
        raise ValueError("val materialization datasetFiles SHA-256 drift")

    output_dir = Path(str(document.get("outputDir", ""))).resolve()
    if not output_dir.is_dir():
        raise ValueError(f"val materialization outputDir is missing: {output_dir}")
    dataset_paths: set[str] = set()
    for index, item in enumerate(dataset_files, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"val dataset file {index} must be an object")
        relative = str(item.get("path", ""))
        if (
            not relative
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
        ):
            raise ValueError(f"val dataset file {index} has an invalid path")
        artifact = (output_dir / Path(relative)).resolve()
        if not is_within(artifact, output_dir):
            raise ValueError(f"val dataset file {index} escapes outputDir")
        normalized_relative = artifact.relative_to(output_dir).as_posix()
        if normalized_relative in dataset_paths:
            raise ValueError(f"val dataset file {index} has a duplicate path")
        dataset_paths.add(normalized_relative)
        expected_hash = require_hash(
            item.get("sha256"), f"val dataset file {relative}"
        )
        if not artifact.is_file() or sha256_file(artifact) != expected_hash:
            raise ValueError(f"val dataset file hash drift: {relative}")

    report_path = path.resolve()
    actual_dataset_paths = {
        artifact.resolve().relative_to(output_dir).as_posix()
        for artifact in output_dir.rglob("*")
        if artifact.is_file() and artifact.resolve() != report_path
    }
    if actual_dataset_paths != dataset_paths:
        unlisted = sorted(actual_dataset_paths - dataset_paths)
        missing = sorted(dataset_paths - actual_dataset_paths)
        raise ValueError(
            "val materialization file inventory differs from datasetFiles: "
            f"unlisted={unlisted}, missing={missing}"
        )

    records: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    seen_hashes: set[str] = set()
    for index, item in enumerate(raw_records, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"val record {index} must be an object")
        identity = require_identity(
            item.get("fileName"),
            item.get("sourceImageSha256"),
            [item.get("sourceGroup")],
            f"val record {index}",
        )
        reject_seen_identity("val", identity, seen_names, seen_hashes)
        if (
            item.get("materializedRawImageSha256") != identity["imageSha256"]
            or item.get("materializedValidationImageSha256")
            != identity["imageSha256"]
        ):
            raise ValueError(
                f"val record {identity['fileName']} materialized image SHA-256 differs"
            )
        image_path = output_dir / "images" / "val" / identity["fileName"]
        if not image_path.is_file() or sha256_file(image_path) != identity["imageSha256"]:
            raise ValueError(
                f"val materialized image hash drift: {identity['fileName']}"
            )
        records.append(identity)
    reject_duplicate_identities("val", records)
    return records


def validate_train_index(path: Path, document: dict[str, Any]) -> list[dict[str, Any]]:
    if (
        document.get("ok") is not True
        or document.get("decision") != "approved_unique_training_truth_index"
    ):
        raise ValueError("train truth index is not approved")
    inputs = document.get("inputs")
    if not isinstance(inputs, dict) or inputs.get("truthRole") != "train":
        raise ValueError("train truth index is not restricted to truthRole=train")
    if document.get("errors") not in (None, []) or document.get("conflicts") not in (
        None,
        [],
    ):
        raise ValueError("train truth index contains errors or conflicts")
    raw_records = document.get("canonicalTruths")
    if not isinstance(raw_records, list) or not raw_records:
        raise ValueError("train truth index canonicalTruths are missing")
    summary = document.get("summary")
    if (
        not isinstance(summary, dict)
        or int(summary.get("uniqueImageCount", -1)) != len(raw_records)
    ):
        raise ValueError("train truth index count differs from canonicalTruths")

    records: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    seen_hashes: set[str] = set()
    for index, item in enumerate(raw_records, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"train truth {index} must be an object")
        identity = require_identity(
            item.get("fileName"),
            item.get("imageSha256"),
            [item.get("sourceGroup")],
            f"train truth {index}",
        )
        reject_seen_identity("train", identity, seen_names, seen_hashes)
        report_path = Path(str(item.get("reportPath", ""))).resolve()
        report_hash = require_hash(
            item.get("reportSha256"), f"train truth {index} reportSha256"
        )
        if not report_path.is_file() or sha256_file(report_path) != report_hash:
            raise ValueError(f"train final report hash drift: {identity['fileName']}")
        report = read_json(report_path, f"train final report {identity['fileName']}")
        if (
            report.get("ok") is not True
            or report.get("decision")
            != "approved_as_training_truth_candidate_pending_dataset_materialization"
        ):
            raise ValueError(f"train final report is not approved: {identity['fileName']}")
        report_item = report.get("item")
        report_inputs = report.get("inputs")
        if not isinstance(report_item, dict) or not isinstance(report_inputs, dict):
            raise ValueError(f"train final report is incomplete: {identity['fileName']}")
        if (
            report_item.get("fileName") != identity["fileName"]
            or report_item.get("sha256") != identity["imageSha256"]
            or report_item.get("sourceGroup") not in identity["sourceGroups"]
        ):
            raise ValueError(f"train final report identity drift: {identity['fileName']}")
        image_path = Path(str(report_inputs.get("image", ""))).resolve()
        if (
            report_inputs.get("imageSha256") != identity["imageSha256"]
            or not image_path.is_file()
            or image_path.name != identity["fileName"]
            or sha256_file(image_path) != identity["imageSha256"]
        ):
            raise ValueError(f"train source image hash drift: {identity['fileName']}")
        records.append(identity)
    reject_duplicate_identities("train", records)
    return records


def validate_frozen_test(
    path: Path, document: dict[str, Any]
) -> list[dict[str, Any]]:
    if (
        document.get("decision") != "frozen_reviewed_candidate_not_release_ready"
        or document.get("trainingUse") != "prohibited"
    ):
        raise ValueError("frozen test manifest is not an approved training-prohibited snapshot")
    raw_records = document.get("items")
    if not isinstance(raw_records, list) or not raw_records:
        raise ValueError("frozen test manifest items are missing")
    if document.get("itemsSha256") != canonical_sha256(raw_records):
        raise ValueError("frozen test manifest items SHA-256 drift")
    counts = document.get("counts")
    if not isinstance(counts, dict) or int(counts.get("images", -1)) != len(raw_records):
        raise ValueError("frozen test image count differs from items")

    records: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    seen_hashes: set[str] = set()
    for index, item in enumerate(raw_records, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"frozen test item {index} must be an object")
        identity = require_identity(
            item.get("fileName"),
            item.get("imageSha256"),
            [item.get("sourceGroup"), item.get("parentSourceGroup")],
            f"frozen test item {index}",
        )
        reject_seen_identity("frozen-test", identity, seen_names, seen_hashes)
        if item.get("trainingUse") != "prohibited":
            raise ValueError(
                f"frozen test item is not training-prohibited: {identity['fileName']}"
            )
        lane = str(item.get("lane", ""))
        if (
            lane not in FROZEN_TEST_LANES
            or Path(lane).is_absolute()
            or Path(lane).name != lane
            or any(separator in lane for separator in ("/", "\\"))
            or ".." in Path(lane).parts
        ):
            raise ValueError(
                f"frozen test item has an invalid lane: {identity['fileName']}"
            )
        lane_root = (path.parent / "images" / lane).resolve()
        image_path = (lane_root / identity["fileName"]).resolve()
        if (
            not is_within(image_path, lane_root)
            or not image_path.is_file()
            or sha256_file(image_path) != identity["imageSha256"]
        ):
            raise ValueError(f"frozen test image hash drift: {identity['fileName']}")
        records.append(identity)
    reject_duplicate_identities("frozen-test", records)
    return records


def pick_items(document: dict[str, Any], label: str) -> list[Any]:
    for key in ("items", "records", "canonicalTruths"):
        value = document.get(key)
        if isinstance(value, list):
            if not value:
                raise ValueError(f"{label} {key} are empty")
            aggregate = document.get(f"{key}Sha256")
            if aggregate is not None and aggregate != canonical_sha256(value):
                raise ValueError(f"{label} {key} SHA-256 drift")
            return value
    raise ValueError(f"{label} items/records/canonicalTruths are missing")


def validate_hard_negatives(
    path: Path, document: dict[str, Any]
) -> list[dict[str, Any]]:
    if (
        document.get("ok") is not True
        or document.get("decision") != "approved_hard_negative_manifest"
        or document.get("trainingUse") != "permitted"
    ):
        raise ValueError("hard-negative manifest is not usable")
    raw_records = document.get("items")
    if not isinstance(raw_records, list) or not raw_records:
        raise ValueError("hard-negative manifest items are missing")
    expected_items_hash = require_hash(
        document.get("itemsSha256"), "hard-negative manifest itemsSha256"
    )
    if expected_items_hash != canonical_sha256(raw_records):
        raise ValueError("hard-negative manifest items SHA-256 drift")
    records: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    seen_hashes: set[str] = set()
    for index, item in enumerate(raw_records, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"hard-negative item {index} must be an object")
        identity = require_identity(
            item.get("fileName") or item.get("materializedFileName"),
            item.get("imageSha256") or item.get("sourceImageSha256"),
            [item.get("sourceGroup"), item.get("parentSourceGroup")],
            f"hard-negative item {index}",
        )
        reject_seen_identity("hard-negative", identity, seen_names, seen_hashes)
        path_value = item.get("imagePath") or item.get("sourceImage")
        image_path = Path(str(path_value)).resolve() if path_value else path.parent / "images" / identity["fileName"]
        if not image_path.is_file() or sha256_file(image_path) != identity["imageSha256"]:
            raise ValueError(f"hard-negative image hash drift: {identity['fileName']}")
        records.append(identity)
    reject_duplicate_identities("hard-negative", records)
    return records


def pairwise_overlaps(
    roles: dict[str, list[dict[str, Any]]]
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {
        "fileName": [],
        "imageSha256": [],
        "sourceGroup": [],
    }
    for left_role, right_role in combinations(sorted(roles), 2):
        left = roles[left_role]
        right = roles[right_role]
        for field in ("fileName", "imageSha256"):
            left_values = {str(item[field]) for item in left}
            right_values = {str(item[field]) for item in right}
            values = sorted(left_values & right_values)
            if values:
                result[field].append(
                    {"roles": [left_role, right_role], "values": values}
                )
        left_groups = {
            group for item in left for group in item["sourceGroups"]
        }
        right_groups = {
            group for item in right for group in item["sourceGroups"]
        }
        values = sorted(left_groups & right_groups)
        if values:
            result["sourceGroup"].append(
                {"roles": [left_role, right_role], "values": values}
            )
    return result


def build(args: argparse.Namespace) -> dict[str, Any]:
    input_paths = {
        "valMaterializationReport": Path(args.val_materialization_report).resolve(),
        "trainTruthIndex": Path(args.train_truth_index).resolve(),
        "frozenTestManifest": Path(args.frozen_test_manifest).resolve(),
    }
    if args.hard_negative_manifest:
        input_paths["hardNegativeManifest"] = Path(
            args.hard_negative_manifest
        ).resolve()
    inputs: dict[str, dict[str, str]] = {}
    documents: dict[str, dict[str, Any]] = {}
    for label, path in input_paths.items():
        if not path.is_file():
            raise ValueError(f"{label} is missing: {path}")
        inputs[label] = {"path": str(path), "sha256": sha256_file(path)}
        documents[label] = read_json(path, label)

    roles = {
        "val": validate_val_materialization(
            input_paths["valMaterializationReport"],
            documents["valMaterializationReport"],
        ),
        "train": validate_train_index(
            input_paths["trainTruthIndex"], documents["trainTruthIndex"]
        ),
        "frozen-test": validate_frozen_test(
            input_paths["frozenTestManifest"], documents["frozenTestManifest"]
        ),
    }
    if "hardNegativeManifest" in input_paths:
        roles["hard-negative"] = validate_hard_negatives(
            input_paths["hardNegativeManifest"],
            documents["hardNegativeManifest"],
        )

    overlaps = pairwise_overlaps(roles)
    errors = [
        f"cross-role {field} overlap: {entry['roles']} -> {entry['values']}"
        for field, entries in overlaps.items()
        for entry in entries
    ]
    ok = not errors
    role_summary = {
        role: {
            "images": len(records),
            "imageSha256": len({item["imageSha256"] for item in records}),
            "sourceGroups": len(
                {group for item in records for group in item["sourceGroups"]}
            ),
            "identitiesSha256": canonical_sha256(records),
        }
        for role, records in sorted(roles.items())
    }
    return {
        "schemaVersion": 1,
        "ok": ok,
        "status": "PASS" if ok else "HOLD",
        "decision": (
            "approved_validation_role_isolation"
            if ok
            else "hold_validation_role_isolation"
        ),
        "inputs": inputs,
        "roles": role_summary,
        "overlaps": overlaps,
        "allRolesSha256": canonical_sha256(
            {role: records for role, records in sorted(roles.items())}
        ),
        "invariants": {
            "minimumValidationImages": 30,
            "validationHasNoOrphans": True,
            "uniqueIdentityWithinEachRole": True,
            "fileNamesDisjointAcrossRoles": not overlaps["fileName"],
            "imageSha256DisjointAcrossRoles": not overlaps["imageSha256"],
            "sourceGroupsDisjointAcrossRoles": not overlaps["sourceGroup"],
            "allInputFilesHashBound": True,
        },
        "errors": errors,
    }


def input_evidence(args: argparse.Namespace) -> dict[str, dict[str, str | None]]:
    values = {
        "valMaterializationReport": args.val_materialization_report,
        "trainTruthIndex": args.train_truth_index,
        "frozenTestManifest": args.frozen_test_manifest,
        "hardNegativeManifest": args.hard_negative_manifest,
    }
    evidence: dict[str, dict[str, str | None]] = {}
    for label, value in values.items():
        if not value:
            continue
        path = Path(value).resolve()
        evidence[label] = {
            "path": str(path),
            "sha256": sha256_file(path) if path.is_file() else None,
        }
    return evidence


def protect_output_path(args: argparse.Namespace, output: Path) -> None:
    input_paths = [
        Path(value).resolve()
        for value in (
            args.val_materialization_report,
            args.train_truth_index,
            args.frozen_test_manifest,
            args.hard_negative_manifest,
        )
        if value
    ]
    if output in input_paths:
        raise ValueError("output must not equal any input file")

    val_report_path = Path(args.val_materialization_report).resolve()
    if not val_report_path.is_file():
        return
    document = read_json(val_report_path, "valMaterializationReport")
    output_dir_value = document.get("outputDir")
    if not isinstance(output_dir_value, str) or not output_dir_value.strip():
        return
    val_output_dir = Path(output_dir_value).resolve()
    if is_within(output, val_output_dir):
        raise ValueError(
            "output must not be located inside the validation materialized dataset root"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit validation isolation from train, frozen test, and hard negatives."
    )
    parser.add_argument("--val-materialization-report", required=True)
    parser.add_argument("--train-truth-index", required=True)
    parser.add_argument("--frozen-test-manifest", required=True)
    parser.add_argument("--hard-negative-manifest")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    try:
        protect_output_path(args, output)
    except Exception as error:
        print(
            json.dumps(
                {
                    "ok": False,
                    "status": "HOLD",
                    "decision": "hold_validation_role_isolation",
                    "errors": [str(error)],
                    "output": str(output),
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
            "decision": "hold_validation_role_isolation",
            "inputs": input_evidence(args),
            "roles": {},
            "overlaps": {
                "fileName": [],
                "imageSha256": [],
                "sourceGroup": [],
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
