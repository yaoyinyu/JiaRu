#!/usr/bin/env python3
"""Atomically record and replay an exact positive-reinforcement authorization."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


AUTHORIZED_USES = [
    "commercial-model-training",
    "long-term-regression",
    "model-diagnostic-evaluation",
    "data-quality-audit",
]


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="Record an exact positive training authorization.")
    value.add_argument("--request")
    value.add_argument("--confirmation-text")
    value.add_argument("--confirmed-at")
    value.add_argument("--confirmation-source")
    value.add_argument("--output-dir")
    value.add_argument("--verify-authorization")
    return value


def read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Cannot read {label}: {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object for {label}: {path}")
    return value


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_file(value: str | None, label: str) -> Path:
    if not value:
        raise ValueError(f"Missing {label} path")
    path = Path(value).resolve()
    if not path.is_file():
        raise ValueError(f"Missing {label}: {path}")
    return path


def run_verifier(script_name: str, flag: str, report_path: Path) -> None:
    script_path = Path(__file__).resolve().parent / script_name
    result = subprocess.run(
        [sys.executable, str(script_path), flag, str(report_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        stdout = result.stdout.decode("utf-8", errors="replace").strip()
        detail = stderr or stdout or f"exit {result.returncode}"
        raise ValueError(f"Deep verification failed for {report_path}: {detail}")


def verify_request(request_path: Path) -> dict[str, Any]:
    request = read_object(request_path, "authorization request")
    if request.get("schemaVersion") != 1:
        raise ValueError("Authorization request schemaVersion must be 1")
    if request.get("ok") is not True or request.get("decision") != "exact_positive_training_authorization_required":
        raise ValueError("Authorization request is not ready for exact confirmation")
    if request.get("authorizationStatus") != "missing" or request.get("trainingUse") != "prohibited":
        raise ValueError("Authorization request role state is invalid")
    items = request.get("requestedItems")
    if not isinstance(items, list) or len(items) != 160 or any(not isinstance(item, dict) for item in items):
        raise ValueError("Authorization request must bind exactly 160 item objects")
    if canonical_sha256(items) != request.get("requestedItemsSha256"):
        raise ValueError("Authorization request item digest mismatch")
    inventory_value = request.get("inputs", {}).get("inventory")
    inventory_path = require_file(inventory_value, "candidate inventory")
    if sha256_path(inventory_path) != request.get("inputs", {}).get("inventorySha256"):
        raise ValueError("Authorization request inventory SHA-256 mismatch")
    run_verifier(
        "build-positive-reinforcement-candidate-inventory.py",
        "--verify-report",
        inventory_path,
    )
    run_verifier(
        "build-positive-reinforcement-authorization-request.py",
        "--verify-report",
        request_path,
    )
    return request


def build_record(
    request_path: Path,
    request: dict[str, Any],
    confirmation_text: str,
    confirmed_at: str,
    confirmation_source: str,
) -> dict[str, Any]:
    expected_text = request.get("authorizationText")
    if not isinstance(expected_text, str) or confirmation_text != expected_text:
        raise ValueError("Confirmation text does not exactly match the frozen authorization request")
    if not confirmed_at or not confirmation_source:
        raise ValueError("confirmed-at and confirmation-source are required")
    requested_items = request["requestedItems"]
    authorized_items = [
        {
            **item,
            "authorizationStatus": "confirmed",
            "authorizedUses": AUTHORIZED_USES,
            "trainingUse": "prohibited-until-complete-mask-review-and-training-input-audit",
        }
        for item in requested_items
    ]
    return {
        "schemaVersion": 1,
        "ok": True,
        "decision": "exact_positive_training_authorization_recorded",
        "requestId": request["requestId"],
        "inputs": {
            "authorizationRequest": str(request_path),
            "authorizationRequestSha256": sha256_path(request_path),
            "inventory": request["inputs"]["inventory"],
            "inventorySha256": request["inputs"]["inventorySha256"],
        },
        "authorization": {
            "status": "confirmed",
            "confirmedBy": "workspace-user",
            "confirmedAt": confirmed_at,
            "confirmationSource": confirmation_source,
            "exactConfirmationText": confirmation_text,
            "authorizedUses": AUTHORIZED_USES,
            "doesNotRelaxQualityGates": True,
        },
        "policy": {
            "authorizationDoesNotApproveMasks": True,
            "completeMaskOriginalResolutionReviewRequired": True,
            "polygonValidityAndZeroOverlapRequired": True,
            "sourceIsolationMustRemainIntact": True,
            "val30IsThresholdCalibrationOnly": True,
            "frozenTest100MustNotBeUsedForTuningOrTraining": True,
            "consumedHoldoutsRemainTrainingProhibited": True,
            "trainingInputAuditRequiredBeforeTraining": True,
        },
        "counts": {
            "authorizedImages": len(authorized_items),
            "authorizedSourceGroups": len({item["sourceGroup"] for item in authorized_items}),
            "authorizedVisibleNails": sum(int(item["fullyVisibleNails"]) for item in authorized_items),
        },
        "requestedItemsSha256": request["requestedItemsSha256"],
        "authorizedItemsSha256": canonical_sha256(authorized_items),
        "authorizationStatus": "confirmed",
        "trainingUse": "prohibited-until-complete-mask-review-and-training-input-audit",
        "authorizedItems": authorized_items,
        "errors": [],
    }


def verify_record(record_path: Path) -> dict[str, Any]:
    record = read_object(record_path, "authorization record")
    if record.get("schemaVersion") != 1 or record.get("ok") is not True:
        raise ValueError("Authorization record schema or status is invalid")
    if record.get("decision") != "exact_positive_training_authorization_recorded":
        raise ValueError("Authorization record decision is invalid")
    request_path = require_file(record.get("inputs", {}).get("authorizationRequest"), "authorization request")
    if sha256_path(request_path) != record.get("inputs", {}).get("authorizationRequestSha256"):
        raise ValueError("Authorization request bytes drifted after confirmation")
    request = verify_request(request_path)
    authorization = record.get("authorization")
    if not isinstance(authorization, dict) or authorization.get("status") != "confirmed":
        raise ValueError("Authorization confirmation is missing")
    rebuilt = build_record(
        request_path,
        request,
        str(authorization.get("exactConfirmationText", "")),
        str(authorization.get("confirmedAt", "")),
        str(authorization.get("confirmationSource", "")),
    )
    if rebuilt != record:
        raise ValueError("Authorization record does not match current replayed evidence")
    return record


def write_atomic(output_dir: Path, record: dict[str, Any]) -> Path:
    if output_dir.exists():
        raise ValueError(f"Output directory already exists: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}-", dir=output_dir.parent))
    try:
        record_path = staging / "authorization-record-A-v1.json"
        record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        verify_record(record_path)
        os.replace(staging, output_dir)
        return output_dir / record_path.name
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def main() -> int:
    args = parser().parse_args()
    try:
        if args.verify_authorization:
            record_path = require_file(args.verify_authorization, "authorization record")
            record = verify_record(record_path)
            print(
                json.dumps(
                    {
                        "ok": True,
                        "decision": "verified",
                        "record": str(record_path),
                        "authorizedImages": record["counts"]["authorizedImages"],
                    },
                    ensure_ascii=False,
                )
            )
            return 0
        request_path = require_file(args.request, "authorization request")
        request = verify_request(request_path)
        if args.confirmation_text is None or args.confirmed_at is None or args.confirmation_source is None:
            raise ValueError("confirmation-text, confirmed-at, and confirmation-source are required")
        record = build_record(
            request_path,
            request,
            args.confirmation_text,
            args.confirmed_at,
            args.confirmation_source,
        )
        if not args.output_dir:
            raise ValueError("output-dir is required")
        record_path = write_atomic(Path(args.output_dir).resolve(), record)
        print(
            json.dumps(
                {
                    "ok": True,
                    "decision": record["decision"],
                    "record": str(record_path),
                    "recordSha256": sha256_path(record_path),
                },
                ensure_ascii=False,
            )
        )
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"ok": False, "decision": "error", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
