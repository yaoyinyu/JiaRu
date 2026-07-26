"""Strict validation for train, validation, and frozen release-test identities."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
ROLE_MINIMUMS = {"train": 100, "val": 30, "frozenTest": 100}
ROLE_DECISIONS = {
    "train": "approved_unique_training_truth_index",
    "val": "approved_unique_validation_truth_index",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def require_sha256(value: Any, label: str) -> str:
    result = str(value or "")
    if not SHA256_PATTERN.fullmatch(result):
        raise ValueError(f"{label} is not a lowercase SHA-256")
    return result


def require_current_file(path_value: Any, hash_value: Any, label: str) -> Path:
    path = Path(str(path_value or "")).resolve()
    expected = require_sha256(hash_value, f"{label} expected SHA-256")
    if not path.is_file() or sha256_file(path) != expected:
        raise ValueError(f"{label} is missing or its SHA-256 has drifted: {path}")
    return path


def require_nonempty(value: Any, label: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ValueError(f"{label} is missing")
    return result


def validate_truth_index(role: str, document: dict[str, Any]) -> None:
    truths = document.get("canonicalTruths")
    summary = document.get("summary")
    if (
        document.get("schemaVersion") != 1
        or document.get("ok") is not True
        or document.get("decision") != ROLE_DECISIONS[role]
        or not isinstance(truths, list)
        or not isinstance(summary, dict)
        or len(truths) < ROLE_MINIMUMS[role]
        or summary.get("uniqueImageCount") != len(truths)
        or document.get("errors") not in (None, [])
        or document.get("conflicts") not in (None, [])
    ):
        raise ValueError(f"{role} truth index does not satisfy the formal role contract")
    complete_masks = 0
    names: set[str] = set()
    hashes: set[str] = set()
    reports: set[str] = set()
    for number, item in enumerate(truths, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"{role} canonical truth {number} must be an object")
        file_name = require_nonempty(item.get("fileName"), f"{role} truth fileName")
        image_hash = require_sha256(
            item.get("imageSha256"),
            f"{role} truth {file_name} image SHA-256",
        )
        require_nonempty(item.get("sourceGroup"), f"{role} truth {file_name} sourceGroup")
        report = require_current_file(
            item.get("reportPath"),
            item.get("reportSha256"),
            f"{role} truth {file_name} report",
        )
        mask_count = item.get("completeMaskCount")
        if isinstance(mask_count, bool) or not isinstance(mask_count, int) or mask_count < 1:
            raise ValueError(f"{role} truth {file_name} has invalid completeMaskCount")
        complete_masks += mask_count
        if (
            file_name.casefold() in names
            or image_hash in hashes
            or str(report).casefold() in reports
        ):
            raise ValueError(f"{role} truth index contains duplicate identities")
        names.add(file_name.casefold())
        hashes.add(image_hash)
        reports.add(str(report).casefold())
    if summary.get("completeMaskCount") != complete_masks:
        raise ValueError(f"{role} truth index completeMaskCount differs from truths")


def validate_frozen_test(
    document: dict[str, Any],
    protected_paths: dict[str, Path],
) -> None:
    items = document.get("items")
    counts = document.get("counts")
    representative = document.get("representativeReleaseGate")
    isolation = document.get("sourceIsolation")
    inputs = document.get("inputs")
    if (
        document.get("schemaVersion") != 2
        or document.get("decision") != "frozen_reviewed_candidate_not_release_ready"
        or document.get("trainingUse") != "prohibited"
        or not isinstance(items, list)
        or len(items) < ROLE_MINIMUMS["frozenTest"]
        or not isinstance(counts, dict)
        or counts.get("images") != len(items)
        or document.get("itemsSha256") != canonical_sha256(items)
        or not isinstance(representative, dict)
        or representative.get("ok") is not True
        or representative.get("actual") != len(items)
        or int(representative.get("required", 0)) < ROLE_MINIMUMS["frozenTest"]
        or representative.get("shortfall") != 0
        or not isinstance(isolation, dict)
        or isolation.get("ok") is not True
        or any(
            isolation.get(key) != 0
            for key in (
                "trainValidationOverlap",
                "trainReleaseTestOverlap",
                "validationReleaseTestOverlap",
                "baseSupplementalOverlap",
            )
        )
        or not isinstance(inputs, dict)
    ):
        raise ValueError("frozenTest manifest does not satisfy the formal role contract")

    for role, path_key, hash_key in (
        ("train", "trainTruthIndex", "trainTruthIndexSha256"),
        ("val", "validationTruthIndex", "validationTruthIndexSha256"),
    ):
        bound = require_current_file(
            inputs.get(path_key),
            inputs.get(hash_key),
            f"frozenTest {role} truth input",
        )
        if bound != protected_paths[role]:
            raise ValueError(
                f"frozenTest {role} truth input differs from selected protected evidence"
            )
    for path_key, hash_key, label in (
        ("baseSnapshot", "baseSnapshotSha256", "frozenTest base snapshot"),
        (
            "supplementalTruthIndex",
            "supplementalTruthIndexSha256",
            "frozenTest supplemental truth index",
        ),
    ):
        require_current_file(inputs.get(path_key), inputs.get(hash_key), label)

    names: set[str] = set()
    hashes: set[str] = set()
    mask_total = 0
    core = 0
    stress = 0
    for number, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"frozenTest item {number} must be an object")
        file_name = require_nonempty(item.get("fileName"), "frozenTest fileName")
        image_hash = require_sha256(
            item.get("imageSha256"),
            f"frozenTest {file_name} image SHA-256",
        )
        require_sha256(
            item.get("annotationSha256"),
            f"frozenTest {file_name} annotation SHA-256",
        )
        require_nonempty(item.get("sourceGroup"), f"frozenTest {file_name} sourceGroup")
        require_nonempty(
            item.get("parentSourceGroup"),
            f"frozenTest {file_name} parentSourceGroup",
        )
        if item.get("trainingUse") != "prohibited":
            raise ValueError(f"frozenTest {file_name} is not training-prohibited")
        uses = set(item.get("authorizedUses") or [])
        if not {"independent-release-test", "long-term-regression"}.issubset(uses):
            raise ValueError(f"frozenTest {file_name} lacks release/regression authorization")
        mask_count = item.get("maskCount")
        if isinstance(mask_count, bool) or not isinstance(mask_count, int) or mask_count < 1:
            raise ValueError(f"frozenTest {file_name} has invalid maskCount")
        mask_total += mask_count
        lane = item.get("lane")
        if lane == "core":
            core += 1
        elif lane == "stress":
            stress += 1
        else:
            raise ValueError(f"frozenTest {file_name} has invalid lane")
        if file_name.casefold() in names or image_hash in hashes:
            raise ValueError("frozenTest manifest contains duplicate identities")
        names.add(file_name.casefold())
        hashes.add(image_hash)
    if (
        counts.get("masks") != mask_total
        or counts.get("coreImages") != core
        or counts.get("stressImages") != stress
    ):
        raise ValueError("frozenTest counts differ from current items")


def validate_protected_role_documents(
    protected_paths: dict[str, Path],
    documents: dict[str, dict[str, Any]],
) -> None:
    if set(protected_paths) != {"train", "val", "frozenTest"}:
        raise ValueError("protected role paths must contain train, val, and frozenTest")
    if set(documents) != set(protected_paths):
        raise ValueError("protected role documents differ from selected paths")
    validate_truth_index("train", documents["train"])
    validate_truth_index("val", documents["val"])
    validate_frozen_test(documents["frozenTest"], protected_paths)
