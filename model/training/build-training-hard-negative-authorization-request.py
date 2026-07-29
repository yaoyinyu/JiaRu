#!/usr/bin/env python3
"""Build or verify an exact authorization request for a frozen training pool.

This command is deliberately pre-authorization.  It freezes the exact files
from a deeply verified 160-item generation-progress report, but it never grants
training eligibility or replaces the user's explicit confirmation.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any


EXPECTED_COUNT = 160
CANDIDATE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{1,127}$")


def load_module(file_name: str, module_name: str) -> Any:
    module_path = Path(__file__).with_name(file_name)
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PROGRESS = load_module(
    "audit-training-hard-negative-generation-progress.py",
    "jiaru_training_hard_negative_generation_progress",
)
AUTHORIZATION = load_module(
    "build-training-hard-negative-user-authorization.py",
    "jiaru_training_hard_negative_user_authorization",
)


def validate_output_path(output_value: str, source_root: Path) -> Path:
    output = Path(output_value).absolute()
    if output.exists():
        raise ValueError(f"refuse to overwrite existing request: {output}")
    if not output.parent.is_dir():
        raise ValueError("output parent must be an existing directory")
    AUTHORIZATION.reject_linked_ancestors(output.parent, "output parent")
    output = output.parent.resolve(strict=True) / output.name
    if output.is_relative_to(source_root):
        raise ValueError("authorization request cannot be stored inside the source pool")
    return output


def write_json_atomic_exclusive(path: Path, value: dict[str, Any]) -> None:
    payload = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    temporary = path.with_name(
        f".{path.name}.staging-{os.getpid()}-{uuid.uuid4().hex}"
    )
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as error:
            raise ValueError(f"refuse to overwrite existing request: {path}") from error
        except OSError as error:
            if path.exists():
                raise ValueError(
                    f"refuse to overwrite existing request: {path}"
                ) from error
            raise ValueError(
                f"cannot atomically publish authorization request: {path}: {error}"
            ) from error
    finally:
        temporary.unlink(missing_ok=True)


def build_request(progress_path: Path, candidate_id: str) -> dict[str, Any]:
    if not CANDIDATE_ID_PATTERN.fullmatch(candidate_id):
        raise ValueError(
            "candidate id must match ^[a-z0-9][a-z0-9._-]{1,127}$"
        )
    PROGRESS.verify_report(progress_path)
    progress = PROGRESS.read_json(progress_path, "generation progress report")
    summary = progress.get("summary")
    if (
        progress.get("ok") is not True
        or progress.get("status") != "READY"
        or progress.get("decision")
        != "ready_to_request_exact_user_authorization"
        or progress.get("trainingUse") != "prohibited"
        or progress.get("authorizationStatus") != "missing"
        or not isinstance(summary, dict)
        or summary.get("expected") != EXPECTED_COUNT
        or summary.get("present") != EXPECTED_COUNT
        or summary.get("passed") != EXPECTED_COUNT
        or summary.get("missing") != 0
        or summary.get("failed") != 0
        or summary.get("unknown") != 0
    ):
        raise ValueError("generation progress is not ready for an exact request")

    source_root = Path(str(progress.get("sourceRoot") or "")).resolve(strict=True)
    inputs = progress.get("inputs")
    if not isinstance(inputs, dict):
        raise ValueError("generation progress inputs are invalid")
    plan_binding = inputs.get("generationPlan")
    registry_binding = inputs.get("protectedHardNegativeRegistry")
    if not isinstance(plan_binding, dict) or not isinstance(registry_binding, dict):
        raise ValueError("generation progress bindings are invalid")

    items = progress.get("items")
    if not isinstance(items, list) or len(items) != EXPECTED_COUNT:
        raise ValueError("generation progress must contain exactly 160 items")
    requested_items = [AUTHORIZATION.expected_request_item(item) for item in items]
    requested_items_sha256 = AUTHORIZATION.canonical_sha256(requested_items)
    confirmation = AUTHORIZATION.build_required_confirmation_text(
        candidate_id,
        EXPECTED_COUNT,
        requested_items_sha256,
    )
    return {
        "schemaVersion": 2,
        "ok": False,
        "status": "HOLD",
        "decision": "awaiting_exact_user_confirmation",
        "role": "training-hard-negative-candidate",
        "trainingUse": "prohibited",
        "authorizationStatus": "pending-user-confirmation",
        "candidateId": candidate_id,
        "sourceRoot": str(source_root),
        "scopeIncludesDescendants": False,
        "inputs": {
            "generationProgressReport": {
                "path": str(progress_path),
                "sha256": AUTHORIZATION.sha256_file(progress_path),
            },
            "generationPlan": plan_binding,
            "protectedHardNegativeRegistry": registry_binding,
            "itemsCurrentSha256": progress["itemsCurrentSha256"],
        },
        "summary": {
            "requestedFileCount": EXPECTED_COUNT,
            "machinePassed": EXPECTED_COUNT,
            "originalResolutionVisualReviewApproved": 0,
            "trainingApproved": 0,
        },
        "requestedUses": AUTHORIZATION.EXPECTED_REQUEST_USES,
        "excludedUses": AUTHORIZATION.EXPECTED_EXCLUDED_USES,
        "qualityConstraint": AUTHORIZATION.QUALITY_CONSTRAINT,
        "roleConstraint": AUTHORIZATION.ROLE_CONSTRAINT,
        "requestedItemsSha256": requested_items_sha256,
        "requiredConfirmationText": confirmation,
        "requestedRelativePaths": [item["relativePath"] for item in requested_items],
        "requestedItems": requested_items,
    }


def verify_request(path: Path) -> dict[str, Any]:
    request, binding = AUTHORIZATION.validate_request(path)
    return {
        "ok": True,
        "request": str(path),
        "requestSha256": AUTHORIZATION.sha256_file(path),
        "schemaVersion": request["schemaVersion"],
        "candidateId": request.get("candidateId"),
        "decision": request["decision"],
        "trainingUse": request["trainingUse"],
        "authorizationStatus": request["authorizationStatus"],
        "requestedFileCount": request["summary"]["requestedFileCount"],
        "requestedItemsSha256": binding["requestedItemsSha256"],
        "requiredConfirmationText": request["requiredConfirmationText"],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generation-progress")
    parser.add_argument("--candidate-id")
    parser.add_argument("--output")
    parser.add_argument("--verify-request")
    args = parser.parse_args()
    if args.verify_request:
        if args.generation_progress or args.candidate_id or args.output:
            parser.error("--verify-request cannot be combined with build arguments")
    elif not all((args.generation_progress, args.candidate_id, args.output)):
        parser.error(
            "build mode requires --generation-progress, --candidate-id, and --output"
        )
    return args


def main() -> int:
    args = parse_args()
    try:
        if args.verify_request:
            result = verify_request(Path(args.verify_request).resolve(strict=True))
        else:
            progress_path = Path(args.generation_progress).resolve(strict=True)
            candidate_id = str(args.candidate_id).strip()
            request = build_request(progress_path, candidate_id)
            source_root = Path(request["sourceRoot"]).resolve(strict=True)
            output_path = validate_output_path(args.output, source_root)
            write_json_atomic_exclusive(output_path, request)
            result = verify_request(output_path.resolve(strict=True))
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, RuntimeError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
