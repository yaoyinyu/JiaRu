#!/usr/bin/env python3
"""Build a hash-bound authorization source for a frozen training batch.

The command converts a previously frozen exact authorization request into the
input contract consumed by ``record-training-hard-negative-authorization.py``.
New batches bind the project's standing commercial-resource authorization and
do not pause for another itemized user message.  Historical schema v1/v2 user
confirmations remain replayable.  The command never discovers files by scanning
a directory and never grants training eligibility: the resulting source only
permits the listed files to enter the formal review workflow while
``trainingUse`` remains prohibited.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
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
EXPECTED_COUNT = 160
EXPECTED_REQUEST_USES = [
    "commercial-model-training",
    "long-term-regression",
    "model-diagnostic-evaluation",
    "data-quality-review",
]
EXPECTED_EXCLUDED_USES = ["independent-release-test"]
QUALITY_CONSTRAINT = "authorization-does-not-relax-quality-gates"
ROLE_CONSTRAINT = "authorization-does-not-assign-train-validation-or-holdout-role"
CANDIDATE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{1,127}$")
REQUEST_V2_KEYS = {
    "schemaVersion",
    "ok",
    "status",
    "decision",
    "role",
    "trainingUse",
    "authorizationStatus",
    "candidateId",
    "sourceRoot",
    "scopeIncludesDescendants",
    "inputs",
    "summary",
    "requestedUses",
    "excludedUses",
    "qualityConstraint",
    "roleConstraint",
    "requestedItemsSha256",
    "requiredConfirmationText",
    "requestedRelativePaths",
    "requestedItems",
}
REQUEST_V3_KEYS = (REQUEST_V2_KEYS - {"requiredConfirmationText"})
STANDING_AUTHORIZATION_DECISION = (
    "standing_project_commercial_resource_authorization_granted"
)
STANDING_REQUEST_DECISION = (
    "standing_project_authorization_bound_pending_quality_review"
)
STANDING_AUTHORIZATION_STATUS = "standing-project-authorization-applied"
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


def require_plain_file(path_value: Any, expected_hash: Any, label: str) -> Path:
    path_input = Path(str(path_value or "")).absolute()
    expected = str(expected_hash or "")
    if not path_input.is_file() or not SHA256_PATTERN.fullmatch(expected):
        raise ValueError(f"{label} binding is invalid")
    reject_linked_ancestors(path_input, label)
    path = path_input.resolve(strict=True)
    if sha256_file(path) != expected:
        raise ValueError(f"{label} SHA-256 drift")
    return path


def validate_standing_authorization(path: Path) -> dict[str, Any]:
    authorization = read_json(path, "standing project authorization")
    scope = authorization.get("scope")
    role_restrictions = authorization.get("roleRestrictionsNotRelaxed")
    quality_gates = authorization.get("qualityGatesNotRelaxed")
    if (
        authorization.get("schemaVersion") != 1
        or authorization.get("decision") != STANDING_AUTHORIZATION_DECISION
        or authorization.get("authorizedBy") != "user"
        or not str(authorization.get("authorizationText") or "").strip()
        or not isinstance(scope, dict)
        or scope.get("projectScopedImageResources") != "commercial-use-permitted"
        or scope.get("localComputeResources")
        != "commercial-model-work-permitted"
        or scope.get("futureUserPlacedProjectResources")
        != "commercial-use-permitted-without-itemized-reauthorization"
        or scope.get("itemizedTrainingAuthorizationRequired") is not False
        or scope.get("trainingStartAuthorizationRequired") is not False
        or not isinstance(role_restrictions, list)
        or not {
            "validation-remains-calibration-only",
            "frozen-test-remains-training-prohibited",
            "consumed-holdout-remains-training-prohibited",
            "future-independent-holdout-must-be-unseen-and-source-isolated",
        }.issubset(set(role_restrictions))
        or not isinstance(quality_gates, list)
        or not {
            "original-resolution-source-review",
            "watermark-shortcut-ablation",
            "val30-threshold-calibration",
            "frozen-test100-positive-recognition",
            "new-unseen-independent-hard-negative-holdout",
            "three-variant-zero-false-positive",
            "completion-audit",
        }.issubset(set(quality_gates))
    ):
        raise ValueError("standing project authorization contract is invalid")
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "decision": authorization["decision"],
        "authorizedAt": authorization.get("authorizedAt"),
    }


def load_progress_module() -> Any:
    module_path = Path(__file__).with_name(
        "audit-training-hard-negative-generation-progress.py"
    )
    spec = importlib.util.spec_from_file_location(
        "audit_training_hard_negative_generation_progress",
        module_path,
    )
    if spec is None or spec.loader is None:
        raise ValueError("cannot load generation-progress verifier")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def normalize_relative_path(value: Any, number: int) -> str:
    relative = str(value or "").strip().replace("\\", "/")
    candidate = Path(relative)
    if (
        not relative
        or candidate.is_absolute()
        or len(candidate.parts) != 1
        or any(part in {"", ".", ".."} for part in candidate.parts)
    ):
        raise ValueError(
            f"requestedRelativePaths entry {number} must be a direct safe file name"
        )
    return relative


def expected_request_item(progress_item: dict[str, Any]) -> dict[str, Any]:
    return {
        "sequence": progress_item["sequence"],
        "relativePath": progress_item["expectedFileName"],
        "sha256": progress_item["sha256"],
        "dhash256": progress_item["dhash256"],
        "width": progress_item["width"],
        "height": progress_item["height"],
        "promptId": progress_item["promptId"],
        "promptFamily": progress_item["promptFamily"],
        "promptVariant": progress_item["promptVariant"],
    }


def build_required_confirmation_text(
    candidate_id: str,
    requested_file_count: int,
    requested_items_sha256: str,
) -> str:
    if not CANDIDATE_ID_PATTERN.fullmatch(candidate_id):
        raise ValueError("candidateId is invalid")
    if requested_file_count != EXPECTED_COUNT:
        raise ValueError("requested file count must be exactly 160")
    if not SHA256_PATTERN.fullmatch(requested_items_sha256):
        raise ValueError("requestedItemsSha256 is invalid")
    return (
        f"允许将 {candidate_id} 最终冻结的{requested_file_count}张精确文件清单"
        f"（requestedItemsSha256={requested_items_sha256}）用于商业模型训练、长期回归、"
        "模型诊断评估和数据质量审核；不用于独立发布测试；授权不放宽质量门。"
    )


def validate_request(
    request_path: Path,
    *,
    expected_user_message: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    request = read_json(request_path, "exact authorization request")
    schema_version = request.get("schemaVersion")
    if (
        schema_version not in {1, 2, 3}
        or request.get("ok") is not False
        or request.get("status") != "HOLD"
        or request.get("role") != "training-hard-negative-candidate"
        or request.get("trainingUse") != "prohibited"
        or request.get("scopeIncludesDescendants") is not False
        or request.get("qualityConstraint") != QUALITY_CONSTRAINT
        or request.get("roleConstraint") != ROLE_CONSTRAINT
        or request.get("requestedUses") != EXPECTED_REQUEST_USES
        or request.get("excludedUses") != EXPECTED_EXCLUDED_USES
    ):
        raise ValueError("exact authorization request contract is invalid")
    if schema_version in {1, 2} and (
        request.get("decision") != "awaiting_exact_user_confirmation"
        or request.get("authorizationStatus") != "pending-user-confirmation"
    ):
        raise ValueError("legacy exact authorization request contract is invalid")
    if schema_version == 3 and (
        request.get("decision") != STANDING_REQUEST_DECISION
        or request.get("authorizationStatus") != STANDING_AUTHORIZATION_STATUS
    ):
        raise ValueError("standing authorization request contract is invalid")
    if schema_version == 2 and set(request) != REQUEST_V2_KEYS:
        raise ValueError(
            "exact authorization request v2 fields are not exact: "
            f"missing={sorted(REQUEST_V2_KEYS - set(request))}, "
            f"extra={sorted(set(request) - REQUEST_V2_KEYS)}"
        )
    if schema_version == 3 and set(request) != REQUEST_V3_KEYS:
        raise ValueError(
            "exact authorization request v3 fields are not exact: "
            f"missing={sorted(REQUEST_V3_KEYS - set(request))}, "
            f"extra={sorted(set(request) - REQUEST_V3_KEYS)}"
        )

    required_text = str(request.get("requiredConfirmationText") or "")
    if schema_version in {1, 2} and not required_text:
        raise ValueError("requiredConfirmationText is missing")
    if schema_version == 1 and (
        expected_user_message is not None and expected_user_message != required_text
    ):
        raise ValueError("user message does not exactly match requiredConfirmationText")

    source_input = Path(str(request.get("sourceRoot") or "")).absolute()
    if not source_input.is_dir():
        raise ValueError("exact authorization request sourceRoot is missing")
    reject_linked_ancestors(source_input, "exact authorization request sourceRoot")
    source_root = source_input.resolve(strict=True)

    inputs = request.get("inputs")
    expected_input_keys = {
        "generationProgressReport",
        "generationPlan",
        "protectedHardNegativeRegistry",
        "itemsCurrentSha256",
    }
    if schema_version == 3:
        expected_input_keys.add("standingProjectAuthorization")
    if not isinstance(inputs, dict) or set(inputs) != expected_input_keys:
        raise ValueError("exact authorization request inputs are invalid")
    progress_binding = inputs.get("generationProgressReport")
    plan_binding = inputs.get("generationPlan")
    registry_binding = inputs.get("protectedHardNegativeRegistry")
    if not all(
        isinstance(value, dict)
        for value in (progress_binding, plan_binding, registry_binding)
    ):
        raise ValueError("exact authorization request file bindings are invalid")
    progress_path = require_plain_file(
        progress_binding.get("path"),
        progress_binding.get("sha256"),
        "generation progress report",
    )
    require_plain_file(
        plan_binding.get("path"),
        plan_binding.get("sha256"),
        "generation plan",
    )
    registry_path = require_plain_file(
        registry_binding.get("path"),
        registry_binding.get("sha256"),
        "protected hard-negative registry",
    )
    standing_binding = None
    if schema_version == 3:
        raw_standing_binding = inputs.get("standingProjectAuthorization")
        if not isinstance(raw_standing_binding, dict):
            raise ValueError("standing project authorization binding is missing")
        standing_path = require_plain_file(
            raw_standing_binding.get("path"),
            raw_standing_binding.get("sha256"),
            "standing project authorization",
        )
        standing_binding = validate_standing_authorization(standing_path)
        if raw_standing_binding != standing_binding:
            raise ValueError("standing project authorization metadata drift")

    progress_module = load_progress_module()
    progress_result = progress_module.verify_report(progress_path)
    progress = read_json(progress_path, "generation progress report")
    if (
        progress_result.get("ok") is not True
        or progress_result.get("decision")
        != "ready_to_request_exact_user_authorization"
        or progress.get("sourceRoot") != str(source_root)
        or progress.get("trainingUse") != "prohibited"
        or progress.get("authorizationStatus") != "missing"
        or progress.get("summary")
        != {
            "expected": EXPECTED_COUNT,
            "present": EXPECTED_COUNT,
            "missing": 0,
            "passed": EXPECTED_COUNT,
            "failed": 0,
            "unknown": 0,
        }
        or progress.get("itemsCurrentSha256") != inputs.get("itemsCurrentSha256")
    ):
        raise ValueError("generation progress report is not a complete clean pool")
    if progress.get("inputs", {}).get("generationPlan") != plan_binding:
        raise ValueError("authorization request generation-plan binding drift")
    if progress.get("inputs", {}).get("protectedHardNegativeRegistry") != registry_binding:
        raise ValueError("authorization request protected-registry binding drift")

    registry = read_json(registry_path, "protected hard-negative registry")
    expected_registry_binding = {
        "path": str(registry_path),
        "sha256": sha256_file(registry_path),
        "decision": registry.get("decision"),
        "entriesSha256": registry.get("entriesSha256"),
        "manifestCount": registry.get("summary", {}).get("manifestCount"),
        "trainingManifestCount": registry.get("summary", {}).get(
            "trainingManifestCount"
        ),
        "holdoutManifestCount": registry.get("summary", {}).get(
            "holdoutManifestCount"
        ),
    }
    if registry_binding != expected_registry_binding:
        raise ValueError("authorization request protected-registry metadata drift")

    raw_paths = request.get("requestedRelativePaths")
    raw_items = request.get("requestedItems")
    progress_items = progress.get("items")
    if (
        not isinstance(raw_paths, list)
        or not isinstance(raw_items, list)
        or not isinstance(progress_items, list)
        or len(raw_paths) != EXPECTED_COUNT
        or len(raw_items) != EXPECTED_COUNT
        or len(progress_items) != EXPECTED_COUNT
    ):
        raise ValueError("exact authorization request must bind exactly 160 items")
    relative_paths = [
        normalize_relative_path(value, number)
        for number, value in enumerate(raw_paths, start=1)
    ]
    if relative_paths != sorted(relative_paths, key=str.casefold):
        raise ValueError("requestedRelativePaths must be case-insensitively sorted")
    if len({value.casefold() for value in relative_paths}) != EXPECTED_COUNT:
        raise ValueError("requestedRelativePaths contains duplicates")

    expected_items = [expected_request_item(item) for item in progress_items]
    if raw_items != expected_items:
        raise ValueError("requestedItems differ from the deeply replayed progress report")
    if relative_paths != sorted(
        [str(item["relativePath"]) for item in expected_items],
        key=str.casefold,
    ):
        raise ValueError("requestedRelativePaths differ from requestedItems")
    if len({str(item["sha256"]) for item in raw_items}) != EXPECTED_COUNT:
        raise ValueError("requestedItems contains duplicate image SHA-256 values")
    requested_items_sha256 = canonical_sha256(raw_items)
    candidate_id: str | None = None
    if schema_version in {2, 3}:
        candidate_id = str(request.get("candidateId") or "")
        if not CANDIDATE_ID_PATTERN.fullmatch(candidate_id):
            raise ValueError("exact authorization request candidateId is invalid")
        if request.get("requestedItemsSha256") != requested_items_sha256:
            raise ValueError("exact authorization request requestedItemsSha256 drift")
        if schema_version == 2:
            expected_confirmation = build_required_confirmation_text(
                candidate_id,
                EXPECTED_COUNT,
                requested_items_sha256,
            )
            if required_text != expected_confirmation:
                raise ValueError("requiredConfirmationText does not match the v2 template")
            if expected_user_message is not None and expected_user_message != required_text:
                raise ValueError("user message does not exactly match requiredConfirmationText")
        elif expected_user_message is not None:
            raise ValueError("schema v3 does not accept an itemized user message")

    summary = request.get("summary")
    if summary != {
        "requestedFileCount": EXPECTED_COUNT,
        "machinePassed": EXPECTED_COUNT,
        "originalResolutionVisualReviewApproved": 0,
        "trainingApproved": 0,
    }:
        raise ValueError("exact authorization request summary drift")
    return request, {
        "requestPath": str(request_path),
        "requestSha256": sha256_file(request_path),
        "sourceRoot": str(source_root),
        "schemaVersion": schema_version,
        "candidateId": candidate_id,
        "requiredConfirmationText": required_text,
        "relativePaths": relative_paths,
        "relativePathsSha256": canonical_sha256(relative_paths),
        "requestedItemsSha256": requested_items_sha256,
        "progressReport": progress_binding,
        "generationPlan": plan_binding,
        "protectedHardNegativeRegistry": registry_binding,
        "itemsCurrentSha256": inputs["itemsCurrentSha256"],
        "standingProjectAuthorization": standing_binding,
    }


def build_authorization(
    request_path: Path,
    user_message: str | None = None,
    thread_id: str | None = None,
    decision_id: str | None = None,
) -> dict[str, Any]:
    request_preview = read_json(request_path, "exact authorization request")
    schema_version = int(request_preview.get("schemaVersion") or 0)
    if schema_version in {1, 2}:
        if not user_message or not thread_id or not decision_id:
            raise ValueError("legacy requests require user message, thread ID, and decision ID")
        if not UUID_PATTERN.fullmatch(thread_id):
            raise ValueError("--thread-id must be a lowercase UUID")
        if thread_id not in decision_id:
            raise ValueError("--decision-id must contain the selected thread ID")
        _, binding = validate_request(
            request_path,
            expected_user_message=user_message,
        )
        confirmed_by = "workspace-user"
        confirmation_note = user_message
        authorization_evidence = {
            "kind": (
                "operator-attested-codex-user-message"
                if schema_version == 2
                else "codex-user-message"
            ),
            "threadId": thread_id,
            "decisionId": decision_id,
            "userMessageText": user_message,
            "userMessageSha256": hashlib.sha256(
                user_message.encode("utf-8")
            ).hexdigest(),
        }
    elif schema_version == 3:
        if any(value is not None for value in (user_message, thread_id, decision_id)):
            raise ValueError("schema v3 does not accept itemized user confirmation arguments")
        request, binding = validate_request(request_path)
        standing_binding = binding.get("standingProjectAuthorization")
        if not isinstance(standing_binding, dict):
            raise ValueError("schema v3 standing authorization binding is missing")
        standing_path = require_plain_file(
            standing_binding.get("path"),
            standing_binding.get("sha256"),
            "standing project authorization",
        )
        standing = read_json(standing_path, "standing project authorization")
        confirmed_by = "standing-project-authorization"
        confirmation_note = str(standing["authorizationText"])
        authorization_evidence = {
            "kind": "standing-project-commercial-resource-authorization",
            **standing_binding,
            "candidateId": request["candidateId"],
            "requestedItemsSha256": binding["requestedItemsSha256"],
        }
    else:
        raise ValueError("unsupported exact authorization request schema")
    result = {
        "schemaVersion": schema_version,
        "ok": True,
        "decision": "authorized_for_training_hard_negative_review",
        "confirmedBy": confirmed_by,
        "confirmationNote": confirmation_note,
        "authorizationEvidence": authorization_evidence,
        "sourceRoot": binding["sourceRoot"],
        "scopeIncludesDescendants": False,
        "authorizedUses": EXPECTED_REQUEST_USES,
        "excludedUses": EXPECTED_EXCLUDED_USES,
        "qualityConstraint": QUALITY_CONSTRAINT,
        "roleConstraint": ROLE_CONSTRAINT,
        "authorizedRelativePaths": binding["relativePaths"],
        "authorizedRelativePathsSha256": binding["relativePathsSha256"],
        "inputs": {
            "authorizationRequest": {
                "path": binding["requestPath"],
                "sha256": binding["requestSha256"],
            },
            "generationProgressReport": binding["progressReport"],
            "generationPlan": binding["generationPlan"],
            "protectedHardNegativeRegistry": binding[
                "protectedHardNegativeRegistry"
            ],
            "itemsCurrentSha256": binding["itemsCurrentSha256"],
            "requestedItemsSha256": binding["requestedItemsSha256"],
        },
        "summary": {
            "authorizedFileCount": EXPECTED_COUNT,
            "formalReviewApproved": 0,
            "trainingApproved": 0,
        },
        "currentTrainingUse": "prohibited",
    }
    if schema_version in {2, 3}:
        result["candidateId"] = binding["candidateId"]
        result["requestedItemsSha256"] = binding["requestedItemsSha256"]
    if schema_version == 2:
        result["authorizationEvidence"]["attestationScope"] = (
            "operator-attested; deep replayable but not host-cryptographically-signed"
        )
    return result


def verify_authorization(path: Path) -> dict[str, Any]:
    authorization = read_json(path, "user authorization source")
    evidence = authorization.get("authorizationEvidence")
    inputs = authorization.get("inputs")
    if not isinstance(evidence, dict) or not isinstance(inputs, dict):
        raise ValueError("user authorization source evidence bindings are missing")
    request_binding = inputs.get("authorizationRequest")
    if not isinstance(request_binding, dict):
        raise ValueError("user authorization source request binding is missing")
    request_path = require_plain_file(
        request_binding.get("path"),
        request_binding.get("sha256"),
        "exact authorization request",
    )
    if authorization.get("schemaVersion") == 3:
        expected = build_authorization(request_path)
    else:
        expected = build_authorization(
            request_path,
            str(evidence.get("userMessageText") or ""),
            str(evidence.get("threadId") or ""),
            str(evidence.get("decisionId") or ""),
        )
    if authorization != expected:
        raise ValueError("user authorization source deep replay drift")
    return {
        "ok": True,
        "authorizationSource": str(path),
        "authorizationSourceSha256": sha256_file(path),
        "authorizationRequest": str(request_path),
        "authorizationRequestSha256": sha256_file(request_path),
        "authorizedFileCount": EXPECTED_COUNT,
        "authorizedRelativePathsSha256": authorization[
            "authorizedRelativePathsSha256"
        ],
        "currentTrainingUse": "prohibited",
    }


def validate_output_path(output_value: str, request_path: Path) -> Path:
    output = Path(output_value).absolute()
    if output.exists():
        raise ValueError(f"refusing to overwrite existing output: {output}")
    if not output.parent.is_dir():
        raise ValueError("output parent must be an existing directory")
    reject_linked_ancestors(output.parent, "output parent")
    output = output.parent.resolve(strict=True) / output.name
    if output == request_path:
        raise ValueError("output cannot overwrite the authorization request")
    return output


def write_atomic_exclusive(path: Path, value: dict[str, Any]) -> None:
    payload = (
        json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
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
    parser = argparse.ArgumentParser(
        description=(
            "Build or verify a hash-bound user authorization source for an exact "
            "160-image training hard-negative request."
        )
    )
    parser.add_argument("--authorization-request")
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
                    args.authorization_request,
                    args.user_message,
                    args.thread_id,
                    args.decision_id,
                    args.output,
                )
            ):
                raise ValueError(
                    "--verify-authorization cannot be combined with creation arguments"
                )
            path = Path(args.verify_authorization).absolute().resolve(strict=True)
            result = verify_authorization(path)
        else:
            request_input = Path(str(args.authorization_request or "")).absolute()
            if not request_input.is_file():
                raise ValueError("exact authorization request is missing")
            reject_linked_ancestors(request_input, "exact authorization request")
            request_path = request_input.resolve(strict=True)
            request = read_json(request_path, "exact authorization request")
            required = {
                "--authorization-request": args.authorization_request,
                "--output": args.output,
            }
            if request.get("schemaVersion") in {1, 2}:
                required.update({
                    "--user-message": args.user_message,
                    "--thread-id": args.thread_id,
                    "--decision-id": args.decision_id,
                })
            missing = [name for name, value in required.items() if not value]
            if missing:
                raise ValueError(f"missing required arguments: {', '.join(missing)}")
            output = validate_output_path(args.output, request_path)
            authorization = build_authorization(
                request_path,
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
