#!/usr/bin/env python3
"""Freeze a user-authorized independent hard-negative batch before inference.

The command cannot create user authorization from free text. It consumes a
pre-existing authorization source, binds one candidate weight file and one
explicit contiguous batch range, rejects exact and perceptual duplicates, and
atomically creates a fixed evidence directory inside the source root.

The evidence is candidate-only. It never assigns training, validation, test,
or holdout roles and cannot be overwritten or recreated under another output
path by this command.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sys
import uuid
from collections import Counter
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from types import ModuleType
from typing import Any

from PIL import Image, UnidentifiedImageError


FORMAL_MINIMUM_IMAGES = 100
FORMAL_NEAR_DUPLICATE_DISTANCE = 12
EVIDENCE_DIRECTORY_NAME = "_independent_holdout_freeze_v1"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
IMAGE_FORMAT_BY_SUFFIX = {
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
    ".webp": "WEBP",
}
FILE_PATTERN = re.compile(
    r"^hard_negative_independent_(?P<date>\d{8})_(?P<sequence>\d{3})_"
    r"(?P<family>[a-z0-9_]+)_(?P<variant>\d{2})\.(?P<suffix>png|jpe?g|webp)$",
    re.IGNORECASE,
)
DATE_PATTERN = re.compile(r"^\d{8}$")
REQUIRED_AUTHORIZED_USES = {
    "independent-release-test",
    "long-term-regression",
    "model-diagnostic-evaluation",
    "data-quality-review",
}
UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
FILE_ATTRIBUTE_REPARSE_POINT = 0x0400


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


def read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is unreadable JSON: {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain an object: {path}")
    return value


def load_threshold_calibrator() -> ModuleType:
    script = Path(__file__).with_name("calibrate-model-score-threshold.py")
    spec = importlib.util.spec_from_file_location(
        "independent_holdout_threshold_calibrator",
        script,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load candidate threshold calibrator")
    module = importlib.util.module_from_spec(spec)
    sibling_directory = str(script.parent)
    inserted = sibling_directory not in sys.path
    if inserted:
        sys.path.insert(0, sibling_directory)
    try:
        spec.loader.exec_module(module)
    finally:
        if inserted:
            sys.path.remove(sibling_directory)
    return module


def load_training_authorization_recorder() -> ModuleType:
    script = Path(__file__).with_name(
        "record-training-hard-negative-authorization.py"
    )
    spec = importlib.util.spec_from_file_location(
        "independent_holdout_training_authorization_recorder",
        script,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load training hard-negative authorization recorder")
    module = importlib.util.module_from_spec(spec)
    sibling_directory = str(script.parent)
    inserted = sibling_directory not in sys.path
    if inserted:
        sys.path.insert(0, sibling_directory)
    try:
        spec.loader.exec_module(module)
    finally:
        if inserted:
            sys.path.remove(sibling_directory)
    return module


def difference_hash(image: Image.Image, size: int = 16) -> str:
    grayscale = image.convert("L").resize(
        (size + 1, size),
        Image.Resampling.LANCZOS,
    )
    pixels = list(grayscale.get_flattened_data())
    bits = 0
    for row in range(size):
        offset = row * (size + 1)
        for column in range(size):
            bits = (bits << 1) | int(
                pixels[offset + column] > pixels[offset + column + 1]
            )
    return f"{bits:0{size * size // 4}x}"


def hamming_distance(left: str, right: str) -> int:
    return (int(left, 16) ^ int(right, 16)).bit_count()


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def is_link_or_reparse_point(path: Path) -> bool:
    try:
        attributes = int(getattr(path.lstat(), "st_file_attributes", 0))
    except OSError as error:
        raise ValueError(f"cannot inspect filesystem entry: {path}: {error}") from error
    return (
        path.is_symlink()
        or bool(getattr(path, "is_junction", lambda: False)())
        or bool(attributes & FILE_ATTRIBUTE_REPARSE_POINT)
    )


def reject_linked_entries(source_root: Path) -> None:
    stack = [source_root]
    while stack:
        directory = stack.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError as error:
            raise ValueError(f"cannot enumerate source directory: {directory}: {error}") from error
        for entry in entries:
            path = Path(entry.path)
            if is_link_or_reparse_point(path):
                raise ValueError(
                    f"symbolic link, junction, or reparse-point entry is prohibited: {path}"
                )
            if entry.is_dir(follow_symlinks=False):
                stack.append(path)


def decode_image(path: Path) -> tuple[int, int, str, str]:
    try:
        with Image.open(path) as image:
            width, height = image.size
            image_format = str(image.format or "").upper()
            image.verify()
        with Image.open(path) as image:
            image.load()
            if image.size != (width, height):
                raise ValueError("image dimensions changed during decode")
            perceptual_hash = difference_hash(image)
    except (OSError, RuntimeError, SyntaxError, UnidentifiedImageError) as error:
        raise ValueError(f"image cannot be fully decoded: {path}: {error}") from error
    expected_format = IMAGE_FORMAT_BY_SUFFIX.get(path.suffix.lower())
    if image_format != expected_format:
        raise ValueError(
            f"image format {image_format!r} differs from suffix contract "
            f"{expected_format!r}: {path}"
        )
    if min(width, height) < 320:
        raise ValueError(f"image minimum side is below 320px: {path}")
    return width, height, image_format, perceptual_hash


def validate_user_authorization(
    path: Path,
    source_root: Path,
) -> tuple[dict[str, Any], list[str]]:
    authorization = read_json(path, "user authorization source")
    if (
        authorization.get("schemaVersion") != 1
        or authorization.get("ok") is not True
        or authorization.get("decision")
        != "authorized_for_independent_holdout_evaluation"
        or authorization.get("confirmedBy") != "workspace-user"
        or authorization.get("qualityConstraint")
        != "authorization-does-not-relax-quality-gates"
    ):
        raise ValueError("user authorization source does not satisfy the holdout contract")
    confirmation_note = str(authorization.get("confirmationNote") or "").strip()
    if not confirmation_note:
        raise ValueError("user authorization source confirmationNote is missing")
    authorization_evidence = authorization.get("authorizationEvidence")
    if not isinstance(authorization_evidence, dict):
        raise ValueError("user authorization source authorizationEvidence is missing")
    evidence_text = str(
        authorization_evidence.get("userMessageText") or ""
    ).strip()
    evidence_thread_id = str(
        authorization_evidence.get("threadId") or ""
    ).strip()
    evidence_decision_id = str(
        authorization_evidence.get("decisionId") or ""
    ).strip()
    if (
        authorization_evidence.get("kind") != "codex-user-message"
        or evidence_text != confirmation_note
        or authorization_evidence.get("userMessageSha256")
        != hashlib.sha256(evidence_text.encode("utf-8")).hexdigest()
        or not UUID_PATTERN.fullmatch(evidence_thread_id)
        or not evidence_decision_id
        or evidence_thread_id not in evidence_decision_id
    ):
        raise ValueError(
            "user authorization source does not bind a traceable user-message decision"
        )
    authorized_uses = sorted(
        {
            str(value)
            for value in list(authorization.get("authorizedUses") or [])
            if str(value)
        }
    )
    if set(authorized_uses) != REQUIRED_AUTHORIZED_USES:
        raise ValueError(
            "user authorization source authorizedUses must exactly equal the "
            f"independent-holdout allowlist: {sorted(REQUIRED_AUTHORIZED_USES)}"
        )

    authorized_root_raw = Path(str(authorization.get("sourceRoot") or ""))
    if not authorized_root_raw.is_absolute():
        raise ValueError("user authorization sourceRoot must be absolute")
    authorized_root = authorized_root_raw.resolve()
    if authorized_root != source_root:
        raise ValueError(
            "user authorization sourceRoot must exactly match the frozen batch root"
        )
    return authorization, authorized_uses


def enumerate_batch(
    source_root: Path,
    batch_date: str,
    sequence_start: int,
    sequence_end: int,
) -> list[dict[str, Any]]:
    reject_linked_entries(source_root)
    expected_sequences = set(range(sequence_start, sequence_end + 1))
    expected_images = len(expected_sequences)
    if expected_images < FORMAL_MINIMUM_IMAGES:
        raise ValueError(
            f"batch range cannot lower the formal {FORMAL_MINIMUM_IMAGES}-image gate"
        )

    files = sorted(
        path
        for path in source_root.rglob("*")
        if path.is_file()
        and path.suffix.lower() in IMAGE_SUFFIXES
        and EVIDENCE_DIRECTORY_NAME not in path.parts
    )
    if len(files) != expected_images:
        raise ValueError(
            f"image count differs from the explicit batch range: "
            f"expected={expected_images} actual={len(files)}"
        )

    records: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    seen_hashes: set[str] = set()
    seen_sequences: set[int] = set()
    for path in files:
        if is_link_or_reparse_point(path):
            raise ValueError(f"linked image is prohibited: {path}")
        resolved_path = path.resolve()
        if not is_relative_to(resolved_path, source_root):
            raise ValueError(f"image resolves outside source root: {path}")
        for parent in path.parents:
            if parent == source_root:
                break
            if is_link_or_reparse_point(parent):
                raise ValueError(f"linked directory is prohibited: {parent}")

        file_name = path.name
        match = FILE_PATTERN.fullmatch(file_name)
        if not match:
            raise ValueError(f"file name does not match the frozen contract: {file_name}")
        if match.group("date") != batch_date:
            raise ValueError(f"file date differs from --batch-date: {file_name}")
        sequence = int(match.group("sequence"))
        if sequence not in expected_sequences:
            raise ValueError(f"file sequence is outside the explicit range: {file_name}")
        if file_name.casefold() in seen_names:
            raise ValueError(f"duplicate file name: {file_name}")
        if sequence in seen_sequences:
            raise ValueError(f"duplicate sequence number: {sequence:03d}")

        image_hash = sha256_file(resolved_path)
        if image_hash in seen_hashes:
            raise ValueError(f"duplicate image SHA-256: {file_name}")
        width, height, image_format, perceptual_hash = decode_image(resolved_path)
        seen_names.add(file_name.casefold())
        seen_hashes.add(image_hash)
        seen_sequences.add(sequence)
        records.append(
            {
                "fileName": file_name,
                "relativePath": path.relative_to(source_root).as_posix(),
                "sourcePath": str(resolved_path),
                "sha256": image_hash,
                "width": width,
                "height": height,
                "format": image_format,
                "bytes": resolved_path.stat().st_size,
                "dhash256": perceptual_hash,
                "sequence": sequence,
                "batchDate": match.group("date"),
                "promptFamily": match.group("family").lower(),
                "promptVariant": int(match.group("variant")),
            }
        )

    if seen_sequences != expected_sequences:
        missing = sorted(expected_sequences - seen_sequences)
        raise ValueError(f"batch sequences are not contiguous; missing={missing}")
    records.sort(key=lambda item: int(item["sequence"]))
    return records


def reject_protected_overlaps(
    records: list[dict[str, Any]],
    protected_records: list[dict[str, Any]],
) -> dict[str, Any]:
    protected_hashes = {
        str(item["imageSha256"]): str(item["fileName"])
        for item in protected_records
    }
    protected_source_identities = {
        str(item["sourceIdentity"]): str(item["fileName"])
        for item in protected_records
    }
    recorder = load_training_authorization_recorder()
    comparisons = 0
    for record in records:
        image_hash = str(record["sha256"])
        if image_hash in protected_hashes:
            raise ValueError(
                "new independent holdout exactly duplicates a protected hard negative: "
                f"{record['fileName']} == {protected_hashes[image_hash]}"
            )
        source_group = (
            f"ai-hard-negative-independent-{record['batchDate']}:"
            f"{record['promptFamily']}"
        )
        source_identity = recorder.normalize_protected_source_group(source_group)
        record["sourceGroup"] = source_group
        record["sourceIdentity"] = source_identity
        if source_identity in protected_source_identities:
            raise ValueError(
                "new independent holdout sourceGroup overlaps a protected hard "
                f"negative source: {record['fileName']} ~= "
                f"{protected_source_identities[source_identity]}"
            )
        for protected in protected_records:
            comparisons += 1
            distance = hamming_distance(
                str(record["dhash256"]),
                str(protected["dhash256"]),
            )
            if distance <= FORMAL_NEAR_DUPLICATE_DISTANCE:
                raise ValueError(
                    "new independent holdout perceptually duplicates a protected "
                    f"hard negative at dHash256 distance {distance}: "
                    f"{record['fileName']} ~= {protected['fileName']}"
                )
    return {
        "decision": "pass_no_protected_hard_negative_overlap",
        "candidateRecordCount": len(records),
        "protectedRecordCount": len(protected_records),
        "protectedRecordsSha256": canonical_sha256(protected_records),
        "exactSha256Matches": 0,
        "sourceIdentityMatches": 0,
        "perceptualMatchesAtOrBelowThreshold": 0,
        "perceptualComparisons": comparisons,
        "nearDuplicateThreshold": FORMAL_NEAR_DUPLICATE_DISTANCE,
    }


def find_near_duplicate_pairs(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for left, right in combinations(records, 2):
        distance = hamming_distance(
            str(left["dhash256"]),
            str(right["dhash256"]),
        )
        if distance <= FORMAL_NEAR_DUPLICATE_DISTANCE:
            result.append(
                {
                    "left": left["fileName"],
                    "right": right["fileName"],
                    "dhashDistance": distance,
                }
            )
    return result


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def require_bound_file(
    path_value: Any,
    hash_value: Any,
    label: str,
) -> Path:
    path = Path(str(path_value or "")).resolve()
    expected_hash = str(hash_value or "")
    if not path.is_file() or sha256_file(path) != expected_hash:
        raise ValueError(f"{label} is missing or its SHA-256 has drifted: {path}")
    return path


def require_bound_relative_file(
    freeze_dir: Path,
    record: Any,
    label: str,
) -> Path:
    if not isinstance(record, dict):
        raise ValueError(f"{label} binding is missing")
    relative = Path(str(record.get("pathWithinFreeze") or ""))
    if relative.is_absolute() or len(relative.parts) != 1:
        raise ValueError(f"{label} pathWithinFreeze must be one relative file name")
    path = (freeze_dir / relative).resolve()
    if path.parent != freeze_dir.resolve():
        raise ValueError(f"{label} escapes the freeze directory")
    return require_bound_file(path, record.get("sha256"), label)


def verify_threshold_report(
    path: Path,
    candidate_weights: Path,
) -> dict[str, Any]:
    verified = load_threshold_calibrator().verify_calibration_report(
        path,
        candidate_weights,
    )
    score_threshold = float(verified["scoreThreshold"])
    return {
        "path": str(Path(verified["reportPath"]).resolve()),
        "sha256": str(verified["reportSha256"]),
        "scoreThreshold": score_threshold,
        "weightsSha256": str(verified["weightsSha256"]),
        "decision": str(verified["decision"]),
    }


def verify_freeze_manifest(path: Path) -> dict[str, Any]:
    manifest_path = path.resolve()
    manifest = read_json(manifest_path, "independent holdout freeze manifest")
    if (
        manifest.get("schemaVersion") != 1
        or manifest.get("ok") is not True
        or manifest.get("decision")
        != "independent_holdout_frozen_before_authorized_inference"
        or manifest.get("datasetRole")
        != "candidate-only-pending-original-resolution-review"
        or manifest.get("trainingUse") != "prohibited"
    ):
        raise ValueError("freeze manifest does not satisfy the candidate-only contract")
    freeze_dir = manifest_path.parent
    if freeze_dir.name != EVIDENCE_DIRECTORY_NAME:
        raise ValueError("freeze manifest is outside the fixed evidence directory")
    if manifest_path.name != "freeze-manifest-v1.json":
        raise ValueError("freeze manifest must use the fixed evidence file name")
    source_root = Path(str(manifest.get("sourceRoot") or "")).resolve()
    if freeze_dir.parent.resolve() != source_root:
        raise ValueError("fixed freeze directory is not inside the declared source root")

    inputs = manifest.get("inputs")
    if not isinstance(inputs, dict):
        raise ValueError("freeze manifest inputs are missing")
    user_authorization_path = require_bound_file(
        inputs.get("userAuthorizationSource", {}).get("path")
        if isinstance(inputs.get("userAuthorizationSource"), dict)
        else None,
        inputs.get("userAuthorizationSource", {}).get("sha256")
        if isinstance(inputs.get("userAuthorizationSource"), dict)
        else None,
        "user authorization source",
    )
    candidate_weights = require_bound_file(
        inputs.get("candidateWeights", {}).get("path")
        if isinstance(inputs.get("candidateWeights"), dict)
        else None,
        inputs.get("candidateWeights", {}).get("sha256")
        if isinstance(inputs.get("candidateWeights"), dict)
        else None,
        "candidate weights",
    )
    threshold_report_input = inputs.get("candidateThresholdReport")
    if not isinstance(threshold_report_input, dict):
        raise ValueError("candidate threshold report binding is missing")
    threshold_report = require_bound_file(
        threshold_report_input.get("path"),
        threshold_report_input.get("sha256"),
        "candidate threshold report",
    )
    threshold_verification = verify_threshold_report(
        threshold_report,
        candidate_weights,
    )
    if (
        threshold_verification["scoreThreshold"]
        != threshold_report_input.get("scoreThreshold")
        or threshold_verification["weightsSha256"]
        != sha256_file(candidate_weights)
    ):
        raise ValueError("candidate threshold report binding differs from deep replay")
    registry_input = inputs.get("protectedHardNegativeRegistry")
    protected_manifest_inputs = inputs.get("protectedHardNegativeManifests")
    if not isinstance(registry_input, dict) or not isinstance(
        protected_manifest_inputs, list
    ):
        raise ValueError(
            "freeze manifest omits the protected hard-negative registry binding"
        )
    registry_path = require_bound_file(
        registry_input.get("path"),
        registry_input.get("sha256"),
        "protected hard-negative registry",
    )
    training_recorder = load_training_authorization_recorder()
    (
        registry_binding,
        protected_manifest_bindings,
        protected_records,
    ) = training_recorder.load_protected_registry(str(registry_path))
    if registry_binding != registry_input:
        raise ValueError("protected hard-negative registry binding drift")
    if protected_manifest_bindings != protected_manifest_inputs:
        raise ValueError("protected hard-negative manifest binding drift")
    machine_audit_path = require_bound_relative_file(
        freeze_dir,
        inputs.get("machineAudit"),
        "machine audit",
    )
    authorization_record_path = require_bound_relative_file(
        freeze_dir,
        inputs.get("authorizationRecord"),
        "authorization record",
    )
    if machine_audit_path.name != "machine-audit-v1.json":
        raise ValueError("machine audit must use the fixed evidence file name")
    if authorization_record_path.name != "authorization-record-A-v1.json":
        raise ValueError("authorization record must use the fixed evidence file name")
    machine_audit = read_json(machine_audit_path, "machine audit")
    authorization_record = read_json(authorization_record_path, "authorization record")
    batch_identity = manifest.get("batchIdentity")
    if not isinstance(batch_identity, dict):
        raise ValueError("freeze batchIdentity is missing")
    batch_identity_sha256 = canonical_sha256(batch_identity)
    if (
        manifest.get("batchIdentitySha256") != batch_identity_sha256
        or machine_audit.get("batchIdentity") != batch_identity
        or machine_audit.get("batchIdentitySha256") != batch_identity_sha256
        or authorization_record.get("batchIdentity") != batch_identity
        or authorization_record.get("batchIdentitySha256") != batch_identity_sha256
    ):
        raise ValueError("freeze, machine audit, and authorization batch identities differ")
    if sha256_file(candidate_weights) != batch_identity.get("candidateWeightsSha256"):
        raise ValueError("candidate weights differ from the frozen batch identity")
    if (
        batch_identity.get("candidateThresholdReportSha256")
        != threshold_verification["sha256"]
        or batch_identity.get("candidateScoreThreshold")
        != threshold_verification["scoreThreshold"]
    ):
        raise ValueError("candidate threshold differs from the frozen batch identity")

    user_authorization, authorized_uses = validate_user_authorization(
        user_authorization_path,
        source_root,
    )
    current_records = enumerate_batch(
        source_root,
        str(batch_identity.get("batchDate") or ""),
        int(batch_identity.get("sequenceStart", -1)),
        int(batch_identity.get("sequenceEnd", -1)),
    )
    if find_near_duplicate_pairs(current_records):
        raise ValueError("current frozen batch no longer passes the perceptual duplicate gate")
    protected_cross_check = reject_protected_overlaps(
        current_records,
        protected_records,
    )
    current_records_sha256 = canonical_sha256(current_records)
    if (
        current_records_sha256 != batch_identity.get("recordsSha256")
        or machine_audit.get("records") != current_records
        or machine_audit.get("recordsSha256") != current_records_sha256
    ):
        raise ValueError("current image records differ from the frozen machine audit")

    entries = authorization_record.get("entries")
    if not isinstance(entries, list):
        raise ValueError("authorization record entries are missing")
    expected_entries = [
        {
            "fileName": item["fileName"],
            "sourcePath": item["sourcePath"],
            "sha256": item["sha256"],
            "width": item["width"],
            "height": item["height"],
            "authorizedUses": authorization_record["authorizedUses"],
            "trainingEligibility": "prohibited-independent-holdout-only",
        }
        for item in current_records
    ]
    if (
        entries != expected_entries
        or authorization_record.get("entriesSha256") != canonical_sha256(entries)
        or authorization_record.get("currentTrainingUse") != "prohibited"
        or authorization_record.get("schemaVersion") != 1
        or authorization_record.get("ok") is not True
        or authorization_record.get("decision") != "A"
        or authorization_record.get("status") != "confirmed"
        or authorization_record.get("confirmedBy") != "workspace-user"
        or authorization_record.get("sourceRoot") != str(source_root)
        or authorization_record.get("authorizedUses") != authorized_uses
        or authorization_record.get("confirmationNote")
        != user_authorization.get("confirmationNote")
        or authorization_record.get("qualityConstraint")
        != "authorization-does-not-relax-quality-gates"
        or authorization_record.get("roleConstraint")
        != "authorization-does-not-assign-train-validation-or-holdout-role"
        or "independent-release-test"
        not in set(authorization_record.get("authorizedUses") or [])
    ):
        raise ValueError("authorization record differs from current frozen identities")
    authorization_inputs = authorization_record.get("inputs")
    if not isinstance(authorization_inputs, dict):
        raise ValueError("authorization record inputs are missing")
    expected_input_bindings = {
        "userAuthorizationSource": {
            "path": str(user_authorization_path),
            "sha256": sha256_file(user_authorization_path),
        },
        "candidateWeights": {
            "path": str(candidate_weights),
            "sha256": sha256_file(candidate_weights),
        },
        "candidateThresholdReport": threshold_report_input,
        "protectedHardNegativeRegistry": registry_binding,
        "protectedHardNegativeManifests": protected_manifest_bindings,
        "machineAudit": inputs.get("machineAudit"),
    }
    if authorization_inputs != expected_input_bindings:
        raise ValueError("authorization record input bindings differ from freeze manifest")
    if (
        machine_audit.get("schemaVersion") != 1
        or machine_audit.get("ok") is not True
        or machine_audit.get("decision") != "machine_audit_pass_candidate_only"
        or machine_audit.get("role") != "candidate-only"
        or machine_audit.get("trainingUse") != "prohibited"
        or machine_audit.get("sourceRoot") != str(source_root)
        or machine_audit.get("fileCount") != len(current_records)
        or machine_audit.get("decodedCount") != len(current_records)
        or machine_audit.get("decodeFailures") != []
        or machine_audit.get("exactDuplicateGroups") != []
        or machine_audit.get("nearDuplicateThreshold")
        != FORMAL_NEAR_DUPLICATE_DISTANCE
        or machine_audit.get("nearDuplicatePairs") != []
        or machine_audit.get("protectedHardNegativeRegistry") != registry_binding
        or machine_audit.get("protectedHardNegativeManifests")
        != protected_manifest_bindings
        or machine_audit.get("protectedHardNegativeRecordsSha256")
        != canonical_sha256(protected_records)
        or machine_audit.get("protectedHardNegativeCrossCheck")
        != protected_cross_check
    ):
        raise ValueError("machine audit outer contract differs from frozen evidence")
    expected_registry_identity = {
        "protectedRegistryBindingSha256": canonical_sha256(registry_binding),
        "protectedManifestBindingsSha256": canonical_sha256(
            protected_manifest_bindings
        ),
        "protectedRecordsSha256": canonical_sha256(protected_records),
        "protectedCrossCheckSha256": canonical_sha256(protected_cross_check),
    }
    if any(
        batch_identity.get(key) != value
        for key, value in expected_registry_identity.items()
    ):
        raise ValueError("protected hard-negative batch identity drift")
    if manifest.get("protectedHardNegativeCrossCheck") != protected_cross_check:
        raise ValueError("freeze protected hard-negative cross-check drift")
    return {
        "ok": True,
        "decision": manifest["decision"],
        "freezeManifest": str(manifest_path),
        "freezeManifestSha256": sha256_file(manifest_path),
        "sourceRoot": str(source_root),
        "imageCount": len(current_records),
        "batchIdentitySha256": batch_identity_sha256,
        "candidateWeights": str(candidate_weights),
        "candidateWeightsSha256": sha256_file(candidate_weights),
        "candidateThresholdReport": str(threshold_report),
        "candidateThresholdReportSha256": sha256_file(threshold_report),
        "candidateScoreThreshold": threshold_verification["scoreThreshold"],
        "machineAudit": str(machine_audit_path),
        "authorizationRecord": str(authorization_record_path),
        "protectedHardNegativeRegistry": registry_binding,
        "protectedHardNegativeManifests": protected_manifest_bindings,
        "protectedHardNegativeRecordsSha256": canonical_sha256(protected_records),
        "protectedHardNegativeCrossCheck": protected_cross_check,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Atomically freeze a pre-authorized independent hard-negative "
            "batch before candidate-model inference."
        )
    )
    parser.add_argument("--verify-freeze")
    parser.add_argument("--source-root")
    parser.add_argument("--user-authorization")
    parser.add_argument("--candidate-weights")
    parser.add_argument("--candidate-threshold-report")
    parser.add_argument("--protected-hard-negative-registry")
    parser.add_argument("--batch-date")
    parser.add_argument("--sequence-start", type=int)
    parser.add_argument("--sequence-end", type=int)
    args = parser.parse_args()

    if args.verify_freeze:
        creation_values = (
            args.source_root,
            args.user_authorization,
            args.candidate_weights,
            args.candidate_threshold_report,
            args.protected_hard_negative_registry,
            args.batch_date,
            args.sequence_start,
            args.sequence_end,
        )
        if any(value is not None for value in creation_values):
            raise ValueError("--verify-freeze cannot be combined with creation inputs")
        print(
            json.dumps(
                verify_freeze_manifest(Path(args.verify_freeze)),
                ensure_ascii=False,
            )
        )
        return
    if not all(
        value is not None
        for value in (
            args.source_root,
            args.user_authorization,
            args.candidate_weights,
            args.candidate_threshold_report,
            args.protected_hard_negative_registry,
            args.batch_date,
            args.sequence_start,
            args.sequence_end,
        )
    ):
        parser.error(
            "--source-root, --user-authorization, --candidate-weights, "
            "--candidate-threshold-report, --protected-hard-negative-registry, "
            "--batch-date, --sequence-start and --sequence-end are required"
        )

    source_root_raw = Path(str(args.source_root))
    if is_link_or_reparse_point(source_root_raw):
        raise ValueError(
            "source root cannot be a symbolic link, junction, or reparse point"
        )
    source_root = source_root_raw.resolve()
    if not source_root.is_dir():
        raise FileNotFoundError(f"source root does not exist: {source_root}")
    batch_date = str(args.batch_date)
    if not DATE_PATTERN.fullmatch(batch_date):
        raise ValueError("--batch-date must contain exactly eight digits")
    try:
        datetime.strptime(batch_date, "%Y%m%d")
    except ValueError as error:
        raise ValueError("--batch-date is not a valid calendar date") from error
    sequence_start = int(args.sequence_start)
    sequence_end = int(args.sequence_end)
    if not 0 <= sequence_start <= sequence_end <= 999:
        raise ValueError("sequence range must be ascending and stay within 000..999")

    user_authorization_path = Path(args.user_authorization).resolve()
    candidate_weights = Path(args.candidate_weights).resolve()
    candidate_threshold_report = Path(args.candidate_threshold_report).resolve()
    if not user_authorization_path.is_file():
        raise FileNotFoundError(
            f"user authorization source is missing: {user_authorization_path}"
        )
    if not candidate_weights.is_file():
        raise FileNotFoundError(f"candidate weights are missing: {candidate_weights}")
    if not candidate_threshold_report.is_file():
        raise FileNotFoundError(
            f"candidate threshold report is missing: {candidate_threshold_report}"
        )
    threshold_verification = verify_threshold_report(
        candidate_threshold_report,
        candidate_weights,
    )
    training_recorder = load_training_authorization_recorder()
    (
        registry_binding,
        protected_manifest_bindings,
        protected_records,
    ) = training_recorder.load_protected_registry(
        str(args.protected_hard_negative_registry)
    )
    user_authorization_sha256 = sha256_file(user_authorization_path)
    user_authorization, authorized_uses = validate_user_authorization(
        user_authorization_path,
        source_root,
    )

    evidence_dir = source_root / EVIDENCE_DIRECTORY_NAME
    if evidence_dir.exists():
        raise ValueError(f"frozen evidence already exists and is immutable: {evidence_dir}")
    stale_staging = list(source_root.glob(f".{EVIDENCE_DIRECTORY_NAME}.staging-*"))
    if stale_staging:
        raise ValueError(f"stale freeze staging directory requires inspection: {stale_staging}")

    records = enumerate_batch(
        source_root,
        batch_date,
        sequence_start,
        sequence_end,
    )
    near_duplicate_pairs = find_near_duplicate_pairs(records)
    if near_duplicate_pairs:
        raise ValueError(
            "perceptual near-duplicate gate failed at fixed "
            f"dHash256 distance {FORMAL_NEAR_DUPLICATE_DISTANCE}: "
            f"pairs={len(near_duplicate_pairs)}"
        )
    protected_cross_check = reject_protected_overlaps(records, protected_records)

    generated_at = datetime.now(timezone.utc).isoformat()
    weights_sha256 = sha256_file(candidate_weights)
    records_sha256 = canonical_sha256(records)
    dimension_histogram = Counter(
        f"{item['width']}x{item['height']}" for item in records
    )
    batch_identity = {
        "batchDate": batch_date,
        "sequenceStart": sequence_start,
        "sequenceEnd": sequence_end,
        "imageCount": len(records),
        "recordsSha256": records_sha256,
        "candidateWeightsSha256": weights_sha256,
        "candidateThresholdReportSha256": threshold_verification["sha256"],
        "candidateScoreThreshold": threshold_verification["scoreThreshold"],
        "protectedRegistryBindingSha256": canonical_sha256(registry_binding),
        "protectedManifestBindingsSha256": canonical_sha256(
            protected_manifest_bindings
        ),
        "protectedRecordsSha256": canonical_sha256(protected_records),
        "protectedCrossCheckSha256": canonical_sha256(protected_cross_check),
    }
    batch_identity_sha256 = canonical_sha256(batch_identity)
    machine_audit = {
        "schemaVersion": 1,
        "generatedAt": generated_at,
        "ok": True,
        "decision": "machine_audit_pass_candidate_only",
        "role": "candidate-only",
        "trainingUse": "prohibited",
        "sourceRoot": str(source_root),
        "batchIdentity": batch_identity,
        "batchIdentitySha256": batch_identity_sha256,
        "fileCount": len(records),
        "decodedCount": len(records),
        "decodeFailures": [],
        "exactDuplicateGroups": [],
        "nearDuplicateThreshold": FORMAL_NEAR_DUPLICATE_DISTANCE,
        "nearDuplicatePairs": [],
        "protectedHardNegativeRegistry": registry_binding,
        "protectedHardNegativeManifests": protected_manifest_bindings,
        "protectedHardNegativeRecordsSha256": canonical_sha256(protected_records),
        "protectedHardNegativeCrossCheck": protected_cross_check,
        "dimensionHistogram": dict(sorted(dimension_histogram.items())),
        "recordsSha256": records_sha256,
        "records": records,
    }

    entries = [
        {
            "fileName": item["fileName"],
            "sourcePath": item["sourcePath"],
            "sha256": item["sha256"],
            "width": item["width"],
            "height": item["height"],
            "authorizedUses": authorized_uses,
            "trainingEligibility": "prohibited-independent-holdout-only",
        }
        for item in records
    ]
    authorization_record = {
        "schemaVersion": 1,
        "generatedAt": generated_at,
        "ok": True,
        "decision": "A",
        "status": "confirmed",
        "confirmedBy": "workspace-user",
        "confirmationNote": user_authorization["confirmationNote"],
        "sourceRoot": str(source_root),
        "sourceRootIdentity": (
            f"ai-hard-negative-post-train-holdout-{batch_date}-"
            f"{sequence_start:03d}-{sequence_end:03d}"
        ),
        "authorizedUses": authorized_uses,
        "qualityConstraint": "authorization-does-not-relax-quality-gates",
        "roleConstraint": (
            "authorization-does-not-assign-train-validation-or-holdout-role"
        ),
        "currentTrainingUse": "prohibited",
        "eligibilityGate": (
            "original-resolution-review-and-source-role-isolation-required"
        ),
        "batchIdentity": batch_identity,
        "batchIdentitySha256": batch_identity_sha256,
        "inputs": {
            "userAuthorizationSource": {
                "path": str(user_authorization_path),
                "sha256": user_authorization_sha256,
            },
            "candidateWeights": {
                "path": str(candidate_weights),
                "sha256": weights_sha256,
            },
            "candidateThresholdReport": {
                "path": str(candidate_threshold_report),
                "sha256": threshold_verification["sha256"],
                "scoreThreshold": threshold_verification["scoreThreshold"],
            },
            "protectedHardNegativeRegistry": registry_binding,
            "protectedHardNegativeManifests": protected_manifest_bindings,
        },
        "summary": {
            "authorizedImages": len(entries),
            "qualityApprovedImages": 0,
            "qualityExcludedImages": 0,
            "pendingOriginalResolutionReviewImages": len(entries),
        },
        "entriesSha256": canonical_sha256(entries),
        "entries": entries,
    }

    staging_dir = source_root / (
        f".{EVIDENCE_DIRECTORY_NAME}.staging-{os.getpid()}-{uuid.uuid4().hex}"
    )
    try:
        staging_dir.mkdir()
        machine_audit_path = staging_dir / "machine-audit-v1.json"
        authorization_record_path = staging_dir / "authorization-record-A-v1.json"
        freeze_manifest_path = staging_dir / "freeze-manifest-v1.json"
        write_json(machine_audit_path, machine_audit)
        authorization_record["inputs"]["machineAudit"] = {
            "pathWithinFreeze": "machine-audit-v1.json",
            "sha256": sha256_file(machine_audit_path),
        }
        write_json(authorization_record_path, authorization_record)
        freeze_manifest = {
            "schemaVersion": 1,
            "generatedAt": generated_at,
            "ok": True,
            "decision": "independent_holdout_frozen_before_authorized_inference",
            "datasetRole": "candidate-only-pending-original-resolution-review",
            "trainingUse": "prohibited",
            "sourceRoot": str(source_root),
            "batchIdentity": batch_identity,
            "batchIdentitySha256": batch_identity_sha256,
            "inputs": {
                "userAuthorizationSource": {
                    "path": str(user_authorization_path),
                    "sha256": user_authorization_sha256,
                },
                "candidateWeights": {
                    "path": str(candidate_weights),
                    "sha256": weights_sha256,
                },
                "candidateThresholdReport": {
                    "path": str(candidate_threshold_report),
                    "sha256": threshold_verification["sha256"],
                    "scoreThreshold": threshold_verification["scoreThreshold"],
                },
                "protectedHardNegativeRegistry": registry_binding,
                "protectedHardNegativeManifests": protected_manifest_bindings,
                "machineAudit": {
                    "pathWithinFreeze": machine_audit_path.name,
                    "sha256": sha256_file(machine_audit_path),
                },
                "authorizationRecord": {
                    "pathWithinFreeze": authorization_record_path.name,
                    "sha256": sha256_file(authorization_record_path),
                },
            },
            "protectedHardNegativeCrossCheck": protected_cross_check,
            "invariants": {
                "fixedEvidenceDirectoryInsideSourceRoot": True,
                "formalMinimumCannotBeLowered": True,
                "explicitContiguousSequenceRange": True,
                "allImagesResolveInsideSourceRoot": True,
                "symbolicLinksRejected": True,
                "exactAndPerceptualDuplicatesRejected": True,
                "nearDuplicateThresholdFixed": FORMAL_NEAR_DUPLICATE_DISTANCE,
                "candidateWeightsBoundBeforeAuthorizedInference": True,
                "candidateThresholdBoundBeforeAuthorizedInference": True,
                "candidateThresholdReportDeeplyReplayed": True,
                "protectedHardNegativeRegistryRequired": True,
                "protectedHardNegativeRegistryDeeplyReplayed": True,
                "protectedExactSourceAndPerceptualOverlapRejected": True,
                "authorizationDoesNotAssignDatasetRole": True,
                "trainingUseBeforeReview": "prohibited",
            },
        }
        write_json(freeze_manifest_path, freeze_manifest)

        # Re-read every mutable external input immediately before the commit
        # point. A concurrent write must leave no visible final freeze.
        if sha256_file(user_authorization_path) != user_authorization_sha256:
            raise ValueError("user authorization changed during freeze creation")
        validate_user_authorization(user_authorization_path, source_root)
        if sha256_file(candidate_weights) != weights_sha256:
            raise ValueError("candidate weights changed during freeze creation")
        threshold_before_commit = verify_threshold_report(
            candidate_threshold_report,
            candidate_weights,
        )
        if threshold_before_commit != threshold_verification:
            raise ValueError("candidate threshold evidence changed during freeze creation")
        (
            registry_before_commit,
            manifests_before_commit,
            protected_before_commit,
        ) = training_recorder.load_protected_registry(
            str(registry_binding["path"])
        )
        if (
            registry_before_commit != registry_binding
            or manifests_before_commit != protected_manifest_bindings
            or protected_before_commit != protected_records
        ):
            raise ValueError(
                "protected hard-negative evidence changed during freeze creation"
            )
        records_before_commit = enumerate_batch(
            source_root,
            batch_date,
            sequence_start,
            sequence_end,
        )
        cross_check_before_commit = reject_protected_overlaps(
            records_before_commit,
            protected_before_commit,
        )
        if (
            records_before_commit != records
            or find_near_duplicate_pairs(records_before_commit)
            or cross_check_before_commit != protected_cross_check
        ):
            raise ValueError("source images changed during freeze creation")

        # The entire evidence directory becomes visible in one same-volume rename.
        staging_dir.rename(evidence_dir)
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise

    final_manifest = evidence_dir / "freeze-manifest-v1.json"
    verified_final = verify_freeze_manifest(final_manifest)
    print(
        json.dumps(
            {
                "ok": True,
                "decision": "independent_holdout_frozen_before_authorized_inference",
                "imageCount": len(records),
                "batchIdentitySha256": batch_identity_sha256,
                "candidateWeightsSha256": weights_sha256,
                "candidateThresholdReportSha256": threshold_verification["sha256"],
                "candidateScoreThreshold": verified_final["candidateScoreThreshold"],
                "protectedHardNegativeRegistrySha256": registry_binding["sha256"],
                "protectedHardNegativeRecordCount": len(protected_records),
                "evidenceDir": str(evidence_dir),
                "freezeManifest": str(final_manifest),
                "freezeManifestSha256": sha256_file(final_manifest),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
