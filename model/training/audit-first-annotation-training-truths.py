from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


TRUTH_NAME = re.compile(r"^training-truth-(\d+)-.*-final\.json$")
EXPECTED_DECISION = "approved_as_training_truth_candidate_pending_dataset_materialization"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sequence(path: Path) -> tuple[int, str]:
    match = TRUTH_NAME.match(path.name)
    return (int(match.group(1)) if match else -1, path.name)


def read_candidate(path: Path) -> tuple[dict[str, Any] | None, str | None, dict[str, Any] | None]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return None, f"{path.name}: unreadable JSON: {error}", None
    item = document.get("item", {})
    inputs = document.get("inputs", {})
    if document.get("ok") is False or document.get("decision") == "reject_training_truth_candidate":
        return None, None, {
            "reportName": path.name,
            "decision": document.get("decision"),
            "errors": document.get("errors", []),
        }
    if document.get("ok") is not True or document.get("decision") != EXPECTED_DECISION:
        return None, f"{path.name}: report has an unsupported state", None
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
        "sequence": sequence(path)[0],
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
    args = parser.parse_args()
    truth_dir = Path(args.truth_dir).resolve()
    output_path = Path(args.output).resolve()
    errors: list[str] = []
    candidates: list[dict[str, Any]] = []
    rejected_reports: list[dict[str, Any]] = []
    if not truth_dir.is_dir():
        errors.append("training truth directory is missing")
    else:
        paths = sorted(truth_dir.glob("training-truth-*-final.json"), key=sequence)
        if not paths:
            errors.append("training truth directory contains no finalized reports")
        for path in paths:
            candidate, error, rejected = read_candidate(path)
            if error:
                errors.append(error)
            elif candidate:
                candidates.append(candidate)
            elif rejected:
                rejected_reports.append(rejected)

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
        "decision": "approved_unique_training_truth_index" if not errors else "reject_training_truth_index",
        "inputs": {
            "truthDir": str(truth_dir),
            "reportPattern": "training-truth-*-final.json",
        },
        "policy": {
            "uniqueKey": "item.fileName",
            "canonicalSelection": "highest numeric training-truth sequence, then report filename",
            "redundantIdenticalReportsAreCountedOnce": True,
            "conflictingDuplicateReportsAreRejected": True,
            "datasetMaterializationAndSourceIsolationStillRequired": True,
            "trainingUse": "prohibited-until-materialization-audit",
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
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["ok"], **result["summary"]}, ensure_ascii=True))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
