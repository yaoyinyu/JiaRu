#!/usr/bin/env python3
"""Record an exact, authorized training hard-negative batch.

The command consumes a pre-existing authorization JSON document whose
explicit relative-path allow-list is bound by SHA-256. It never scans the
source root to infer authorization. Every selected image must follow one
contiguous ``hard_negative_training_YYYYMMDD_NNN_family_NN`` sequence.

New schema v3 evidence binds the project's standing commercial authorization;
historical schema v1/v2 itemized confirmations remain replayable.

The two outputs remain candidate-only and ``trainingUse=prohibited``. They are
designed for direct consumption by
``build-independent-hard-negative-review-workspace.py``.
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
from typing import Any

from PIL import Image, UnidentifiedImageError


FORMAL_NEAR_DUPLICATE_DISTANCE = 12
FORMAL_MINIMUM_SIDE = 768
IMAGE_FORMAT_BY_SUFFIX = {
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
    ".webp": "WEBP",
}
FILE_PATTERN = re.compile(
    r"^hard_negative_training_(?P<date>\d{8})_(?P<sequence>\d{3})_"
    r"(?P<family>[a-z0-9_]+)_(?P<variant>\d{2})\.(?P<suffix>png|jpe?g|webp)$",
    re.IGNORECASE,
)
DATE_PATTERN = re.compile(r"^\d{8}$")
SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
REQUIRED_AUTHORIZED_USES = {
    "commercial-model-training",
    "long-term-regression",
}
PROHIBITED_AUTHORIZED_USE = "independent-release-test"
EXACT_AUTHORIZED_USES = [
    "commercial-model-training",
    "long-term-regression",
    "model-diagnostic-evaluation",
    "data-quality-review",
]
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


def load_user_authorization_module() -> Any:
    module_path = Path(__file__).with_name(
        "build-training-hard-negative-user-authorization.py"
    )
    spec = importlib.util.spec_from_file_location(
        "jiaru_training_hard_negative_user_authorization_verifier",
        module_path,
    )
    if spec is None or spec.loader is None:
        raise ValueError("cannot load training user-authorization verifier")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


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


def reject_linked_ancestors(path: Path, label: str) -> None:
    current = path
    while True:
        if is_link_or_reparse_point(current):
            raise ValueError(
                f"{label} cannot traverse a symbolic link, junction, or reparse point: "
                f"{current}"
            )
        if current.parent == current:
            return
        current = current.parent


def reject_linked_path(path: Path, source_root: Path) -> None:
    current = path
    while True:
        if is_link_or_reparse_point(current):
            raise ValueError(
                "symbolic link, junction, or reparse-point entry is prohibited: "
                f"{current}"
            )
        if current == source_root:
            return
        if current.parent == current or not is_relative_to(current, source_root):
            raise ValueError(f"authorized path escapes source root: {path}")
        current = current.parent


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


def decode_image(
    path: Path,
    *,
    minimum_side: int = FORMAL_MINIMUM_SIDE,
    require_suffix_contract: bool = True,
) -> tuple[int, int, str, str]:
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
    if require_suffix_contract and image_format != expected_format:
        raise ValueError(
            f"image format {image_format!r} differs from suffix contract "
            f"{expected_format!r}: {path}"
        )
    if min(width, height) < minimum_side:
        raise ValueError(
            f"image minimum side is below {minimum_side}px: {path}"
        )
    return width, height, image_format, perceptual_hash


def validate_user_authorization(
    path: Path,
    source_root: Path,
) -> tuple[dict[str, Any], list[str], list[str]]:
    authorization = read_json(path, "user authorization source")
    schema_version = authorization.get("schemaVersion")
    if (
        schema_version not in {1, 2, 3}
        or authorization.get("ok") is not True
        or authorization.get("decision")
        != "authorized_for_training_hard_negative_review"
        or authorization.get("qualityConstraint")
        != "authorization-does-not-relax-quality-gates"
        or authorization.get("roleConstraint")
        != "authorization-does-not-assign-train-validation-or-holdout-role"
    ):
        raise ValueError(
            "user authorization source does not satisfy the training hard-negative contract"
        )
    confirmation_note = str(authorization.get("confirmationNote") or "").strip()
    if not confirmation_note:
        raise ValueError("user authorization source confirmationNote is missing")
    evidence = authorization.get("authorizationEvidence")
    if not isinstance(evidence, dict):
        raise ValueError("user authorization source authorizationEvidence is missing")
    if schema_version in {1, 2}:
        evidence_text = str(evidence.get("userMessageText") or "").strip()
        evidence_thread_id = str(evidence.get("threadId") or "").strip()
        evidence_decision_id = str(evidence.get("decisionId") or "").strip()
        if (
            authorization.get("confirmedBy") != "workspace-user"
            or evidence.get("kind")
            != (
                "operator-attested-codex-user-message"
                if schema_version == 2
                else "codex-user-message"
            )
            or evidence_text != confirmation_note
            or evidence.get("userMessageSha256")
            != hashlib.sha256(evidence_text.encode("utf-8")).hexdigest()
            or not UUID_PATTERN.fullmatch(evidence_thread_id)
            or not evidence_decision_id
            or evidence_thread_id not in evidence_decision_id
        ):
            raise ValueError(
                "user authorization source does not bind a traceable user-message decision"
            )
    elif (
        authorization.get("confirmedBy") != "standing-project-authorization"
        or evidence.get("kind")
        != "standing-project-commercial-resource-authorization"
        or evidence.get("decision")
        != "standing_project_commercial_resource_authorization_granted"
        or not SHA256_PATTERN.fullmatch(str(evidence.get("sha256") or ""))
        or not SHA256_PATTERN.fullmatch(
            str(evidence.get("requestedItemsSha256") or "")
        )
    ):
        raise ValueError(
            "authorization source does not bind the standing project authorization"
        )
    if schema_version in {2, 3}:
        verification = load_user_authorization_module().verify_authorization(path)
        if (
            verification.get("ok") is not True
            or verification.get("currentTrainingUse") != "prohibited"
        ):
            raise ValueError("user authorization source v2 deep replay failed")

    try:
        authorized_root = Path(str(authorization.get("sourceRoot") or "")).resolve(
            strict=True
        )
    except OSError as error:
        raise ValueError("authorized sourceRoot is missing") from error
    if authorized_root != source_root:
        raise ValueError(
            "user authorization sourceRoot must exactly match the selected source root"
        )
    if authorization.get("scopeIncludesDescendants") is not False:
        raise ValueError(
            "user authorization must use an explicit file set, not descendant-wide scope"
        )

    authorized_uses = sorted(
        {
            str(value).strip()
            for value in list(authorization.get("authorizedUses") or [])
            if str(value).strip()
        }
    )
    if schema_version in {2, 3} and authorized_uses != sorted(EXACT_AUTHORIZED_USES):
        raise ValueError("authorizedUses must exactly match the confirmed uses")
    if schema_version == 1 and not REQUIRED_AUTHORIZED_USES.issubset(authorized_uses):
        raise ValueError(
            "authorizedUses must include commercial-model-training and long-term-regression"
        )
    if PROHIBITED_AUTHORIZED_USE in authorized_uses:
        raise ValueError(
            "authorizedUses must exclude independent-release-test for training batches"
        )
    if schema_version in {2, 3} and (
        authorization.get("excludedUses") != [PROHIBITED_AUTHORIZED_USE]
        or authorization.get("currentTrainingUse") != "prohibited"
    ):
        raise ValueError("authorization use exclusions or training state drift")

    raw_paths = authorization.get("authorizedRelativePaths")
    if not isinstance(raw_paths, list) or not raw_paths:
        raise ValueError("authorizedRelativePaths must contain an explicit non-empty file set")
    relative_paths: list[str] = []
    seen: set[str] = set()
    for number, value in enumerate(raw_paths, start=1):
        relative = str(value or "").strip().replace("\\", "/")
        candidate = Path(relative)
        if (
            not relative
            or candidate.is_absolute()
            or any(part in {"", ".", ".."} for part in candidate.parts)
        ):
            raise ValueError(
                f"authorizedRelativePaths entry {number} is not a safe relative path"
            )
        key = relative.casefold()
        if key in seen:
            raise ValueError(f"duplicate authorized relative path: {relative}")
        seen.add(key)
        relative_paths.append(relative)
    if relative_paths != sorted(relative_paths, key=str.casefold):
        raise ValueError("authorizedRelativePaths must be case-insensitively sorted")
    if authorization.get("authorizedRelativePathsSha256") != canonical_sha256(
        relative_paths
    ):
        raise ValueError("authorizedRelativePaths SHA-256 drift")
    return authorization, authorized_uses, relative_paths


def audit_explicit_batch(
    source_root: Path,
    relative_paths: list[str],
    batch_date: str,
    sequence_start: int,
    sequence_end: int,
) -> list[dict[str, Any]]:
    if sequence_end < sequence_start:
        raise ValueError("--sequence-end must be greater than or equal to --sequence-start")
    expected_sequences = set(range(sequence_start, sequence_end + 1))
    if len(relative_paths) != len(expected_sequences):
        raise ValueError(
            "authorized file count differs from the explicit batch range: "
            f"expected={len(expected_sequences)} actual={len(relative_paths)}"
        )

    records: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    seen_hashes: set[str] = set()
    seen_sequences: set[int] = set()
    for relative in relative_paths:
        unresolved = source_root / Path(relative)
        if not unresolved.is_file():
            raise ValueError(f"authorized image is missing: {unresolved}")
        reject_linked_path(unresolved, source_root)
        resolved = unresolved.resolve(strict=True)
        if not is_relative_to(resolved, source_root):
            raise ValueError(f"authorized path escapes source root: {unresolved}")

        file_name = unresolved.name
        match = FILE_PATTERN.fullmatch(file_name)
        if not match:
            raise ValueError(
                f"file name does not match the training-batch contract: {file_name}"
            )
        if match.group("date") != batch_date:
            raise ValueError(f"file date differs from --batch-date: {file_name}")
        sequence = int(match.group("sequence"))
        if sequence not in expected_sequences:
            raise ValueError(f"file sequence is outside the explicit range: {file_name}")
        if file_name.casefold() in seen_names:
            raise ValueError(f"duplicate file name: {file_name}")
        if sequence in seen_sequences:
            raise ValueError(f"duplicate sequence number: {sequence:03d}")

        image_hash = sha256_file(resolved)
        if image_hash in seen_hashes:
            raise ValueError(f"duplicate image SHA-256: {file_name}")
        width, height, image_format, perceptual_hash = decode_image(resolved)
        seen_names.add(file_name.casefold())
        seen_hashes.add(image_hash)
        seen_sequences.add(sequence)
        records.append(
            {
                "fileName": file_name,
                "relativePath": Path(relative).as_posix(),
                "sourcePath": str(resolved),
                "sha256": image_hash,
                "width": width,
                "height": height,
                "format": image_format,
                "bytes": resolved.stat().st_size,
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


def normalize_protected_source_group(source_group: str) -> str:
    value = source_group.strip().casefold().replace("\\", "/")
    if not value:
        raise ValueError("protected sourceGroup is missing")
    head, separator, tail = value.partition(":")
    parts = re.split(r"([-_/]+)", head)
    normalized_head = "".join(
        part
        for part in parts
        if part.casefold() not in {"training", "independent"}
    )
    normalized_head = re.sub(r"[-_/]{2,}", "-", normalized_head).strip("-_/ ")
    normalized_head = re.sub(
        r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)",
        lambda match: "".join(match.groups()),
        normalized_head,
    )
    if not normalized_head:
        raise ValueError(f"protected sourceGroup cannot be normalized: {source_group}")
    return f"{normalized_head}:{tail}" if separator else normalized_head


def load_protected_manifests(
    registry_entries: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    bindings: list[dict[str, Any]] = []
    protected_records: list[dict[str, Any]] = []
    seen_manifest_paths: set[str] = set()
    global_records: list[dict[str, Any]] = []
    records_by_file_name: dict[str, dict[str, Any]] = {}
    records_by_image_path: dict[str, dict[str, Any]] = {}
    records_by_image_hash: dict[str, dict[str, Any]] = {}
    seen_contract_roles: set[str] = set()
    for registry_entry in registry_entries:
        path_value = str(registry_entry.get("path") or "")
        registry_sha256 = str(registry_entry.get("sha256") or "")
        registry_role = str(registry_entry.get("role") or "")
        if registry_role not in {"training", "holdout"}:
            raise ValueError(f"protected registry role is invalid: {registry_role}")
        if not SHA256_PATTERN.fullmatch(registry_sha256):
            raise ValueError("protected registry manifest SHA-256 is invalid")
        manifest_input = Path(path_value).absolute()
        if not manifest_input.is_file():
            raise ValueError(
                f"protected hard-negative manifest is missing: {manifest_input}"
            )
        reject_linked_ancestors(
            manifest_input,
            "protected hard-negative manifest",
        )
        manifest_path = manifest_input.resolve(strict=True)
        if sha256_file(manifest_path) != registry_sha256:
            raise ValueError(
                f"protected registry manifest SHA-256 drift: {manifest_path}"
            )
        path_key = str(manifest_path).casefold()
        if path_key in seen_manifest_paths:
            raise ValueError(
                f"duplicate protected hard-negative manifest: {manifest_path}"
            )
        seen_manifest_paths.add(path_key)
        manifest = read_json(manifest_path, "protected hard-negative manifest")
        decision = str(manifest.get("decision") or "")
        training_use = str(manifest.get("trainingUse") or "")
        valid_contract = (
            manifest.get("schemaVersion") == 2
            and manifest.get("ok") is True
            and manifest.get("status") == "PASS"
            and (
                (
                    decision == "approved_hard_negative_manifest"
                    and training_use == "permitted"
                )
                or (
                    decision == "approved_independent_hard_negative_holdout"
                    and training_use == "prohibited"
                )
            )
        )
        if not valid_contract:
            raise ValueError(
                f"protected hard-negative manifest contract is invalid: {manifest_path}"
            )
        expected_batch_role = (
            "training"
            if decision == "approved_hard_negative_manifest"
            else "independent"
        )
        expected_registry_role = (
            "training" if expected_batch_role == "training" else "holdout"
        )
        if registry_role != expected_registry_role:
            raise ValueError(
                "protected registry role differs from manifest decision: "
                f"registry={registry_role}, decision={decision}"
            )
        seen_contract_roles.add(expected_batch_role)
        items = manifest.get("items")
        if not isinstance(items, list) or not items:
            raise ValueError(
                f"protected hard-negative manifest items are missing: {manifest_path}"
            )
        if manifest.get("itemsSha256") != canonical_sha256(items):
            raise ValueError(
                f"protected hard-negative manifest items SHA-256 drift: {manifest_path}"
            )
        manifest_records: list[dict[str, Any]] = []
        for number, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                raise ValueError(
                    f"protected manifest item {number} must be an object: {manifest_path}"
                )
            file_name = str(item.get("fileName") or "")
            source_group = str(item.get("sourceGroup") or "")
            source_identity = normalize_protected_source_group(source_group)
            image_input = Path(str(item.get("imagePath") or "")).absolute()
            if not image_input.is_file():
                raise ValueError(f"protected image is missing: {image_input}")
            reject_linked_ancestors(image_input, "protected image")
            image_path = image_input.resolve(strict=True)
            image_hash = sha256_file(image_path)
            if image_hash != str(item.get("imageSha256") or ""):
                raise ValueError(f"protected image SHA-256 drift: {file_name}")
            width, height, image_format, perceptual_hash = decode_image(
                image_path,
                minimum_side=320,
                require_suffix_contract=False,
            )
            if (
                width != int(item.get("width", -1))
                or height != int(item.get("height", -1))
                or image_format != str(item.get("imageFormat") or "").upper()
            ):
                raise ValueError(
                    f"protected image dimensions or format drift: {file_name}"
                )
            record_identity = {
                "fileName": file_name,
                "imagePath": str(image_path),
                "imageSha256": image_hash,
                "width": width,
                "height": height,
                "imageFormat": image_format,
                "sourceGroup": source_group,
                "sourceIdentity": source_identity,
                "dhash256": perceptual_hash,
            }
            manifest_record = {
                "manifestPath": str(manifest_path),
                **record_identity,
            }
            manifest_records.append(manifest_record)
            collision_records = {
                id(existing): existing
                for existing in (
                    records_by_file_name.get(file_name.casefold()),
                    records_by_image_path.get(str(image_path).casefold()),
                    records_by_image_hash.get(image_hash),
                )
                if existing is not None
            }
            if collision_records:
                if len(collision_records) != 1:
                    raise ValueError(
                        f"conflicting protected hard-negative identities: {file_name}"
                    )
                existing = next(iter(collision_records.values()))
                existing_identity = {
                    key: value
                    for key, value in existing.items()
                    if key != "manifestPaths"
                }
                if existing_identity != record_identity:
                    raise ValueError(
                        "protected hard-negative duplicate evidence conflicts on "
                        f"path/file/hash/sourceGroup: {file_name}"
                    )
                existing["manifestPaths"].append(str(manifest_path))
                existing["manifestPaths"].sort(key=str.casefold)
            else:
                protected_record = {
                    **record_identity,
                    "manifestPaths": [str(manifest_path)],
                }
                global_records.append(protected_record)
                records_by_file_name[file_name.casefold()] = protected_record
                records_by_image_path[str(image_path).casefold()] = protected_record
                records_by_image_hash[image_hash] = protected_record
        bindings.append(
            {
                "path": str(manifest_path),
                "sha256": registry_sha256,
                "registryRole": registry_role,
                "decision": decision,
                "trainingUse": training_use,
                "itemCount": len(items),
                "itemsSha256": manifest["itemsSha256"],
                "protectedRecordsSha256": canonical_sha256(manifest_records),
            }
        )
    missing_contract_roles = {"training", "independent"} - seen_contract_roles
    if missing_contract_roles:
        raise ValueError(
            "protected hard-negative manifests must include at least one approved "
            "training manifest and one approved independent holdout manifest; "
            f"missing={sorted(missing_contract_roles)}"
        )
    bindings.sort(key=lambda item: str(item["path"]).casefold())
    protected_records = sorted(
        global_records,
        key=lambda item: (
            str(item["fileName"]).casefold(),
            str(item["imagePath"]).casefold(),
        )
    )
    return bindings, protected_records


def load_protected_registry(
    path_value: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    registry_input = Path(path_value).absolute()
    if not registry_input.is_file():
        raise ValueError(f"protected hard-negative registry is missing: {registry_input}")
    reject_linked_ancestors(registry_input, "protected hard-negative registry")
    registry_path = registry_input.resolve(strict=True)
    registry = read_json(registry_path, "protected hard-negative registry")
    entries = registry.get("entries")
    if (
        registry.get("schemaVersion") != 1
        or registry.get("ok") is not True
        or registry.get("decision") != "protected_hard_negative_registry"
        or not isinstance(entries, list)
        or not entries
        or registry.get("entriesSha256") != canonical_sha256(entries)
    ):
        raise ValueError("protected hard-negative registry contract is invalid")
    normalized_entries: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for number, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256", "role"}:
            raise ValueError(f"protected registry entry {number} is invalid")
        manifest_path = Path(str(entry.get("path") or "")).absolute()
        path_key = str(manifest_path).casefold()
        if path_key in seen_paths:
            raise ValueError(f"duplicate protected registry manifest path: {manifest_path}")
        seen_paths.add(path_key)
        normalized_entries.append(
            {
                "path": str(manifest_path),
                "sha256": str(entry.get("sha256") or ""),
                "role": str(entry.get("role") or ""),
            }
        )
    if entries != normalized_entries:
        raise ValueError("protected hard-negative registry entries are not canonical")
    role_counts = Counter(str(item["role"]) for item in entries)
    summary = registry.get("summary")
    if summary != {
        "manifestCount": len(entries),
        "trainingManifestCount": role_counts["training"],
        "holdoutManifestCount": role_counts["holdout"],
    }:
        raise ValueError("protected hard-negative registry summary drift")
    bindings, records = load_protected_manifests(entries)
    registry_binding = {
        "path": str(registry_path),
        "sha256": sha256_file(registry_path),
        "decision": registry["decision"],
        "entriesSha256": registry["entriesSha256"],
        "manifestCount": len(entries),
        "trainingManifestCount": role_counts["training"],
        "holdoutManifestCount": role_counts["holdout"],
    }
    return registry_binding, bindings, records


def reject_protected_overlaps(
    records: list[dict[str, Any]],
    protected_records: list[dict[str, Any]],
) -> None:
    protected_hashes = {
        str(item["imageSha256"]): str(item["fileName"])
        for item in protected_records
    }
    protected_source_identities = {
        str(item["sourceIdentity"]): str(item["fileName"])
        for item in protected_records
    }
    for record in records:
        image_hash = str(record["sha256"])
        if image_hash in protected_hashes:
            raise ValueError(
                "new batch exactly duplicates a protected hard negative: "
                f"{record['fileName']} == {protected_hashes[image_hash]}"
            )
        source_identity = (
            f"ai-hard-negative-{record['batchDate']}:{record['promptFamily']}"
        )
        record["sourceGroup"] = (
            f"ai-hard-negative-training-{record['batchDate']}:"
            f"{record['promptFamily']}"
        )
        record["sourceIdentity"] = source_identity
        if source_identity in protected_source_identities:
            raise ValueError(
                "new batch sourceGroup overlaps a protected hard negative source: "
                f"{record['fileName']} ~= {protected_source_identities[source_identity]}"
            )
        for protected in protected_records:
            distance = hamming_distance(
                str(record["dhash256"]),
                str(protected["dhash256"]),
            )
            if distance <= FORMAL_NEAR_DUPLICATE_DISTANCE:
                raise ValueError(
                    "new batch perceptually duplicates a protected hard negative at "
                    f"dHash256 distance {distance}: {record['fileName']} ~= "
                    f"{protected['fileName']}"
                )


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


def require_bound_file(path_value: Any, hash_value: Any, label: str) -> Path:
    input_path = Path(str(path_value or "")).absolute()
    expected_hash = str(hash_value or "")
    if not input_path.is_file() or not SHA256_PATTERN.fullmatch(expected_hash):
        raise ValueError(f"{label} binding is invalid")
    reject_linked_ancestors(input_path, label)
    path = input_path.resolve(strict=True)
    if sha256_file(path) != expected_hash:
        raise ValueError(f"{label} SHA-256 drift")
    return path


def verify_authorization_record(path: Path) -> dict[str, Any]:
    authorization = read_json(path, "training authorization record")
    if (
        authorization.get("schemaVersion") != 1
        or authorization.get("ok") is not True
        or authorization.get("decision") != "A"
        or authorization.get("status") != "confirmed"
        or authorization.get("currentTrainingUse") != "prohibited"
        or authorization.get("qualityConstraint")
        != "authorization-does-not-relax-quality-gates"
        or authorization.get("roleConstraint")
        != "authorization-does-not-assign-train-validation-or-holdout-role"
    ):
        raise ValueError("training authorization record contract is invalid")
    uses = sorted(set(authorization.get("authorizedUses") or []))
    if (
        not REQUIRED_AUTHORIZED_USES.issubset(uses)
        or PROHIBITED_AUTHORIZED_USE in uses
    ):
        raise ValueError("training authorization record uses are invalid")
    inputs = authorization.get("inputs")
    if not isinstance(inputs, dict):
        raise ValueError("training authorization record inputs are missing")
    machine_input = inputs.get("machineAudit")
    user_input = inputs.get("userAuthorizationSource")
    registry_input = inputs.get("protectedHardNegativeRegistry")
    protected_inputs = inputs.get("protectedHardNegativeManifests")
    if (
        not isinstance(machine_input, dict)
        or not isinstance(user_input, dict)
        or not isinstance(registry_input, dict)
        or not isinstance(protected_inputs, list)
        or not protected_inputs
    ):
        raise ValueError("training authorization record input bindings are missing")
    machine_path = require_bound_file(
        machine_input.get("path"),
        machine_input.get("sha256"),
        "machine audit",
    )
    user_path = require_bound_file(
        user_input.get("path"),
        user_input.get("sha256"),
        "user authorization source",
    )
    registry_path = require_bound_file(
        registry_input.get("path"),
        registry_input.get("sha256"),
        "protected hard-negative registry",
    )
    machine = read_json(machine_path, "machine audit")
    registry_binding, protected_bindings, protected_records = load_protected_registry(
        str(registry_path)
    )
    if registry_binding != registry_input:
        raise ValueError("protected hard-negative registry binding drift")
    if protected_bindings != protected_inputs:
        raise ValueError("protected hard-negative manifest binding drift")
    records = machine.get("records")
    entries = authorization.get("entries")
    if (
        machine.get("ok") is not True
        or machine.get("trainingUse") != "prohibited"
        or machine.get("decodeFailures") != []
        or machine.get("exactDuplicateGroups") != []
        or machine.get("nearDuplicatePairs") != []
        or not isinstance(records, list)
        or not isinstance(entries, list)
        or machine.get("decodedCount") != len(records)
        or len(entries) != len(records)
        or machine.get("recordsSha256") != canonical_sha256(records)
        or authorization.get("entriesSha256") != canonical_sha256(entries)
        or machine.get("protectedHardNegativeManifests") != protected_bindings
        or machine.get("protectedHardNegativeRegistry") != registry_binding
        or machine.get("protectedHardNegativeRecordsSha256")
        != canonical_sha256(protected_records)
        or machine.get("protectedHardNegativeRecords") != protected_records
        or machine.get("minimumSide") != FORMAL_MINIMUM_SIDE
    ):
        raise ValueError("training authorization aggregate evidence drift")
    source_root = Path(str(authorization.get("sourceRoot") or "")).resolve(strict=True)
    _, authorized_uses, relative_paths = validate_user_authorization(
        user_path,
        source_root,
    )
    identity = authorization.get("batchIdentity")
    if not isinstance(identity, dict):
        raise ValueError("training authorization batchIdentity is missing")
    if authorization.get("batchIdentitySha256") != canonical_sha256(identity):
        raise ValueError("training authorization batchIdentity SHA-256 drift")
    if (
        identity.get("protectedManifestBindingsSha256")
        != canonical_sha256(protected_bindings)
        or identity.get("protectedRegistryBindingSha256")
        != canonical_sha256(registry_binding)
        or identity.get("protectedRecordsSha256")
        != canonical_sha256(protected_records)
        or machine.get("batchIdentity") != identity
        or machine.get("batchIdentitySha256")
        != authorization.get("batchIdentitySha256")
        or identity.get("minimumSide") != FORMAL_MINIMUM_SIDE
    ):
        raise ValueError("protected hard-negative batch identity drift")
    current_records = audit_explicit_batch(
        source_root,
        relative_paths,
        str(identity.get("batchDate") or ""),
        int(identity.get("sequenceStart", -1)),
        int(identity.get("sequenceEnd", -1)),
    )
    reject_protected_overlaps(current_records, protected_records)
    if current_records != records:
        raise ValueError("authorized image bytes or metadata drift")
    if find_near_duplicate_pairs(current_records):
        raise ValueError("authorized batch now fails the perceptual duplicate gate")
    expected_entries = [
        {
            "fileName": item["fileName"],
            "relativePath": item["relativePath"],
            "sourcePath": item["sourcePath"],
            "sha256": item["sha256"],
            "width": item["width"],
            "height": item["height"],
            "authorizedUses": authorized_uses,
            "trainingEligibility": (
                "permitted-only-after-original-resolution-review-and-source-role-isolation"
            ),
        }
        for item in current_records
    ]
    if entries != expected_entries:
        raise ValueError("training authorization entries drift")
    return {
        "ok": True,
        "authorizationRecord": str(path),
        "authorizationRecordSha256": sha256_file(path),
        "machineAudit": str(machine_path),
        "machineAuditSha256": sha256_file(machine_path),
        "imageCount": len(records),
        "batchIdentitySha256": authorization["batchIdentitySha256"],
    }


def create_evidence(args: argparse.Namespace) -> dict[str, Any]:
    if not DATE_PATTERN.fullmatch(args.batch_date):
        raise ValueError("--batch-date must be YYYYMMDD")
    source_root_input = Path(args.source_root).absolute()
    if not source_root_input.is_dir():
        raise ValueError("source root must be an existing directory")
    reject_linked_ancestors(source_root_input, "source root")
    try:
        source_root = source_root_input.resolve(strict=True)
    except OSError as error:
        raise ValueError("source root is missing") from error

    user_input = Path(args.authorization_source).absolute()
    if not user_input.is_file():
        raise ValueError("user authorization source is missing")
    reject_linked_ancestors(user_input, "user authorization source")
    user_path = user_input.resolve(strict=True)
    user_hash = sha256_file(user_path)
    user_authorization, authorized_uses, relative_paths = validate_user_authorization(
        user_path,
        source_root,
    )
    registry_binding, protected_bindings, protected_records = load_protected_registry(
        str(args.protected_hard_negative_registry)
    )
    records = audit_explicit_batch(
        source_root,
        relative_paths,
        args.batch_date,
        args.sequence_start,
        args.sequence_end,
    )
    near_duplicate_pairs = find_near_duplicate_pairs(records)
    if near_duplicate_pairs:
        raise ValueError(
            "perceptual near-duplicate gate failed at fixed "
            f"dHash256 distance {FORMAL_NEAR_DUPLICATE_DISTANCE}: "
            f"pairs={len(near_duplicate_pairs)}"
        )
    reject_protected_overlaps(records, protected_records)

    output_dir = Path(args.output_dir).resolve()
    if output_dir.exists():
        raise ValueError(f"refusing to overwrite existing evidence directory: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    reject_linked_ancestors(output_dir.parent, "output parent")

    generated_at = datetime.now(timezone.utc).isoformat()
    records_sha256 = canonical_sha256(records)
    batch_identity = {
        "batchRole": "training-hard-negative-candidate",
        "batchDate": args.batch_date,
        "sequenceStart": args.sequence_start,
        "sequenceEnd": args.sequence_end,
        "imageCount": len(records),
        "minimumSide": FORMAL_MINIMUM_SIDE,
        "authorizedRelativePathsSha256": canonical_sha256(relative_paths),
        "recordsSha256": records_sha256,
        "protectedManifestBindingsSha256": canonical_sha256(protected_bindings),
        "protectedRegistryBindingSha256": canonical_sha256(registry_binding),
        "protectedRecordsSha256": canonical_sha256(protected_records),
    }
    batch_identity_sha256 = canonical_sha256(batch_identity)
    dimension_histogram = Counter(
        f"{item['width']}x{item['height']}" for item in records
    )
    machine_audit = {
        "schemaVersion": 1,
        "generatedAt": generated_at,
        "ok": True,
        "decision": "machine_audit_pass_training_candidate_only",
        "role": "training-hard-negative-candidate",
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
        "minimumSide": FORMAL_MINIMUM_SIDE,
        "protectedHardNegativeRegistry": registry_binding,
        "protectedHardNegativeManifests": protected_bindings,
        "protectedHardNegativeRecordsSha256": canonical_sha256(protected_records),
        "protectedHardNegativeRecords": protected_records,
        "dimensionHistogram": dict(sorted(dimension_histogram.items())),
        "recordsSha256": records_sha256,
        "records": records,
    }
    entries = [
        {
            "fileName": item["fileName"],
            "relativePath": item["relativePath"],
            "sourcePath": item["sourcePath"],
            "sha256": item["sha256"],
            "width": item["width"],
            "height": item["height"],
            "authorizedUses": authorized_uses,
            "trainingEligibility": (
                "permitted-only-after-original-resolution-review-and-source-role-isolation"
            ),
        }
        for item in records
    ]
    staging_dir = output_dir.parent / (
        f".{output_dir.name}.staging-{os.getpid()}-{uuid.uuid4().hex}"
    )
    try:
        staging_dir.mkdir()
        machine_path = staging_dir / "machine-audit-v1.json"
        write_json(machine_path, machine_audit)
        final_machine_path = output_dir / machine_path.name
        authorization_record = {
            "schemaVersion": 1,
            "generatedAt": generated_at,
            "ok": True,
            "decision": "A",
            "status": "confirmed",
            "confirmedBy": user_authorization["confirmedBy"],
            "confirmationNote": user_authorization["confirmationNote"],
            "sourceRoot": str(source_root),
            "sourceRootIdentity": (
                f"ai-hard-negative-training-{args.batch_date}-"
                f"{args.sequence_start:03d}-{args.sequence_end:03d}"
            ),
            "scopeIncludesDescendants": False,
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
                    "path": str(user_path),
                    "sha256": user_hash,
                },
                "machineAudit": {
                    "path": str(final_machine_path),
                    "sha256": sha256_file(machine_path),
                },
                "protectedHardNegativeRegistry": registry_binding,
                "protectedHardNegativeManifests": protected_bindings,
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
        authorization_path = staging_dir / "authorization-record-A-v1.json"
        write_json(authorization_path, authorization_record)

        if sha256_file(user_path) != user_hash:
            raise ValueError("user authorization changed during evidence creation")
        validate_user_authorization(user_path, source_root)
        current_records = audit_explicit_batch(
            source_root,
            relative_paths,
            args.batch_date,
            args.sequence_start,
            args.sequence_end,
        )
        # sourceGroup/sourceIdentity are derived after image decoding.
        reject_protected_overlaps(current_records, protected_records)
        if current_records != records:
            raise ValueError("authorized image bytes changed during evidence creation")
        (
            current_registry_binding,
            current_bindings,
            current_protected_records,
        ) = load_protected_registry(
            str(registry_binding["path"])
        )
        if (
            current_registry_binding != registry_binding
            or current_bindings != protected_bindings
            or current_protected_records != protected_records
        ):
            raise ValueError(
                "protected hard-negative evidence changed during evidence creation"
            )
        if output_dir.exists():
            raise ValueError(
                f"refusing to overwrite existing evidence directory: {output_dir}"
            )
        os.replace(staging_dir, output_dir)
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise

    final_authorization_path = output_dir / "authorization-record-A-v1.json"
    verification = verify_authorization_record(final_authorization_path)
    return {
        **verification,
        "decision": "training_hard_negative_batch_authorized_pending_review",
        "trainingUse": "prohibited",
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Record an exact authorized training hard-negative batch and "
            "machine audit."
        )
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--source-root")
    mode.add_argument("--verify-authorization")
    mode.add_argument("--verify-protected-registry")
    parser.add_argument(
        "--authorization-source",
        "--user-authorization",
        dest="authorization_source",
        help=(
            "Hash-bound standing-authorization source; the historical "
            "--user-authorization name remains accepted."
        ),
    )
    parser.add_argument("--output-dir")
    parser.add_argument("--protected-hard-negative-registry")
    parser.add_argument("--batch-date")
    parser.add_argument("--sequence-start", type=int)
    parser.add_argument("--sequence-end", type=int)
    args = parser.parse_args()

    if args.verify_authorization:
        forbidden = (
            args.authorization_source,
            args.output_dir,
            args.protected_hard_negative_registry,
            args.batch_date,
            args.sequence_start,
            args.sequence_end,
        )
        if any(value is not None for value in forbidden):
            raise ValueError(
                "--verify-authorization cannot be combined with creation arguments"
            )
        result = verify_authorization_record(
            Path(args.verify_authorization).resolve()
        )
    elif args.verify_protected_registry:
        forbidden = (
            args.authorization_source,
            args.output_dir,
            args.protected_hard_negative_registry,
            args.batch_date,
            args.sequence_start,
            args.sequence_end,
        )
        if any(value is not None for value in forbidden):
            raise ValueError(
                "--verify-protected-registry cannot be combined with creation arguments"
            )
        registry, manifests, records = load_protected_registry(
            args.verify_protected_registry
        )
        result = {
            "ok": True,
            "protectedHardNegativeRegistry": registry,
            "manifestCount": len(manifests),
            "protectedRecordCount": len(records),
        }
    else:
        required = {
            "--authorization-source": args.authorization_source,
            "--output-dir": args.output_dir,
            "--protected-hard-negative-registry": (
                args.protected_hard_negative_registry
            ),
            "--batch-date": args.batch_date,
            "--sequence-start": args.sequence_start,
            "--sequence-end": args.sequence_end,
        }
        missing = [name for name, value in required.items() if value is None]
        if missing:
            raise ValueError(f"missing creation arguments: {', '.join(missing)}")
        result = create_evidence(args)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
