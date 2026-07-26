#!/usr/bin/env python3
"""Monotonically extend and deeply replay a protected hard-negative registry.

The registry remains schema-v1 compatible with
``record-training-hard-negative-authorization.py``.  A derived registry keeps
the complete parent entry list as an immutable prefix and records a
SHA-256-bound parent link, so verification can prove that older manifests were
not deleted, replaced, reordered, or assigned a different role.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import uuid
from collections import Counter
from pathlib import Path
from types import ModuleType
from typing import Any


ROLE_VALUES = {"training", "holdout"}
APPEND_CONTRACT_KEYS = {
    "decision",
    "previousRegistry",
    "appendedManifestCount",
    "appendedEntriesSha256",
}
APPEND_DECISION = "monotonic_protected_hard_negative_registry_append"


def load_registry_contract() -> ModuleType:
    contract_path = Path(__file__).with_name(
        "record-training-hard-negative-authorization.py"
    )
    spec = importlib.util.spec_from_file_location(
        "jiaru_training_hard_negative_authorization_contract",
        contract_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load registry contract: {contract_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CONTRACT = load_registry_contract()


def path_key(path: Path) -> str:
    return os.path.normcase(str(path)).casefold()


def canonical_existing_file(path_value: str, label: str) -> Path:
    path_input = Path(path_value).absolute()
    if not path_input.is_file():
        raise ValueError(f"{label} is missing: {path_input}")
    CONTRACT.reject_linked_ancestors(path_input, label)
    return path_input.resolve(strict=True)


def registry_document(path: Path) -> dict[str, Any]:
    return CONTRACT.read_json(path, "protected hard-negative registry")


def verify_registry(
    path_value: str,
    *,
    visited: set[str] | None = None,
) -> dict[str, Any]:
    registry_path = canonical_existing_file(
        path_value,
        "protected hard-negative registry",
    )
    seen = set() if visited is None else visited
    registry_key = path_key(registry_path)
    if registry_key in seen:
        raise ValueError(
            f"protected registry lineage contains a cycle: {registry_path}"
        )
    seen.add(registry_key)
    try:
        binding, manifests, records = CONTRACT.load_protected_registry(
            str(registry_path)
        )
        document = registry_document(registry_path)
        entries = document["entries"]
        append_contract = document.get("monotonicAppend")
        lineage_depth = 0
        appended_manifest_count = 0

        if append_contract is not None:
            if (
                not isinstance(append_contract, dict)
                or set(append_contract) != APPEND_CONTRACT_KEYS
                or append_contract.get("decision") != APPEND_DECISION
            ):
                raise ValueError(
                    "protected registry monotonic append contract is invalid"
                )
            previous = append_contract.get("previousRegistry")
            if not isinstance(previous, dict):
                raise ValueError("protected registry previousRegistry binding is invalid")
            previous_path = canonical_existing_file(
                str(previous.get("path") or ""),
                "previous protected hard-negative registry",
            )
            if path_key(previous_path) == registry_key:
                raise ValueError("protected registry cannot name itself as its parent")
            expected_parent_hash = str(previous.get("sha256") or "")
            if CONTRACT.sha256_file(previous_path) != expected_parent_hash:
                raise ValueError("previous protected registry SHA-256 drift")

            parent = verify_registry(str(previous_path), visited=seen)
            if previous != parent["binding"]:
                raise ValueError("previous protected registry binding drift")
            parent_entries = parent["document"]["entries"]
            if len(entries) <= len(parent_entries):
                raise ValueError(
                    "derived protected registry must append at least one manifest"
                )
            if entries[: len(parent_entries)] != parent_entries:
                raise ValueError(
                    "old protected registry entries were deleted, replaced, "
                    "reordered, or assigned a different role"
                )
            appended_entries = entries[len(parent_entries) :]
            if appended_entries != sorted(
                appended_entries,
                key=lambda item: path_key(Path(str(item["path"]))),
            ):
                raise ValueError(
                    "new protected registry entries are not in canonical path order"
                )
            if (
                append_contract.get("appendedManifestCount")
                != len(appended_entries)
                or append_contract.get("appendedEntriesSha256")
                != CONTRACT.canonical_sha256(appended_entries)
            ):
                raise ValueError("protected registry appended-entry evidence drift")
            lineage_depth = int(parent["lineageDepth"]) + 1
            appended_manifest_count = len(appended_entries)

        return {
            "ok": True,
            "registryPath": str(registry_path),
            "registrySha256": CONTRACT.sha256_file(registry_path),
            "binding": binding,
            "document": document,
            "manifestCount": len(manifests),
            "protectedRecordCount": len(records),
            "lineageDepth": lineage_depth,
            "appendedManifestCount": appended_manifest_count,
        }
    finally:
        seen.remove(registry_key)


def canonical_output_path(path_value: str) -> Path:
    output_input = Path(path_value).absolute()
    if os.path.lexists(output_input):
        raise ValueError(f"refusing to overwrite existing output: {output_input}")
    output_input.parent.mkdir(parents=True, exist_ok=True)
    CONTRACT.reject_linked_ancestors(
        output_input.parent,
        "protected registry output parent",
    )
    output_path = output_input.resolve(strict=False)
    if os.path.lexists(output_path):
        raise ValueError(f"refusing to overwrite existing output: {output_path}")
    return output_path


def create_registry(args: argparse.Namespace) -> dict[str, Any]:
    base = verify_registry(args.base_registry)
    base_path = Path(base["registryPath"])
    base_hash = str(base["registrySha256"])
    base_document = base["document"]
    old_entries = base_document["entries"]

    output_path = canonical_output_path(args.output)
    protected_path_keys = {path_key(base_path)}
    protected_path_keys.update(
        path_key(Path(str(entry["path"])).resolve(strict=True))
        for entry in old_entries
    )
    if path_key(output_path) in protected_path_keys:
        raise ValueError(
            "output path aliases the base registry or a protected manifest"
        )

    new_entries: list[dict[str, str]] = []
    seen_new_paths: set[str] = set()
    for number, value in enumerate(args.manifest, start=1):
        role, manifest_value = value
        if role not in ROLE_VALUES:
            raise ValueError(
                f"new manifest {number} role must be training or holdout: {role}"
            )
        manifest_path = canonical_existing_file(
            manifest_value,
            f"new protected hard-negative manifest {number}",
        )
        manifest_key = path_key(manifest_path)
        if manifest_key == path_key(output_path):
            raise ValueError("output path aliases a new protected manifest")
        if manifest_key in protected_path_keys or manifest_key in seen_new_paths:
            raise ValueError(
                f"duplicate protected registry manifest path: {manifest_path}"
            )
        seen_new_paths.add(manifest_key)
        new_entries.append(
            {
                "path": str(manifest_path),
                "sha256": CONTRACT.sha256_file(manifest_path),
                "role": role,
            }
        )

    new_entries.sort(key=lambda item: path_key(Path(item["path"])))
    entries = [*old_entries, *new_entries]
    # This is the authoritative deep replay: manifest contract, explicit role,
    # item hash, image hash/dimensions/format, and cross-manifest identity.
    CONTRACT.load_protected_manifests(entries)
    role_counts = Counter(str(entry["role"]) for entry in entries)
    document = {
        "schemaVersion": 1,
        "ok": True,
        "decision": "protected_hard_negative_registry",
        "monotonicAppend": {
            "decision": APPEND_DECISION,
            "previousRegistry": base["binding"],
            "appendedManifestCount": len(new_entries),
            "appendedEntriesSha256": CONTRACT.canonical_sha256(new_entries),
        },
        "summary": {
            "manifestCount": len(entries),
            "trainingManifestCount": role_counts["training"],
            "holdoutManifestCount": role_counts["holdout"],
        },
        "entriesSha256": CONTRACT.canonical_sha256(entries),
        "entries": entries,
    }

    staging_path = output_path.parent / (
        f".{output_path.name}.staging-{os.getpid()}-{uuid.uuid4().hex}"
    )
    try:
        with staging_path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(document, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())

        verify_registry(str(staging_path))
        current_base = verify_registry(str(base_path))
        if (
            current_base["registrySha256"] != base_hash
            or current_base["binding"] != base["binding"]
            or current_base["document"]["entries"] != old_entries
        ):
            raise ValueError("base protected registry changed during update")
        # Replay all new manifest and image bytes immediately before publication.
        CONTRACT.load_protected_manifests(entries)
        if os.path.lexists(output_path):
            raise ValueError(f"refusing to overwrite existing output: {output_path}")
        try:
            # Same-directory hard-link publication is atomic and fails instead
            # of replacing a destination created by another process.
            os.link(staging_path, output_path)
        except FileExistsError as error:
            raise ValueError(
                f"refusing to overwrite existing output: {output_path}"
            ) from error
        staging_path.unlink()
        try:
            result = verify_registry(str(output_path))
        except Exception:
            output_path.unlink(missing_ok=True)
            raise
    finally:
        staging_path.unlink(missing_ok=True)

    return {
        "ok": True,
        "decision": APPEND_DECISION,
        "registryPath": result["registryPath"],
        "registrySha256": result["registrySha256"],
        "entriesSha256": result["binding"]["entriesSha256"],
        "manifestCount": result["manifestCount"],
        "trainingManifestCount": result["binding"]["trainingManifestCount"],
        "holdoutManifestCount": result["binding"]["holdoutManifestCount"],
        "protectedRecordCount": result["protectedRecordCount"],
        "lineageDepth": result["lineageDepth"],
        "appendedManifestCount": result["appendedManifestCount"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Monotonically append deeply verified manifests to a protected "
            "hard-negative registry."
        )
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--base-registry")
    mode.add_argument("--verify-registry")
    parser.add_argument("--output")
    parser.add_argument(
        "--manifest",
        "--append-manifest",
        dest="manifest",
        action="append",
        nargs=2,
        metavar=("ROLE", "PATH"),
        default=[],
    )
    args = parser.parse_args()

    if args.verify_registry:
        if args.output is not None or args.manifest:
            raise ValueError(
                "--verify-registry cannot be combined with update arguments"
            )
        verified = verify_registry(args.verify_registry)
        result = {
            "ok": True,
            "decision": "protected_hard_negative_registry_verified",
            "registryPath": verified["registryPath"],
            "registrySha256": verified["registrySha256"],
            "entriesSha256": verified["binding"]["entriesSha256"],
            "manifestCount": verified["manifestCount"],
            "trainingManifestCount": verified["binding"][
                "trainingManifestCount"
            ],
            "holdoutManifestCount": verified["binding"]["holdoutManifestCount"],
            "protectedRecordCount": verified["protectedRecordCount"],
            "lineageDepth": verified["lineageDepth"],
            "appendedManifestCount": verified["appendedManifestCount"],
        }
    else:
        missing: list[str] = []
        if args.output is None:
            missing.append("--output")
        if not args.manifest:
            missing.append("--manifest ROLE PATH")
        if missing:
            raise ValueError(f"missing update arguments: {', '.join(missing)}")
        result = create_registry(args)

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error
