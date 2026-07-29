#!/usr/bin/env python3
"""Audit a growing 160-image training hard-negative generation pool.

This command is intentionally pre-authorization.  A complete machine-clean
pool can only become ready to request an exact user authorization; every
report remains ``trainingUse=prohibited`` and ``authorizationStatus=missing``.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXPECTED_COUNT = 160
MINIMUM_SIDE = 768
NEAR_DUPLICATE_DISTANCE = 12
PLAN_KEYS = {
    "schemaVersion",
    "ok",
    "decision",
    "role",
    "trainingUse",
    "authorizationStatus",
    "sourceRoot",
    "batchDate",
    "expectedCount",
    "minimumSide",
    "nearDuplicateThreshold",
    "protectedHardNegativeRegistry",
    "itemsSha256",
    "items",
}
PLAN_ITEM_KEYS = {
    "sequence",
    "expectedFileName",
    "promptId",
    "promptFamily",
    "promptVariant",
    "role",
    "trainingUse",
}
REPORT_KEYS = {
    "schemaVersion",
    "generatedAt",
    "ok",
    "status",
    "decision",
    "role",
    "trainingUse",
    "authorizationStatus",
    "sourceRoot",
    "inputs",
    "constraints",
    "summary",
    "nextMissing",
    "familyCounts",
    "itemsCurrentSha256",
    "items",
    "unknownFiles",
    "issues",
}
PROMPT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{1,127}$")
FAMILY_PATTERN = re.compile(r"^[a-z0-9_]+$")


def load_contract_module() -> Any:
    """Load the hyphenated recorder module without invoking its CLI."""
    module_path = Path(__file__).with_name(
        "record-training-hard-negative-authorization.py"
    )
    spec = importlib.util.spec_from_file_location(
        "jiaru_training_hard_negative_authorization_contract",
        module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load training authorization contract: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CONTRACT = load_contract_module()
canonical_sha256 = CONTRACT.canonical_sha256
decode_image = CONTRACT.decode_image
hamming_distance = CONTRACT.hamming_distance
is_link_or_reparse_point = CONTRACT.is_link_or_reparse_point
is_relative_to = CONTRACT.is_relative_to
load_protected_registry = CONTRACT.load_protected_registry
read_json = CONTRACT.read_json
reject_linked_ancestors = CONTRACT.reject_linked_ancestors
reject_linked_path = CONTRACT.reject_linked_path
sha256_file = CONTRACT.sha256_file
FILE_PATTERN = CONTRACT.FILE_PATTERN
SHA256_PATTERN = CONTRACT.SHA256_PATTERN


def require_plain_file(path_value: str, label: str) -> Path:
    path_input = Path(path_value).absolute()
    if not path_input.is_file():
        raise ValueError(f"{label} is missing: {path_input}")
    reject_linked_ancestors(path_input, label)
    return path_input.resolve(strict=True)


def canonical_source_root(path_value: str) -> Path:
    source_input = Path(path_value).absolute()
    if not source_input.is_dir():
        raise ValueError(f"source root is missing: {source_input}")
    reject_linked_ancestors(source_input, "source root")
    return source_input.resolve(strict=True)


def load_generation_plan(
    plan_path: Path,
    selected_source_root: Path | None = None,
) -> tuple[dict[str, Any], Path, dict[str, Any], list[dict[str, Any]]]:
    plan = read_json(plan_path, "training hard-negative generation plan")
    if set(plan) != PLAN_KEYS:
        raise ValueError(
            "generation plan fields are not exact: "
            f"missing={sorted(PLAN_KEYS - set(plan))}, "
            f"extra={sorted(set(plan) - PLAN_KEYS)}"
        )
    if (
        plan["schemaVersion"] != 1
        or plan["ok"] is not True
        or plan["decision"] != "training_hard_negative_generation_plan"
        or plan["role"] != "training-candidate"
        or plan["trainingUse"] != "prohibited"
        or plan["authorizationStatus"] != "missing"
        or plan["expectedCount"] != EXPECTED_COUNT
        or plan["minimumSide"] != MINIMUM_SIDE
        or plan["nearDuplicateThreshold"] != NEAR_DUPLICATE_DISTANCE
    ):
        raise ValueError("generation plan contract is invalid")
    batch_date = str(plan["batchDate"])
    try:
        datetime.strptime(batch_date, "%Y%m%d")
    except ValueError as error:
        raise ValueError("generation plan batchDate must be a real YYYYMMDD date") from error

    source_root_value = str(plan["sourceRoot"] or "")
    source_root = canonical_source_root(source_root_value)
    if source_root_value != str(source_root):
        raise ValueError("generation plan sourceRoot must be an exact canonical path")
    if selected_source_root is not None and source_root != selected_source_root:
        raise ValueError("--source-root differs from the generation plan sourceRoot")
    if is_relative_to(plan_path, source_root):
        raise ValueError("generation plan cannot be stored inside the scanned source root")

    registry = plan["protectedHardNegativeRegistry"]
    if not isinstance(registry, dict) or set(registry) != {"path", "sha256"}:
        raise ValueError("generation plan registry binding fields are not exact")
    registry_path_value = str(registry.get("path") or "")
    registry_sha256 = str(registry.get("sha256") or "")
    if not SHA256_PATTERN.fullmatch(registry_sha256):
        raise ValueError("generation plan registry SHA-256 is invalid")
    registry_path = require_plain_file(
        registry_path_value,
        "protected hard-negative registry",
    )
    if registry_path_value != str(registry_path):
        raise ValueError("generation plan registry path must be an exact canonical path")
    if sha256_file(registry_path) != registry_sha256:
        raise ValueError("generation plan protected registry SHA-256 drift")
    registry_binding, _, protected_records = load_protected_registry(
        str(registry_path)
    )
    if (
        registry_binding["path"] != str(registry_path)
        or registry_binding["sha256"] != registry_sha256
    ):
        raise ValueError("generation plan protected registry binding drift")

    raw_items = plan["items"]
    if not isinstance(raw_items, list) or len(raw_items) != EXPECTED_COUNT:
        raise ValueError("generation plan must contain exactly 160 items")
    if plan["itemsSha256"] != canonical_sha256(raw_items):
        raise ValueError("generation plan items SHA-256 drift")

    seen_names: set[str] = set()
    seen_prompt_ids: set[str] = set()
    seen_family_variants: set[tuple[str, int]] = set()
    items: list[dict[str, Any]] = []
    for index, raw_item in enumerate(raw_items, start=1):
        if not isinstance(raw_item, dict) or set(raw_item) != PLAN_ITEM_KEYS:
            raise ValueError(f"generation plan item {index:03d} fields are not exact")
        sequence = raw_item["sequence"]
        file_name = str(raw_item["expectedFileName"] or "")
        prompt_id = str(raw_item["promptId"] or "")
        family = str(raw_item["promptFamily"] or "")
        variant = raw_item["promptVariant"]
        if sequence != index:
            raise ValueError("generation plan sequences must be uniquely contiguous 001-160")
        if Path(file_name).name != file_name or not file_name:
            raise ValueError(f"expectedFileName must be a direct file name: {file_name!r}")
        match = FILE_PATTERN.fullmatch(file_name)
        if not match:
            raise ValueError(f"expectedFileName violates the training naming contract: {file_name}")
        if (
            match.group("date") != batch_date
            or int(match.group("sequence")) != sequence
            or match.group("family") != family
            or int(match.group("variant")) != variant
            or not FAMILY_PATTERN.fullmatch(family)
            or not isinstance(variant, int)
            or isinstance(variant, bool)
            or not 1 <= variant <= 99
        ):
            raise ValueError(f"expectedFileName does not match item identity: {file_name}")
        if not PROMPT_ID_PATTERN.fullmatch(prompt_id):
            raise ValueError(f"promptId is invalid: {prompt_id!r}")
        if raw_item["role"] != "training-candidate" or raw_item["trainingUse"] != "prohibited":
            raise ValueError(f"generation plan item role is invalid: {file_name}")
        name_key = file_name.casefold()
        prompt_key = prompt_id.casefold()
        family_variant = (family, variant)
        if name_key in seen_names:
            raise ValueError(f"duplicate expectedFileName: {file_name}")
        if prompt_key in seen_prompt_ids:
            raise ValueError(f"duplicate promptId: {prompt_id}")
        if family_variant in seen_family_variants:
            raise ValueError(
                f"duplicate prompt family+variant: {family}/{variant:02d}"
            )
        seen_names.add(name_key)
        seen_prompt_ids.add(prompt_key)
        seen_family_variants.add(family_variant)
        items.append(dict(raw_item))
    return plan, source_root, registry_binding, protected_records


def add_issue(
    issues: list[dict[str, Any]],
    item_issues: dict[int, set[str]],
    code: str,
    message: str,
    sequences: list[int] | None = None,
    files: list[str] | None = None,
) -> None:
    issue: dict[str, Any] = {"code": code, "message": message}
    if sequences:
        issue["sequences"] = sorted(set(sequences))
        for sequence in sequences:
            item_issues[sequence].add(code)
    if files:
        issue["files"] = sorted(set(files), key=str.casefold)
    issues.append(issue)


def inspect_pool(
    source_root: Path,
    plan_items: list[dict[str, Any]],
    batch_date: str,
    protected_records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    expected_by_name = {
        str(item["expectedFileName"]): item for item in plan_items
    }
    item_issues: dict[int, set[str]] = defaultdict(set)
    issues: list[dict[str, Any]] = []
    unknown_files: list[dict[str, Any]] = []

    for entry in sorted(source_root.iterdir(), key=lambda value: value.name.casefold()):
        if entry.name in expected_by_name and entry.is_file() and not is_link_or_reparse_point(entry):
            continue
        reason = "unknown-file"
        if is_link_or_reparse_point(entry):
            reason = "link-or-reparse-point"
        elif not entry.is_file():
            reason = "unexpected-non-file-entry"
        elif entry.name.casefold() in {
            name.casefold() for name in expected_by_name
        }:
            reason = "file-name-case-drift"
        unknown_files.append({"name": entry.name, "path": str(entry.absolute()), "reason": reason})
    if unknown_files:
        add_issue(
            issues,
            item_issues,
            "UNKNOWN_SOURCE_ENTRY",
            "source root contains entries outside the exact 160-item plan",
            files=[item["name"] for item in unknown_files],
        )

    current_items: list[dict[str, Any]] = []
    decoded_by_sequence: dict[int, dict[str, Any]] = {}
    for planned in plan_items:
        sequence = int(planned["sequence"])
        file_name = str(planned["expectedFileName"])
        source_path = source_root / file_name
        current: dict[str, Any] = {
            **planned,
            "sourcePath": str(source_path),
            "state": "missing",
            "issueCodes": [],
            "sha256": None,
            "width": None,
            "height": None,
            "format": None,
            "bytes": None,
            "dhash256": None,
        }
        if not source_path.exists():
            current_items.append(current)
            continue
        if not source_path.is_file() or is_link_or_reparse_point(source_path):
            add_issue(
                issues,
                item_issues,
                "EXPECTED_PATH_NOT_PLAIN_FILE",
                f"expected path is not a plain file: {file_name}",
                [sequence],
                [file_name],
            )
            current["state"] = "failed"
            current_items.append(current)
            continue
        try:
            reject_linked_path(source_path, source_root)
            resolved = source_path.resolve(strict=True)
            if not is_relative_to(resolved, source_root):
                raise ValueError("resolved image escapes source root")
            image_hash = sha256_file(resolved)
            width, height, image_format, dhash = decode_image(
                resolved,
                minimum_side=MINIMUM_SIDE,
            )
            match = FILE_PATTERN.fullmatch(file_name)
            if (
                match is None
                or match.group("date") != batch_date
                or int(match.group("sequence")) != sequence
                or match.group("family") != planned["promptFamily"]
                or int(match.group("variant")) != planned["promptVariant"]
            ):
                raise ValueError("current file name differs from the planned identity")
            current.update(
                {
                    "state": "passed",
                    "sourcePath": str(resolved),
                    "sha256": image_hash,
                    "width": width,
                    "height": height,
                    "format": image_format,
                    "bytes": resolved.stat().st_size,
                    "dhash256": dhash,
                }
            )
            decoded_by_sequence[sequence] = current
        except (OSError, ValueError) as error:
            add_issue(
                issues,
                item_issues,
                "IMAGE_MACHINE_GATE_FAILED",
                f"{file_name}: {error}",
                [sequence],
                [file_name],
            )
            current["state"] = "failed"
        current_items.append(current)

    hash_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in decoded_by_sequence.values():
        hash_groups[str(item["sha256"])].append(item)
    for image_hash, group in sorted(hash_groups.items()):
        if len(group) > 1:
            add_issue(
                issues,
                item_issues,
                "BATCH_EXACT_DUPLICATE",
                f"batch contains an exact duplicate SHA-256: {image_hash}",
                [int(item["sequence"]) for item in group],
                [str(item["expectedFileName"]) for item in group],
            )

    decoded = [decoded_by_sequence[key] for key in sorted(decoded_by_sequence)]
    for left_index, left in enumerate(decoded):
        for right in decoded[left_index + 1 :]:
            if left["sha256"] == right["sha256"]:
                continue
            distance = hamming_distance(str(left["dhash256"]), str(right["dhash256"]))
            if distance <= NEAR_DUPLICATE_DISTANCE:
                add_issue(
                    issues,
                    item_issues,
                    "BATCH_PERCEPTUAL_NEAR_DUPLICATE",
                    f"batch dHash256 distance {distance} is not greater than 12",
                    [int(left["sequence"]), int(right["sequence"])],
                    [str(left["expectedFileName"]), str(right["expectedFileName"])],
                )

    protected_hashes: dict[str, str] = {
        str(item["imageSha256"]): str(item["fileName"]) for item in protected_records
    }
    protected_sources: dict[str, str] = {
        str(item["sourceIdentity"]): str(item["fileName"]) for item in protected_records
    }
    for item in decoded:
        sequence = int(item["sequence"])
        file_name = str(item["expectedFileName"])
        source_identity = f"ai-hard-negative-{batch_date}:{item['promptFamily']}"
        if str(item["sha256"]) in protected_hashes:
            add_issue(
                issues,
                item_issues,
                "PROTECTED_EXACT_DUPLICATE",
                f"{file_name} duplicates protected {protected_hashes[str(item['sha256'])]}",
                [sequence],
                [file_name],
            )
        if source_identity in protected_sources:
            add_issue(
                issues,
                item_issues,
                "PROTECTED_SOURCE_OVERLAP",
                f"{file_name} shares protected source identity {source_identity}",
                [sequence],
                [file_name],
            )
        for protected in protected_records:
            if str(item["sha256"]) == str(protected["imageSha256"]):
                continue
            distance = hamming_distance(
                str(item["dhash256"]),
                str(protected["dhash256"]),
            )
            if distance <= NEAR_DUPLICATE_DISTANCE:
                add_issue(
                    issues,
                    item_issues,
                    "PROTECTED_PERCEPTUAL_NEAR_DUPLICATE",
                    f"{file_name} is dHash256 distance {distance} from protected {protected['fileName']}",
                    [sequence],
                    [file_name],
                )
                break

    for item in current_items:
        sequence = int(item["sequence"])
        codes = sorted(item_issues[sequence])
        item["issueCodes"] = codes
        if codes and item["state"] != "missing":
            item["state"] = "failed"
    issues.sort(
        key=lambda item: (
            str(item["code"]),
            list(item.get("sequences") or []),
            list(item.get("files") or []),
        )
    )
    return current_items, unknown_files, issues


def validate_previous_report(
    previous_path: Path,
    plan_binding: dict[str, Any],
    source_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    previous = read_json(previous_path, "previous generation progress report")
    if set(previous) != REPORT_KEYS:
        raise ValueError("previous report fields are not exact")
    if (
        previous.get("schemaVersion") != 1
        or previous.get("role") != "training-candidate"
        or previous.get("trainingUse") != "prohibited"
        or previous.get("authorizationStatus") != "missing"
        or previous.get("sourceRoot") != str(source_root)
        or previous.get("itemsCurrentSha256")
        != canonical_sha256(previous.get("items"))
    ):
        raise ValueError("previous report contract or items hash is invalid")
    inputs = previous.get("inputs")
    if not isinstance(inputs, dict) or inputs.get("generationPlan") != plan_binding:
        raise ValueError("previous report generation plan binding drift")
    items = previous.get("items")
    if not isinstance(items, list) or len(items) != EXPECTED_COUNT:
        raise ValueError("previous report item set is invalid")
    return previous, {
        "path": str(previous_path),
        "sha256": sha256_file(previous_path),
    }


def enforce_completed_file_stability(
    previous: dict[str, Any] | None,
    current_items: list[dict[str, Any]],
) -> None:
    if previous is None:
        return
    current_by_sequence = {int(item["sequence"]): item for item in current_items}
    for old in previous["items"]:
        if old.get("state") != "passed":
            continue
        sequence = int(old["sequence"])
        current = current_by_sequence.get(sequence)
        if (
            current is None
            or current.get("state") != "passed"
            or current.get("sha256") != old.get("sha256")
        ):
            raise ValueError(
                "previously completed image SHA-256 drift: "
                f"{old.get('expectedFileName')}"
            )


def build_report(
    plan_path: Path,
    selected_source_root: Path | None,
    previous_path: Path | None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    plan, source_root, registry_binding, protected_records = load_generation_plan(
        plan_path,
        selected_source_root,
    )
    plan_binding = {"path": str(plan_path), "sha256": sha256_file(plan_path)}
    previous: dict[str, Any] | None = None
    previous_binding: dict[str, Any] | None = None
    if previous_path is not None:
        previous, previous_binding = validate_previous_report(
            previous_path,
            plan_binding,
            source_root,
        )
    items, unknown_files, issues = inspect_pool(
        source_root,
        plan["items"],
        str(plan["batchDate"]),
        protected_records,
    )
    enforce_completed_file_stability(previous, items)

    present = sum(item["state"] != "missing" for item in items)
    missing = sum(item["state"] == "missing" for item in items)
    passed = sum(item["state"] == "passed" for item in items)
    failed = sum(item["state"] == "failed" for item in items) + len(unknown_files)
    ready = present == EXPECTED_COUNT and missing == 0 and failed == 0 and passed == EXPECTED_COUNT
    decision = (
        "ready_to_request_exact_user_authorization"
        if ready
        else "hold_generation_incomplete_or_machine_gate_failed"
    )

    family_counts: dict[str, dict[str, int]] = {}
    families = sorted({str(item["promptFamily"]) for item in items})
    for family in families:
        members = [item for item in items if item["promptFamily"] == family]
        family_counts[family] = {
            "expected": len(members),
            "present": sum(item["state"] != "missing" for item in members),
            "missing": sum(item["state"] == "missing" for item in members),
            "passed": sum(item["state"] == "passed" for item in members),
            "failed": sum(item["state"] == "failed" for item in members),
        }
    next_missing_item = next(
        (item for item in items if item["state"] == "missing"),
        None,
    )
    next_missing = (
        {
            "sequence": next_missing_item["sequence"],
            "expectedFileName": next_missing_item["expectedFileName"],
            "promptId": next_missing_item["promptId"],
            "promptFamily": next_missing_item["promptFamily"],
            "promptVariant": next_missing_item["promptVariant"],
        }
        if next_missing_item is not None
        else None
    )
    report = {
        "schemaVersion": 1,
        "generatedAt": generated_at or datetime.now(timezone.utc).isoformat(),
        "ok": ready,
        "status": "READY" if ready else "HOLD",
        "decision": decision,
        "role": "training-candidate",
        "trainingUse": "prohibited",
        "authorizationStatus": "missing",
        "sourceRoot": str(source_root),
        "inputs": {
            "generationPlan": plan_binding,
            "protectedHardNegativeRegistry": registry_binding,
            "protectedRecordsSha256": canonical_sha256(protected_records),
            "previousReport": previous_binding,
        },
        "constraints": {
            "expectedCount": EXPECTED_COUNT,
            "minimumSide": MINIMUM_SIDE,
            "nearDuplicateThreshold": NEAR_DUPLICATE_DISTANCE,
            "unknownEntriesAllowed": False,
            "linksOrReparsePointsAllowed": False,
        },
        "summary": {
            "expected": EXPECTED_COUNT,
            "present": present,
            "missing": missing,
            "passed": passed,
            "failed": failed,
            "unknown": len(unknown_files),
        },
        "nextMissing": next_missing,
        "familyCounts": family_counts,
        "itemsCurrentSha256": canonical_sha256(items),
        "items": items,
        "unknownFiles": unknown_files,
        "issues": issues,
    }
    return report


def verify_report(report_path: Path) -> dict[str, Any]:
    stored = read_json(report_path, "generation progress report")
    if set(stored) != REPORT_KEYS:
        raise ValueError("generation progress report fields are not exact")
    inputs = stored.get("inputs")
    if not isinstance(inputs, dict) or set(inputs) != {
        "generationPlan",
        "protectedHardNegativeRegistry",
        "protectedRecordsSha256",
        "previousReport",
    }:
        raise ValueError("generation progress report input bindings are invalid")
    plan_binding = inputs["generationPlan"]
    if not isinstance(plan_binding, dict) or set(plan_binding) != {"path", "sha256"}:
        raise ValueError("generation progress report plan binding is invalid")
    plan_path = require_plain_file(str(plan_binding.get("path") or ""), "generation plan")
    if sha256_file(plan_path) != plan_binding.get("sha256"):
        raise ValueError("generation progress report plan SHA-256 drift")
    previous_binding = inputs["previousReport"]
    previous_path: Path | None = None
    if previous_binding is not None:
        if not isinstance(previous_binding, dict) or set(previous_binding) != {"path", "sha256"}:
            raise ValueError("generation progress report previous binding is invalid")
        previous_path = require_plain_file(
            str(previous_binding.get("path") or ""),
            "previous generation progress report",
        )
        if previous_path == report_path:
            raise ValueError("generation progress report cannot bind itself as previous")
        if sha256_file(previous_path) != previous_binding.get("sha256"):
            raise ValueError("generation progress report previous SHA-256 drift")
    replay = build_report(
        plan_path,
        canonical_source_root(str(stored.get("sourceRoot") or "")),
        previous_path,
        generated_at=str(stored.get("generatedAt") or ""),
    )
    if replay != stored:
        raise ValueError("generation progress report deep replay drift")
    return {
        "ok": True,
        "report": str(report_path),
        "reportSha256": sha256_file(report_path),
        "decision": stored["decision"],
        "trainingUse": "prohibited",
        "authorizationStatus": "missing",
        "summary": stored["summary"],
        "itemsCurrentSha256": stored["itemsCurrentSha256"],
    }


def validate_output_path(
    output_value: str,
    source_root: Path,
    input_paths: list[Path],
) -> Path:
    output = Path(output_value).absolute()
    if output.exists():
        raise ValueError(f"refusing to overwrite existing output: {output}")
    if output.parent == output or not output.parent.is_dir():
        raise ValueError("output parent must be an existing directory")
    reject_linked_ancestors(output.parent, "output parent")
    output_parent = output.parent.resolve(strict=True)
    output = output_parent / output.name
    if is_relative_to(output, source_root):
        raise ValueError("output cannot be placed inside the scanned source root")
    for input_path in input_paths:
        if output == input_path:
            raise ValueError("output cannot overwrite an input")
    return output


def write_atomic_json(path: Path, value: dict[str, Any]) -> None:
    payload = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    temporary = path.parent / f".{path.name}.staging-{os.getpid()}-{uuid.uuid4().hex}"
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as error:
            raise ValueError(f"refusing to overwrite existing output: {path}") from error
        except OSError as error:
            if path.exists():
                raise ValueError(
                    f"refusing to overwrite existing output: {path}"
                ) from error
            raise ValueError(
                f"cannot atomically publish generation progress report: {path}: {error}"
            ) from error
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit the read-only progress of a 160-image training hard-negative pool."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--source-root")
    mode.add_argument("--verify-report")
    parser.add_argument("--plan")
    parser.add_argument("--protected-hard-negative-registry")
    parser.add_argument("--previous-report")
    parser.add_argument("--output")
    args = parser.parse_args()

    if args.verify_report:
        forbidden = (
            args.plan,
            args.protected_hard_negative_registry,
            args.previous_report,
            args.output,
        )
        if any(value is not None for value in forbidden):
            raise ValueError("--verify-report cannot be combined with creation arguments")
        report_path = require_plain_file(args.verify_report, "generation progress report")
        result = verify_report(report_path)
    else:
        missing = [
            name
            for name, value in {
                "--plan": args.plan,
                "--protected-hard-negative-registry": args.protected_hard_negative_registry,
                "--output": args.output,
            }.items()
            if value is None
        ]
        if missing:
            raise ValueError(f"missing creation arguments: {', '.join(missing)}")
        source_root = canonical_source_root(args.source_root)
        plan_path = require_plain_file(args.plan, "generation plan")
        registry_path = require_plain_file(
            args.protected_hard_negative_registry,
            "protected hard-negative registry",
        )
        previous_path = (
            require_plain_file(args.previous_report, "previous generation progress report")
            if args.previous_report
            else None
        )
        plan, planned_root, _, _ = load_generation_plan(plan_path, source_root)
        plan_registry = plan["protectedHardNegativeRegistry"]
        if (
            str(registry_path) != plan_registry["path"]
            or sha256_file(registry_path) != plan_registry["sha256"]
        ):
            raise ValueError("CLI registry differs from the exact generation plan binding")
        output = validate_output_path(
            args.output,
            planned_root,
            [path for path in [plan_path, registry_path, previous_path] if path is not None],
        )
        report = build_report(plan_path, source_root, previous_path)
        # Re-scan immediately before the atomic publication to reject concurrent drift.
        replay = build_report(
            plan_path,
            source_root,
            previous_path,
            generated_at=report["generatedAt"],
        )
        if replay != report:
            raise ValueError("source pool changed during progress audit")
        write_atomic_json(output, report)
        try:
            result = verify_report(output)
        except Exception:
            output.unlink(missing_ok=True)
            raise
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
