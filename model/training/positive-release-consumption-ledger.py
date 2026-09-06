#!/usr/bin/env python3
"""Atomically claim and verify one-use positive release holdout consumption.

The ledger is created before any image is read. A retry is allowed only when
the previous attempt was explicitly aborted before the image-read event.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


DECISION = "positive_release_holdout_one_use_ledger"
PURPOSE = "positive-recognition-release-evaluation"
EVENTS_BY_STATE = {
    "claimed": ["claimed"],
    "aborted-no-data-read": ["claimed", "aborted-no-data-read"],
    "image-read-started": ["claimed", "image-read-started"],
    "prediction-started": ["claimed", "image-read-started", "prediction-started"],
    "completed": ["claimed", "image-read-started", "prediction-started", "completed"],
}


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_object(path: Path, label: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def require_file(path: Path, label: str) -> Path:
    resolved = path.resolve()
    if not resolved.is_file():
        raise ValueError(f"{label} is missing: {resolved}")
    return resolved


def validate_release_identity(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"core", "coreSha256", "manifestSha256"}:
        raise ValueError("releaseIdentity must contain exactly core, coreSha256 and manifestSha256")
    core = value.get("core")
    if not isinstance(core, dict) or canonical_sha256(core) != value.get("coreSha256"):
        raise ValueError("releaseIdentity core hash is invalid")
    if not isinstance(value.get("manifestSha256"), str) or len(value["manifestSha256"]) != 64:
        raise ValueError("releaseIdentity manifestSha256 is invalid")
    return value


def load_identity_document(path: Path) -> dict[str, Any]:
    document = read_object(require_file(path, "release identity document"), "release identity document")
    return validate_release_identity(document.get("releaseIdentity", document))


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def event(sequence: int, event_type: str, **extra: Any) -> dict[str, Any]:
    return {"sequence": sequence, "type": event_type, "at": now(), **extra}


def write_new_exclusive(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise


def atomic_replace(path: Path, document: dict[str, Any]) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".next", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def transition_lock(ledger_path: Path) -> Iterator[None]:
    lock_path = ledger_path.with_name(f".{ledger_path.name}.lock")
    descriptor = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    try:
        yield
    finally:
        lock_path.unlink(missing_ok=True)


def expected_snapshot(path: Path) -> dict[str, str]:
    resolved = require_file(path, "positive release snapshot")
    document = read_object(resolved, "positive release snapshot")
    items = document.get("items")
    if document.get("trainingUse") != "prohibited" or not isinstance(items, list):
        raise ValueError("positive release snapshot must be training-prohibited and contain items")
    items_sha = canonical_sha256(items)
    if items_sha != document.get("itemsSha256"):
        raise ValueError("positive release snapshot items hash is invalid")
    return {"path": str(resolved), "sha256": sha256_file(resolved), "itemsSha256": items_sha}


def expected_runtime_lock(path: Path, identity: dict[str, Any]) -> dict[str, str]:
    resolved = require_file(path, "runtime selection lock")
    digest = sha256_file(resolved)
    if identity["core"].get("runtimeSelectionLockSha256") != digest:
        raise ValueError("runtime selection lock does not match releaseIdentity")
    return {"path": str(resolved), "sha256": digest}


def validate_attempt(attempt: Any, number: int, *, final: bool) -> None:
    if not isinstance(attempt, dict) or set(attempt) != {"attempt", "runId", "state", "events", "artifactIndex"}:
        raise ValueError(f"attempt {number} schema is invalid")
    if attempt.get("attempt") != number or not isinstance(attempt.get("runId"), str):
        raise ValueError(f"attempt {number} identity is invalid")
    try:
        uuid.UUID(attempt["runId"])
    except (ValueError, AttributeError):
        raise ValueError(f"attempt {number} runId is invalid") from None
    state = attempt.get("state")
    if state not in EVENTS_BY_STATE:
        raise ValueError(f"attempt {number} state is invalid")
    events = attempt.get("events")
    expected_types = EVENTS_BY_STATE[state]
    if not isinstance(events, list) or [item.get("type") if isinstance(item, dict) else None for item in events] != expected_types:
        raise ValueError(f"attempt {number} event sequence is invalid")
    for index, item in enumerate(events, start=1):
        if set(item) - {"sequence", "type", "at", "reason"} or item.get("sequence") != index or not item.get("at"):
            raise ValueError(f"attempt {number} event {index} is invalid")
    artifact = attempt.get("artifactIndex")
    if state == "completed":
        if not isinstance(artifact, dict) or set(artifact) != {"path", "sha256"}:
            raise ValueError(f"attempt {number} artifact index binding is invalid")
        artifact_path = require_file(Path(str(artifact.get("path", ""))), "prediction artifact index")
        if sha256_file(artifact_path) != artifact.get("sha256"):
            raise ValueError("prediction artifact index has drifted")
    elif artifact is not None:
        raise ValueError(f"attempt {number} cannot bind artifacts before completion")
    if not final and state != "aborted-no-data-read":
        raise ValueError("only a no-data-read abort may precede a retry")


def verify_ledger(path: Path, *, require_completed: bool = True) -> dict[str, Any]:
    document = read_object(require_file(path, "positive release consumption ledger"), "positive release consumption ledger")
    if set(document) != {"schemaVersion", "decision", "purpose", "releaseIdentity", "snapshot", "runtimeSelectionLock", "attempts"}:
        raise ValueError("positive release consumption ledger schema is invalid")
    if document.get("schemaVersion") != 1 or document.get("decision") != DECISION or document.get("purpose") != PURPOSE:
        raise ValueError("positive release consumption ledger contract is invalid")
    identity = validate_release_identity(document.get("releaseIdentity"))
    snapshot = document.get("snapshot")
    if not isinstance(snapshot, dict) or snapshot != expected_snapshot(Path(str(snapshot.get("path", "")))):
        raise ValueError("positive release snapshot binding has drifted")
    runtime_lock = document.get("runtimeSelectionLock")
    if not isinstance(runtime_lock, dict) or runtime_lock != expected_runtime_lock(Path(str(runtime_lock.get("path", ""))), identity):
        raise ValueError("runtime selection lock binding has drifted")
    attempts = document.get("attempts")
    if not isinstance(attempts, list) or not attempts:
        raise ValueError("positive release consumption attempts are missing")
    if len({attempt.get("runId") for attempt in attempts if isinstance(attempt, dict)}) != len(attempts):
        raise ValueError("positive release consumption runId values must be unique")
    for index, attempt in enumerate(attempts, start=1):
        validate_attempt(attempt, index, final=index == len(attempts))
    if require_completed and attempts[-1].get("state") != "completed":
        raise ValueError("positive release holdout consumption is not completed")
    return document


def claim(ledger_path: Path, identity_path: Path, snapshot_path: Path, runtime_lock_path: Path) -> str:
    identity = load_identity_document(identity_path)
    base = {
        "schemaVersion": 1,
        "decision": DECISION,
        "purpose": PURPOSE,
        "releaseIdentity": identity,
        "snapshot": expected_snapshot(snapshot_path),
        "runtimeSelectionLock": expected_runtime_lock(runtime_lock_path, identity),
    }
    run_id = str(uuid.uuid4())
    attempt = {"attempt": 1, "runId": run_id, "state": "claimed", "events": [event(1, "claimed")], "artifactIndex": None}
    if not ledger_path.exists():
        write_new_exclusive(ledger_path, {**base, "attempts": [attempt]})
        return run_id
    with transition_lock(ledger_path):
        document = verify_ledger(ledger_path, require_completed=False)
        for key, value in base.items():
            if document.get(key) != value:
                raise ValueError(f"existing ledger differs at {key}")
        attempts = document["attempts"]
        if attempts[-1].get("state") != "aborted-no-data-read":
            raise ValueError("holdout was already claimed or consumed; retry is forbidden")
        attempt["attempt"] = len(attempts) + 1
        attempts.append(attempt)
        atomic_replace(ledger_path, document)
    return run_id


def transition(ledger_path: Path, run_id: str, action: str, *, artifact_index: Path | None = None, reason: str | None = None) -> dict[str, Any]:
    mapping = {
        "mark-read": ("claimed", "image-read-started"),
        "mark-prediction": ("image-read-started", "prediction-started"),
        "complete": ("prediction-started", "completed"),
        "abort-no-data-read": ("claimed", "aborted-no-data-read"),
    }
    expected_state, next_state = mapping[action]
    with transition_lock(ledger_path):
        document = verify_ledger(ledger_path, require_completed=False)
        attempt = document["attempts"][-1]
        if attempt.get("runId") != run_id or attempt.get("state") != expected_state:
            raise ValueError("ledger transition does not match the active attempt")
        extra = {"reason": reason} if action == "abort-no-data-read" else {}
        attempt["events"].append(event(len(attempt["events"]) + 1, next_state, **extra))
        attempt["state"] = next_state
        if action == "complete":
            resolved = require_file(artifact_index or Path(""), "prediction artifact index")
            attempt["artifactIndex"] = {"path": str(resolved), "sha256": sha256_file(resolved)}
        atomic_replace(ledger_path, document)
    return document


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage a one-use positive release holdout ledger")
    parser.add_argument("--action", required=True, choices=("claim", "mark-read", "mark-prediction", "complete", "abort-no-data-read", "verify"))
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--release-identity")
    parser.add_argument("--snapshot-manifest")
    parser.add_argument("--runtime-selection-lock")
    parser.add_argument("--run-id")
    parser.add_argument("--artifact-index")
    parser.add_argument("--reason")
    args = parser.parse_args()
    try:
        ledger_path = Path(args.ledger).resolve()
        if args.action == "claim":
            if not all((args.release_identity, args.snapshot_manifest, args.runtime_selection_lock)):
                raise ValueError("claim requires release identity, snapshot manifest and runtime selection lock")
            run_id = claim(ledger_path, Path(args.release_identity), Path(args.snapshot_manifest), Path(args.runtime_selection_lock))
            result = {"ok": True, "state": "claimed", "runId": run_id, "ledger": str(ledger_path)}
        elif args.action == "verify":
            document = verify_ledger(ledger_path)
            result = {"ok": True, "state": document["attempts"][-1]["state"], "attempts": len(document["attempts"]), "ledger": str(ledger_path), "sha256": sha256_file(ledger_path)}
        else:
            if not args.run_id:
                raise ValueError(f"{args.action} requires --run-id")
            document = transition(
                ledger_path,
                args.run_id,
                args.action,
                artifact_index=Path(args.artifact_index) if args.artifact_index else None,
                reason=args.reason,
            )
            result = {"ok": True, "state": document["attempts"][-1]["state"], "runId": args.run_id, "ledger": str(ledger_path)}
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as error:  # noqa: BLE001
        print(f"ERROR: {error}", file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
