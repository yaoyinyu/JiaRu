from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def collect_existing_files(value: Any) -> set[Path]:
    paths: set[Path] = set()
    if isinstance(value, dict):
        for child in value.values():
            paths.update(collect_existing_files(child))
    elif isinstance(value, list):
        for child in value:
            paths.update(collect_existing_files(child))
    elif isinstance(value, str) and value:
        try:
            candidate = Path(value).resolve()
        except OSError:
            return paths
        if candidate.is_file():
            paths.add(candidate)
    return paths


def aliases(left: Path, right: Path) -> bool:
    if left.resolve() == right.resolve():
        return True
    if left.exists() and right.exists():
        try:
            return os.path.samefile(left, right)
        except OSError:
            return False
    return False


def ensure_safe_output(output_path: Path, protected_paths: set[Path]) -> None:
    for protected in protected_paths:
        if aliases(output_path, protected):
            raise ValueError(f"output must not overwrite input evidence: {protected}")


def evidence_hashes(paths: set[Path]) -> dict[str, str]:
    return {str(path.resolve()): sha256_file(path) for path in paths if path.is_file()}


def assert_evidence_unchanged(expected: dict[str, str]) -> None:
    for raw_path, expected_hash in expected.items():
        path = Path(raw_path)
        if not path.is_file() or sha256_file(path) != expected_hash:
            raise ValueError(f"input evidence changed while building truth index: {path}")


def write_json_atomic(output_path: Path, value: dict[str, Any], protected_paths: set[Path]) -> None:
    ensure_safe_output(output_path, protected_paths)
    snapshot = evidence_hashes(protected_paths)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.tmp-", dir=output_path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        assert_evidence_unchanged(snapshot)
        ensure_safe_output(output_path, protected_paths)
        os.replace(temporary, output_path)
        assert_evidence_unchanged(snapshot)
    finally:
        if temporary.exists():
            temporary.unlink()


def sequence(path: Path, prefix: str) -> tuple[int, str]:
    match = re.match(rf"^{re.escape(prefix)}-(\d+)-.*-final\.json$", path.name)
    return (int(match.group(1)) if match else -1, path.name)


def truth_contract(truth_role: str) -> tuple[str, str, str, str]:
    if truth_role == "val":
        return (
            "validation",
            "validation",
            "approved_as_validation_truth_candidate_pending_dataset_materialization",
            "reject_val_truth_candidate",
        )
    if truth_role == "release-test":
        return (
            "release-test",
            "release_test",
            "approved_as_release_test_truth_candidate_pending_snapshot_freeze",
            "reject_release_test_truth_candidate",
        )
    return (
        "training",
        "training",
        "approved_as_training_truth_candidate_pending_dataset_materialization",
        "reject_train_truth_candidate",
    )


def verify_release_test_candidate(
    path: Path, document: dict[str, Any], item: dict[str, Any], inputs: dict[str, Any]
) -> str | None:
    if inputs.get("truthRole") != "release-test":
        return f"{path.name}: release-test report truthRole mismatch"
    if (
        item.get("annotationTruthStatus") != "approved-as-release-test-truth-candidate"
        or item.get("trainingUse") != "prohibited"
        or item.get("evaluationUse") != "prohibited-until-snapshot-freeze"
    ):
        return f"{path.name}: release-test item role/use state is not eligible"
    policy = document.get("policy", {})
    if (
        policy.get("snapshotFreezeAndSourceIsolationStillRequired") is not True
        or policy.get("trainingUse") != "prohibited"
        or policy.get("evaluationUse") != "prohibited-until-snapshot-freeze"
    ):
        return f"{path.name}: release-test policy does not preserve freeze/isolation gates"

    bindings = (
        ("visualReviewFinal", "visualReviewFinalSha256"),
        ("image", "imageSha256"),
        ("annotation", "annotationSha256"),
        ("roleManifest", "roleManifestSha256"),
    )
    resolved: dict[str, Path] = {}
    for path_key, hash_key in bindings:
        raw_path = inputs.get(path_key)
        expected_hash = inputs.get(hash_key)
        if not isinstance(raw_path, str) or not raw_path or not isinstance(expected_hash, str):
            return f"{path.name}: release-test report is missing {path_key} binding"
        bound_path = Path(raw_path).resolve()
        if not bound_path.is_file() or sha256_file(bound_path) != expected_hash:
            return f"{path.name}: bound {path_key} is missing or changed"
        resolved[path_key] = bound_path

    if inputs.get("imageSha256") != item.get("sha256"):
        return f"{path.name}: release-test image hash differs from item identity"
    try:
        role_manifest = json.loads(resolved["roleManifest"].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return f"{path.name}: release-test role manifest is unreadable: {error}"
    if (
        role_manifest.get("ok") is not True
        or role_manifest.get("decision") != "annotation_workspace_ready_candidate_only"
        or role_manifest.get("policy", {}).get("selectionMode") != "independent-release-test"
        or role_manifest.get("policy", {}).get("assignedRole") != "independent-release-test"
    ):
        return f"{path.name}: bound role manifest is not independent-release-test"
    matching_role_items = [
        candidate
        for candidate in role_manifest.get("items", [])
        if candidate.get("fileName") == item.get("fileName")
    ]
    if len(matching_role_items) != 1:
        return f"{path.name}: role manifest must contain exactly one matching image"
    role_item = matching_role_items[0]
    if (
        role_item.get("sha256") != item.get("sha256")
        or role_item.get("sourceGroup") != item.get("sourceGroup")
        or role_item.get("assignedRole") != "independent-release-test"
        or role_item.get("trainingUse") != "prohibited"
        or int(role_item.get("expectedFullyVisibleNails", -1))
        != int(item.get("completeMaskCount", -2))
    ):
        return f"{path.name}: role manifest identity/count/use differs from truth report"
    visual_flag = (
        "--repair-final"
        if inputs.get("visualReviewType") == "repair"
        else "--mask-review-final"
    )
    command = [
        sys.executable,
        str(Path(__file__).resolve().parent / "finalize-first-annotation-training-truth.py"),
        visual_flag,
        str(resolved["visualReviewFinal"]),
    ]
    if visual_flag == "--mask-review-final":
        command.extend(["--annotation", str(resolved["annotation"])])
    command.extend(
        [
            "--image",
            str(resolved["image"]),
            "--truth-role",
            "release-test",
            "--role-manifest",
            str(resolved["roleManifest"]),
        ]
    )
    with tempfile.TemporaryDirectory(prefix="release-truth-index-replay-") as directory:
        replay_path = Path(directory) / "replayed.json"
        completed = subprocess.run(
            [*command, "--output", str(replay_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0 or not replay_path.is_file():
            detail = completed.stderr.strip() or completed.stdout.strip()
            return f"{path.name}: release-test truth deep replay failed: {detail}"
        replayed = json.loads(replay_path.read_text(encoding="utf-8"))
        if canonical_json(replayed) != canonical_json(document):
            return f"{path.name}: release-test truth report differs from deep replay"
    return None


def read_candidate(path: Path, truth_role: str, prefix: str) -> tuple[dict[str, Any] | None, str | None, dict[str, Any] | None]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return None, f"{path.name}: unreadable JSON: {error}", None
    item = document.get("item", {})
    inputs = document.get("inputs", {})
    _, _, expected_decision, rejected_decision = truth_contract(truth_role)
    if document.get("ok") is False or document.get("decision") == rejected_decision:
        return None, None, {
            "reportName": path.name,
            "decision": document.get("decision"),
            "errors": document.get("errors", []),
        }
    if document.get("ok") is not True or document.get("decision") != expected_decision:
        return None, f"{path.name}: report has an unsupported state", None
    if truth_role == "release-test":
        release_error = verify_release_test_candidate(path, document, item, inputs)
        if release_error:
            return None, release_error, None
    required = {
        "fileName": item.get("fileName"),
        "sha256": item.get("sha256"),
        "sourceGroup": item.get("sourceGroup"),
        "completeMaskCount": item.get("completeMaskCount"),
        "annotationSha256": inputs.get("annotationSha256"),
    }
    missing = [key for key, value in required.items() if value in (None, "")]
    if missing:
        return None, f"{path.name}: missing required fields: {', '.join(missing)}", None
    return {
        "reportPath": str(path),
        "reportName": path.name,
        "reportSha256": sha256_file(path),
        "sequence": sequence(path, prefix)[0],
        "fileName": str(item["fileName"]),
        "imageSha256": str(item["sha256"]),
        "sourceGroup": str(item["sourceGroup"]),
        "completeMaskCount": int(item["completeMaskCount"]),
        "annotationPath": str(inputs.get("annotation", "")),
        "annotationSha256": str(inputs["annotationSha256"]),
    }, None, None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a unique, deterministic index of finalized first-annotation training truths."
    )
    parser.add_argument("--truth-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--truth-role", choices=("train", "val", "release-test"), default="train"
    )
    args = parser.parse_args()
    truth_dir = Path(args.truth_dir).resolve()
    output_path = Path(args.output).resolve()
    errors: list[str] = []
    candidates: list[dict[str, Any]] = []
    rejected_reports: list[dict[str, Any]] = []
    protected_paths: set[Path] = set()
    truth_label, decision_label, _, _ = truth_contract(args.truth_role)
    prefix = f"{truth_label}-truth"
    report_pattern = f"{prefix}-*-final.json"
    if not truth_dir.is_dir():
        errors.append(f"{truth_label} truth directory is missing")
    else:
        paths = sorted(truth_dir.glob(report_pattern), key=lambda path: sequence(path, prefix))
        if not paths:
            errors.append(f"{truth_label} truth directory contains no finalized reports")
        for path in paths:
            protected_paths.add(path.resolve())
            try:
                protected_paths.update(
                    collect_existing_files(json.loads(path.read_text(encoding="utf-8")))
                )
            except (OSError, json.JSONDecodeError):
                pass
            candidate, error, rejected = read_candidate(path, args.truth_role, prefix)
            if error:
                errors.append(error)
            elif candidate:
                candidates.append(candidate)
            elif rejected:
                rejected_reports.append(rejected)

    if not candidates:
        errors.append(f"{truth_label} truth index requires at least one approved candidate")

    by_file: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        by_file[candidate["fileName"]].append(candidate)

    canonical: list[dict[str, Any]] = []
    redundant: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    identity_fields = ("imageSha256", "sourceGroup", "completeMaskCount", "annotationSha256")
    for file_name in sorted(by_file):
        reports = sorted(by_file[file_name], key=lambda item: (item["sequence"], item["reportName"]))
        selected = reports[-1]
        canonical.append(selected)
        if len(reports) == 1:
            continue
        signatures = {tuple(report[field] for field in identity_fields) for report in reports}
        duplicate = {
            "fileName": file_name,
            "selectedReport": selected["reportName"],
            "reportNames": [report["reportName"] for report in reports],
        }
        if len(signatures) == 1:
            redundant.append(duplicate)
        else:
            conflicts.append(duplicate)
            errors.append(f"{file_name}: conflicting finalized truth reports")

    result = {
        "schemaVersion": 1,
        "ok": not errors,
        "decision": (
            f"approved_unique_{decision_label}_truth_index"
            if not errors
            else f"reject_{decision_label}_truth_index"
        ),
        "inputs": {
            "truthRole": args.truth_role,
            "truthDir": str(truth_dir),
            "reportPattern": report_pattern,
        },
        "policy": {
            "uniqueKey": "item.fileName",
            "canonicalSelection": f"highest numeric {prefix} sequence, then report filename",
            "redundantIdenticalReportsAreCountedOnce": True,
            "conflictingDuplicateReportsAreRejected": True,
            "datasetMaterializationAndSourceIsolationStillRequired": args.truth_role != "release-test",
            "snapshotFreezeAndSourceIsolationStillRequired": args.truth_role == "release-test",
            "trainingUse": (
                "prohibited"
                if args.truth_role in {"val", "release-test"}
                else "prohibited-until-materialization-audit"
            ),
            "validationUse": "prohibited-until-materialization-audit" if args.truth_role == "val" else None,
            "evaluationUse": (
                "prohibited-until-snapshot-freeze"
                if args.truth_role == "release-test"
                else None
            ),
        },
        "summary": {
            "approvedReportCount": len(candidates),
            "rejectedReportCount": len(rejected_reports),
            "uniqueImageCount": len(canonical),
            "completeMaskCount": sum(item["completeMaskCount"] for item in canonical),
            "redundantReportCount": sum(len(item["reportNames"]) - 1 for item in redundant),
            "redundantImageCount": len(redundant),
            "conflictingImageCount": len(conflicts),
        },
        "canonicalTruths": canonical,
        "rejectedReports": rejected_reports,
        "redundantReports": redundant,
        "conflicts": conflicts,
        "errors": errors,
    }
    try:
        write_json_atomic(output_path, result, protected_paths)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
    print(json.dumps({"ok": result["ok"], **result["summary"]}, ensure_ascii=True))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
