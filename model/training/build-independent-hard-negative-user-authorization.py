#!/usr/bin/env python3
"""Build a traceable, exact-file authorization for an independent holdout.

The script never scans a directory to decide the authorization scope. It binds
the already-reviewed candidate list and pre-authorization machine audit, then
requires the user's message to match the generated confirmation text exactly.
The resulting schema-v2 source remains training-prohibited and is consumed by
``record-independent-hard-negative-authorization.py`` before first inference.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any


SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
FILE_PATTERN = re.compile(
    r"^hard_negative_independent_(?P<date>\d{8})_(?P<sequence>\d{3})_"
    r"(?P<family>[a-z0-9_]+)_(?P<variant>\d{2})\.(?P<suffix>png|jpe?g|webp)$",
    re.IGNORECASE,
)
REQUIRED_USES = [
    "independent-release-test",
    "long-term-regression",
    "model-diagnostic-evaluation",
    "data-quality-review",
]
EXCLUDED_USES = ["commercial-model-training"]
QUALITY_CONSTRAINT = "authorization-does-not-relax-quality-gates"
ROLE_CONSTRAINT = "authorization-does-not-assign-train-validation-or-holdout-role"
MINIMUM_IMAGES = 100
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


def require_plain_file(path_value: Any, label: str) -> Path:
    path_input = Path(str(path_value or "")).absolute()
    if not path_input.is_file():
        raise ValueError(f"{label} is missing: {path_input}")
    reject_linked_ancestors(path_input, label)
    return path_input.resolve(strict=True)


def require_bound_file(path_value: Any, hash_value: Any, label: str) -> Path:
    path = require_plain_file(path_value, label)
    expected = str(hash_value or "")
    if not SHA256_PATTERN.fullmatch(expected) or sha256_file(path) != expected:
        raise ValueError(f"{label} SHA-256 binding has drifted")
    return path


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def required_confirmation_text(
    source_root: Path,
    count: int,
    sequence_start: int,
    sequence_end: int,
) -> str:
    return (
        f"我授权 {source_root} 中最终冻结的{count}张精确文件清单"
        f"（{sequence_start}—{sequence_end}）用于独立发布测试、长期回归、"
        "模型诊断评估和数据质量审核；不用于商业模型训练；"
        "授权不放宽任何质量门。"
    )


def validate_sources(
    candidate_list_path: Path,
    preauthorization_audit_path: Path,
) -> dict[str, Any]:
    candidate_list = read_json(candidate_list_path, "generated candidate list")
    audit = read_json(preauthorization_audit_path, "pre-authorization machine audit")
    if (
        candidate_list.get("schemaVersion") != 1
        or candidate_list.get("decision")
        != "generated_independent_holdout_candidate_list_ready_for_exact_user_authorization"
        or candidate_list.get("trainingUse") != "prohibited"
        or candidate_list.get("evaluationUse")
        != "prohibited-until-exact-user-authorization-and-atomic-freeze"
        or candidate_list.get("qualityGateRelaxed") is not False
        or candidate_list.get("candidateModelInferencePerformed") is not False
    ):
        raise ValueError("generated candidate list contract is invalid")
    if (
        audit.get("schemaVersion") != 1
        or audit.get("ok") is not True
        or audit.get("decision")
        != "pre_authorization_machine_audit_pass_candidate_only"
        or audit.get("trainingUse") != "prohibited"
        or audit.get("evaluationUse")
        != "prohibited-until-exact-user-authorization-and-atomic-freeze"
        or audit.get("candidateModelInferencePerformed") is not False
        or audit.get("nearDuplicateThreshold") != 12
        or audit.get("nearDuplicatePairs") != []
    ):
        raise ValueError("pre-authorization machine audit contract is invalid")

    source_input = Path(str(candidate_list.get("sourceRoot") or ""))
    if not source_input.is_absolute() or not source_input.is_dir():
        raise ValueError("candidate sourceRoot must be an existing absolute directory")
    reject_linked_ancestors(source_input, "candidate sourceRoot")
    source_root = source_input.resolve(strict=True)
    if audit.get("sourceRoot") != str(source_root):
        raise ValueError("candidate list and pre-authorization audit sourceRoot differ")

    sequence_start = int(candidate_list.get("sequenceStart", -1))
    sequence_end = int(candidate_list.get("sequenceEnd", -1))
    count = int(candidate_list.get("count", -1))
    if (
        count < MINIMUM_IMAGES
        or sequence_start < 0
        or sequence_end < sequence_start
        or sequence_end - sequence_start + 1 != count
        or audit.get("sequenceStart") != sequence_start
        or audit.get("sequenceEnd") != sequence_end
        or audit.get("fileCount") != count
        or audit.get("decodedCount") != count
    ):
        raise ValueError("candidate count or contiguous sequence contract is invalid")

    raw_candidates = candidate_list.get("items")
    raw_records = audit.get("records")
    if (
        not isinstance(raw_candidates, list)
        or not isinstance(raw_records, list)
        or len(raw_candidates) != count
        or len(raw_records) != count
        or audit.get("recordsSha256") != canonical_sha256(raw_records)
    ):
        raise ValueError("candidate or audit item inventory is invalid")

    protected = audit.get("protectedCrossCheck")
    if (
        not isinstance(protected, dict)
        or protected.get("decision") != "pass_no_protected_hard_negative_overlap"
        or protected.get("candidateRecordCount") != count
        or protected.get("exactSha256Matches") != 0
        or protected.get("sourceIdentityMatches") != 0
        or protected.get("perceptualMatchesAtOrBelowThreshold") != 0
        or protected.get("nearDuplicateThreshold") != 12
    ):
        raise ValueError("protected hard-negative cross-check is not a clean PASS")

    candidates_by_sequence: dict[int, dict[str, Any]] = {}
    records: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    seen_hashes: set[str] = set()
    for number, item in enumerate(raw_candidates, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"candidate item {number} must be an object")
        sequence = int(item.get("sequence", -1))
        if sequence in candidates_by_sequence:
            raise ValueError(f"duplicate candidate sequence: {sequence}")
        candidates_by_sequence[sequence] = item

    for number, record in enumerate(raw_records, start=1):
        if not isinstance(record, dict):
            raise ValueError(f"audit record {number} must be an object")
        sequence = int(record.get("sequence", -1))
        expected_sequence = sequence_start + number - 1
        if sequence != expected_sequence:
            raise ValueError("audit records are not in contiguous sequence order")
        candidate = candidates_by_sequence.get(sequence)
        if candidate is None:
            raise ValueError(f"candidate list is missing sequence {sequence}")
        relative = str(record.get("relativePath") or "").replace("\\", "/")
        relative_path = Path(relative)
        if (
            not relative
            or relative_path.is_absolute()
            or any(part in {"", ".", ".."} for part in relative_path.parts)
            or relative.casefold() in seen_paths
        ):
            raise ValueError(f"unsafe or duplicate relativePath: {relative!r}")
        current = (source_root / relative_path).resolve(strict=True)
        if not is_relative_to(current, source_root) or not current.is_file():
            raise ValueError(f"authorized image escapes or is missing: {relative}")
        reject_linked_ancestors(current, f"authorized image {relative}")
        if (
            Path(str(record.get("sourcePath") or "")).resolve() != current
            or Path(str(candidate.get("sourcePath") or "")).resolve() != current
        ):
            raise ValueError(f"candidate or audit sourcePath drift: {relative}")
        file_name = str(record.get("fileName") or "")
        match = FILE_PATTERN.fullmatch(file_name)
        if (
            current.name != file_name
            or not match
            or int(match.group("sequence")) != sequence
            or str(record.get("batchDate") or "") != match.group("date")
            or str(record.get("promptFamily") or "") != match.group("family").lower()
            or int(record.get("promptVariant", -1)) != int(match.group("variant"))
        ):
            raise ValueError(f"audit record naming contract drift: {file_name}")
        image_hash = str(record.get("sha256") or "")
        if (
            not SHA256_PATTERN.fullmatch(image_hash)
            or image_hash in seen_hashes
            or sha256_file(current) != image_hash
            or current.stat().st_size != int(record.get("bytes", -1))
        ):
            raise ValueError(f"authorized image identity drift: {relative}")
        if any(
            candidate.get(key) != record.get(record_key)
            for key, record_key in (
                ("fileName", "fileName"),
                ("relativePath", "relativePath"),
                ("sha256", "sha256"),
                ("bytes", "bytes"),
                ("sequence", "sequence"),
            )
        ):
            raise ValueError(f"candidate list and audit record differ: {relative}")
        if (
            candidate.get("modelInferenceBeforeFreeze") is not False
            or candidate.get("originalResolutionVisualReview") != "pass-candidate-only"
        ):
            raise ValueError(f"candidate-only review state is invalid: {relative}")
        seen_paths.add(relative.casefold())
        seen_hashes.add(image_hash)
        records.append(record)

    expected_sequences = set(range(sequence_start, sequence_end + 1))
    if set(candidates_by_sequence) != expected_sequences:
        raise ValueError("candidate sequence coverage is incomplete")

    external_bindings: dict[str, dict[str, Any]] = {}
    for key, path_key, hash_key in (
        ("candidateWeights", "candidateWeights", "candidateWeightsSha256"),
        ("candidateThresholdReport", "path", "sha256"),
        ("protectedHardNegativeRegistry", "protectedRegistry", "protectedRegistrySha256"),
    ):
        if key == "candidateThresholdReport":
            threshold = audit.get("thresholdVerification")
            if not isinstance(threshold, dict):
                raise ValueError("threshold verification binding is missing")
            path_value = threshold.get(path_key)
            hash_value = threshold.get(hash_key)
        else:
            path_value = audit.get(path_key)
            hash_value = audit.get(hash_key)
        path = require_bound_file(path_value, hash_value, key)
        external_bindings[key] = {
            "path": str(path),
            "sha256": sha256_file(path),
        }
    threshold = audit["thresholdVerification"]
    if (
        threshold.get("weightsSha256")
        != external_bindings["candidateWeights"]["sha256"]
        or threshold.get("decision")
        != "calibrated_threshold_ready_for_candidate_manifest"
        or float(threshold.get("scoreThreshold", -1)) <= 0
    ):
        raise ValueError("candidate threshold and weights binding is invalid")
    external_bindings["candidateThresholdReport"]["scoreThreshold"] = float(
        threshold["scoreThreshold"]
    )

    return {
        "sourceRoot": str(source_root),
        "sequenceStart": sequence_start,
        "sequenceEnd": sequence_end,
        "count": count,
        "records": records,
        "recordsSha256": canonical_sha256(records),
        "candidateList": {
            "path": str(candidate_list_path),
            "sha256": sha256_file(candidate_list_path),
        },
        "preauthorizationAudit": {
            "path": str(preauthorization_audit_path),
            "sha256": sha256_file(preauthorization_audit_path),
        },
        **external_bindings,
    }


def build_authorization(
    candidate_list_path: Path,
    preauthorization_audit_path: Path,
    user_message: str,
    thread_id: str,
    decision_id: str,
) -> dict[str, Any]:
    binding = validate_sources(candidate_list_path, preauthorization_audit_path)
    expected_message = required_confirmation_text(
        Path(binding["sourceRoot"]),
        binding["count"],
        binding["sequenceStart"],
        binding["sequenceEnd"],
    )
    if user_message != expected_message:
        raise ValueError("user message does not exactly match required confirmation text")
    if not UUID_PATTERN.fullmatch(thread_id):
        raise ValueError("--thread-id must be a lowercase UUID")
    if not decision_id or thread_id not in decision_id:
        raise ValueError("--decision-id must contain the selected thread ID")
    return {
        "schemaVersion": 2,
        "ok": True,
        "decision": "authorized_for_independent_holdout_evaluation",
        "confirmedBy": "workspace-user",
        "confirmationNote": user_message,
        "authorizationEvidence": {
            "kind": "codex-user-message",
            "threadId": thread_id,
            "decisionId": decision_id,
            "userMessageText": user_message,
            "userMessageSha256": hashlib.sha256(user_message.encode("utf-8")).hexdigest(),
        },
        "sourceRoot": binding["sourceRoot"],
        "scopeIncludesDescendants": False,
        "authorizedUses": REQUIRED_USES,
        "excludedUses": EXCLUDED_USES,
        "qualityConstraint": QUALITY_CONSTRAINT,
        "roleConstraint": ROLE_CONSTRAINT,
        "currentTrainingUse": "prohibited",
        "exactBatch": {
            "sequenceStart": binding["sequenceStart"],
            "sequenceEnd": binding["sequenceEnd"],
            "imageCount": binding["count"],
            "recordsSha256": binding["recordsSha256"],
        },
        "authorizedItemsSha256": binding["recordsSha256"],
        "authorizedItems": binding["records"],
        "inputs": {
            "generatedCandidateList": binding["candidateList"],
            "preauthorizationMachineAudit": binding["preauthorizationAudit"],
            "candidateWeights": binding["candidateWeights"],
            "candidateThresholdReport": binding["candidateThresholdReport"],
            "protectedHardNegativeRegistry": binding["protectedHardNegativeRegistry"],
        },
    }


def verify_authorization(path: Path) -> dict[str, Any]:
    authorization = read_json(path, "independent holdout authorization")
    evidence = authorization.get("authorizationEvidence")
    inputs = authorization.get("inputs")
    if not isinstance(evidence, dict) or not isinstance(inputs, dict):
        raise ValueError("authorization evidence or inputs are missing")
    candidate_list = inputs.get("generatedCandidateList")
    preaudit = inputs.get("preauthorizationMachineAudit")
    if not isinstance(candidate_list, dict) or not isinstance(preaudit, dict):
        raise ValueError("authorization exact-list source bindings are missing")
    candidate_list_path = require_bound_file(
        candidate_list.get("path"), candidate_list.get("sha256"), "generated candidate list"
    )
    preaudit_path = require_bound_file(
        preaudit.get("path"), preaudit.get("sha256"), "pre-authorization machine audit"
    )
    expected = build_authorization(
        candidate_list_path,
        preaudit_path,
        str(evidence.get("userMessageText") or ""),
        str(evidence.get("threadId") or ""),
        str(evidence.get("decisionId") or ""),
    )
    if authorization != expected:
        raise ValueError("independent holdout authorization deep replay drift")
    return {
        "ok": True,
        "decision": "exact_independent_holdout_authorization_verified",
        "authorizationSource": str(path),
        "authorizationSourceSha256": sha256_file(path),
        "sourceRoot": authorization["sourceRoot"],
        "imageCount": authorization["exactBatch"]["imageCount"],
        "authorizedItemsSha256": authorization["authorizedItemsSha256"],
        "currentTrainingUse": "prohibited",
    }


def validate_output_path(output_value: str, protected_inputs: list[Path]) -> Path:
    output = Path(output_value).absolute()
    if output.exists():
        raise ValueError(f"refusing to overwrite existing output: {output}")
    if not output.parent.is_dir():
        raise ValueError("output parent must be an existing directory")
    reject_linked_ancestors(output.parent, "output parent")
    output = output.parent.resolve(strict=True) / output.name
    if output in protected_inputs:
        raise ValueError("output cannot overwrite an input")
    return output


def write_atomic_exclusive(path: Path, value: dict[str, Any]) -> None:
    payload = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    staging = path.parent / f".{path.name}.staging-{os.getpid()}-{uuid.uuid4().hex}"
    try:
        with staging.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(staging, path)
        except FileExistsError as error:
            raise ValueError(f"refusing to overwrite existing output: {path}") from error
        except OSError as error:
            if path.exists():
                raise ValueError(f"refusing to overwrite existing output: {path}") from error
            raise ValueError(f"cannot atomically publish output: {path}: {error}") from error
    finally:
        try:
            staging.unlink()
        except FileNotFoundError:
            pass


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description=(
            "Inspect, create, or verify an exact-file schema-v2 authorization for "
            "an independent hard-negative holdout."
        )
    )
    parser.add_argument("--candidate-list")
    parser.add_argument("--preauthorization-audit")
    parser.add_argument("--inspect", action="store_true")
    parser.add_argument("--user-message")
    parser.add_argument("--thread-id")
    parser.add_argument("--decision-id")
    parser.add_argument("--output")
    parser.add_argument("--verify-authorization")
    args = parser.parse_args()
    try:
        if args.verify_authorization:
            if any(
                value
                for value in (
                    args.candidate_list,
                    args.preauthorization_audit,
                    args.inspect,
                    args.user_message,
                    args.thread_id,
                    args.decision_id,
                    args.output,
                )
            ):
                raise ValueError(
                    "--verify-authorization cannot be combined with creation arguments"
                )
            path = require_plain_file(
                args.verify_authorization, "independent holdout authorization"
            )
            result = verify_authorization(path)
        else:
            if not args.candidate_list or not args.preauthorization_audit:
                raise ValueError(
                    "--candidate-list and --preauthorization-audit are required"
                )
            candidate_list_path = require_plain_file(
                args.candidate_list, "generated candidate list"
            )
            preaudit_path = require_plain_file(
                args.preauthorization_audit, "pre-authorization machine audit"
            )
            binding = validate_sources(candidate_list_path, preaudit_path)
            confirmation = required_confirmation_text(
                Path(binding["sourceRoot"]),
                binding["count"],
                binding["sequenceStart"],
                binding["sequenceEnd"],
            )
            if args.inspect:
                if any(
                    value
                    for value in (
                        args.user_message,
                        args.thread_id,
                        args.decision_id,
                        args.output,
                    )
                ):
                    raise ValueError("--inspect cannot be combined with creation arguments")
                result = {
                    "ok": True,
                    "decision": "ready_for_exact_user_authorization",
                    "sourceRoot": binding["sourceRoot"],
                    "imageCount": binding["count"],
                    "sequenceStart": binding["sequenceStart"],
                    "sequenceEnd": binding["sequenceEnd"],
                    "authorizedItemsSha256": binding["recordsSha256"],
                    "requiredConfirmationText": confirmation,
                    "currentTrainingUse": "prohibited",
                }
            else:
                required = {
                    "--user-message": args.user_message,
                    "--thread-id": args.thread_id,
                    "--decision-id": args.decision_id,
                    "--output": args.output,
                }
                missing = [name for name, value in required.items() if not value]
                if missing:
                    raise ValueError(f"missing required arguments: {', '.join(missing)}")
                output = validate_output_path(
                    args.output, [candidate_list_path, preaudit_path]
                )
                authorization = build_authorization(
                    candidate_list_path,
                    preaudit_path,
                    args.user_message,
                    args.thread_id,
                    args.decision_id,
                )
                write_atomic_exclusive(output, authorization)
                result = verify_authorization(output)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
