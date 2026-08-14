#!/usr/bin/env python3
"""Finalize a hash-bound candidate7 original-resolution source-review shard."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {path}")
    return value


def object_array(value: Any, field: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"Expected object array: {field}")
    return value


def build_report(audit_path: Path, decisions_path: Path) -> dict[str, Any]:
    audit = load_object(audit_path)
    decisions = load_object(decisions_path)
    if audit.get("decision") != "machine_audit_ready_for_original_resolution_visual_review":
        raise ValueError("Machine audit is not ready")
    if decisions.get("decision") != "candidate7_original_resolution_source_review_decisions":
        raise ValueError("Decision manifest has an unsupported decision")
    audit_items = object_array(audit.get("items"), "audit.items")
    decision_items = object_array(decisions.get("items"), "decisions.items")
    audit_by_name = {str(item.get("fileName") or ""): item for item in audit_items}
    if len(audit_by_name) != len(audit_items):
        raise ValueError("Audit contains duplicate filenames")
    seen: set[str] = set()
    items: list[dict[str, Any]] = []
    valid_decisions = {"keep-for-complete-mask-rereview", "exclude-source"}
    for decision_item in decision_items:
        file_name = str(decision_item.get("fileName") or "")
        if not file_name or file_name in seen:
            raise ValueError(f"Missing or duplicate decision filename: {file_name}")
        seen.add(file_name)
        audit_item = audit_by_name.get(file_name)
        if audit_item is None:
            raise ValueError(f"Decision item is absent from audit: {file_name}")
        decision = decision_item.get("decision")
        if decision not in valid_decisions:
            raise ValueError(f"Unsupported source decision for {file_name}: {decision}")
        reason = str(decision_item.get("reason") or "").strip()
        if not reason:
            raise ValueError(f"Missing decision reason: {file_name}")
        fully_visible_nails = decision_item.get("fullyVisibleNails")
        if decision == "keep-for-complete-mask-rereview":
            if not isinstance(fully_visible_nails, int) or fully_visible_nails <= 0:
                raise ValueError(f"Kept item needs a positive fullyVisibleNails count: {file_name}")
        elif fully_visible_nails is not None:
            raise ValueError(f"Excluded item must use null fullyVisibleNails: {file_name}")
        image_path = Path(audit_item["imagePath"])
        annotation_path = Path(audit_item["annotationPath"])
        overlay_path = Path(audit_item["overlayPath"])
        crops_path = Path(audit_item["nailCropSheetPath"])
        if sha256_path(image_path) != audit_item["imageSha256"]:
            raise ValueError(f"Image drift: {file_name}")
        if sha256_path(annotation_path) != audit_item["annotationSha256"]:
            raise ValueError(f"Annotation drift: {file_name}")
        if sha256_path(overlay_path) != audit_item["overlaySha256"]:
            raise ValueError(f"Overlay drift: {file_name}")
        if sha256_path(crops_path) != audit_item["nailCropSheetSha256"]:
            raise ValueError(f"Nail crop evidence drift: {file_name}")
        items.append(
            {
                "fileName": file_name,
                "imagePath": audit_item["imagePath"],
                "imageSha256": audit_item["imageSha256"],
                "annotationPath": audit_item["annotationPath"],
                "annotationSha256": audit_item["annotationSha256"],
                "sourceGroup": audit_item["sourceGroup"],
                "width": audit_item["width"],
                "height": audit_item["height"],
                "legacyPolygonCount": len(audit_item["polygonResults"]),
                "machineStatus": audit_item["machineStatus"],
                "overlayPath": audit_item["overlayPath"],
                "overlaySha256": audit_item["overlaySha256"],
                "nailCropSheetPath": audit_item["nailCropSheetPath"],
                "nailCropSheetSha256": audit_item["nailCropSheetSha256"],
                "sourceDecision": decision,
                "fullyVisibleNails": fully_visible_nails,
                "reason": reason,
                "completeMaskReview": "pending" if decision == "keep-for-complete-mask-rereview" else "not-applicable-source-excluded",
                "trainingUse": "prohibited",
            }
        )
    expected_count = decisions.get("expectedItems")
    if expected_count != len(items):
        raise ValueError(f"Decision item count mismatch: expected {expected_count}, got {len(items)}")
    kept = [item for item in items if item["sourceDecision"] == "keep-for-complete-mask-rereview"]
    excluded = [item for item in items if item["sourceDecision"] == "exclude-source"]
    return {
        "schemaVersion": 1,
        "ok": True,
        "decision": "candidate7_source_review_shard_complete",
        "inputs": {
            "machineAudit": str(audit_path),
            "machineAuditSha256": sha256_path(audit_path),
            "machineAuditItemsSha256": audit.get("itemsSha256"),
            "decisions": str(decisions_path),
            "decisionsSha256": sha256_path(decisions_path),
        },
        "review": {
            "reviewer": decisions.get("reviewer"),
            "reviewedAt": decisions.get("reviewedAt"),
            "method": decisions.get("method"),
        },
        "policy": {
            "sourcePassDoesNotApproveLegacyMasks": True,
            "sourcePassDoesNotGrantTrainingUse": True,
            "completeMaskOriginalResolutionReviewRequired": True,
            "excludedSourcesRemainTrainingProhibited": True,
            "trainingUse": "prohibited",
        },
        "counts": {
            "reviewedImages": len(items),
            "keptForCompleteMaskRereview": len(kept),
            "excludedSources": len(excluded),
            "fullyVisibleNailsInKeptSources": sum(int(item["fullyVisibleNails"]) for item in kept),
            "keptMachineCleanImages": sum(item["machineStatus"].startswith("machine-clean") for item in kept),
            "keptMachineReworkImages": sum(item["machineStatus"] == "machine-rework-required" for item in kept),
        },
        "itemsSha256": canonical_sha256(items),
        "items": items,
        "errors": [],
    }


def build_corrected_report(base_report_path: Path, corrections_path: Path) -> dict[str, Any]:
    base = load_object(base_report_path)
    base_inputs = base.get("inputs", {})
    if "baseReport" in base_inputs:
        replayed_base = build_corrected_report(
            Path(base_inputs["baseReport"]), Path(base_inputs["corrections"])
        )
    else:
        replayed_base = build_report(
            Path(base_inputs["machineAudit"]), Path(base_inputs["decisions"])
        )
    if replayed_base != base:
        raise ValueError("Base source-review report does not match replayed evidence")

    corrections = load_object(corrections_path)
    if corrections.get("decision") != "candidate7_source_review_corrections":
        raise ValueError("Correction manifest has an unsupported decision")
    correction_items = object_array(corrections.get("items"), "corrections.items")
    if corrections.get("expectedItems") != len(correction_items):
        raise ValueError("Correction item count mismatch")

    items = json.loads(json.dumps(base.get("items"), ensure_ascii=False))
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise ValueError("Base report items are invalid")
    by_name = {str(item.get("fileName") or ""): item for item in items}
    if len(by_name) != len(items):
        raise ValueError("Base report contains duplicate filenames")
    seen: set[str] = set()
    valid_decisions = {"keep-for-complete-mask-rereview", "exclude-source"}
    for correction in correction_items:
        file_name = str(correction.get("fileName") or "")
        if not file_name or file_name in seen:
            raise ValueError(f"Missing or duplicate correction filename: {file_name}")
        seen.add(file_name)
        item = by_name.get(file_name)
        if item is None:
            raise ValueError(f"Correction item is absent from base report: {file_name}")
        if item.get("sourceDecision") != correction.get("expectedPreviousDecision"):
            raise ValueError(f"Previous decision mismatch: {file_name}")
        if item.get("fullyVisibleNails") != correction.get("expectedPreviousFullyVisibleNails"):
            raise ValueError(f"Previous fully-visible count mismatch: {file_name}")
        decision = correction.get("decision")
        if decision not in valid_decisions:
            raise ValueError(f"Unsupported corrected source decision: {file_name}")
        fully_visible_nails = correction.get("fullyVisibleNails")
        if decision == "keep-for-complete-mask-rereview":
            if not isinstance(fully_visible_nails, int) or fully_visible_nails <= 0:
                raise ValueError(f"Corrected kept item needs a positive count: {file_name}")
        elif fully_visible_nails is not None:
            raise ValueError(f"Corrected excluded item must use null count: {file_name}")
        reason = str(correction.get("reason") or "").strip()
        if not reason:
            raise ValueError(f"Missing correction reason: {file_name}")
        item["sourceDecision"] = decision
        item["fullyVisibleNails"] = fully_visible_nails
        item["reason"] = reason
        item["completeMaskReview"] = (
            "pending" if decision == "keep-for-complete-mask-rereview"
            else "not-applicable-source-excluded"
        )
        item["trainingUse"] = "prohibited"

    kept = [item for item in items if item["sourceDecision"] == "keep-for-complete-mask-rereview"]
    excluded = [item for item in items if item["sourceDecision"] == "exclude-source"]
    return {
        "schemaVersion": 1,
        "ok": True,
        "decision": "candidate7_source_review_shard_complete",
        "inputs": {
            "baseReport": str(base_report_path),
            "baseReportSha256": sha256_path(base_report_path),
            "corrections": str(corrections_path),
            "correctionsSha256": sha256_path(corrections_path),
            "machineAudit": base_inputs.get("machineAudit") or replayed_base["inputs"].get("machineAudit"),
            "machineAuditSha256": base_inputs.get("machineAuditSha256") or replayed_base["inputs"].get("machineAuditSha256"),
            "machineAuditItemsSha256": base_inputs.get("machineAuditItemsSha256") or replayed_base["inputs"].get("machineAuditItemsSha256"),
        },
        "review": {
            "reviewer": corrections.get("reviewer"),
            "reviewedAt": corrections.get("reviewedAt"),
            "method": corrections.get("method"),
        },
        "policy": base["policy"],
        "counts": {
            "reviewedImages": len(items),
            "keptForCompleteMaskRereview": len(kept),
            "excludedSources": len(excluded),
            "fullyVisibleNailsInKeptSources": sum(int(item["fullyVisibleNails"]) for item in kept),
            "keptMachineCleanImages": sum(item["machineStatus"].startswith("machine-clean") for item in kept),
            "keptMachineReworkImages": sum(item["machineStatus"] == "machine-rework-required" for item in kept),
        },
        "itemsSha256": canonical_sha256(items),
        "items": items,
        "errors": [],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--machine-audit")
    parser.add_argument("--decisions")
    parser.add_argument("--base-report")
    parser.add_argument("--corrections")
    parser.add_argument("--output")
    parser.add_argument("--verify-report")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.verify_report:
            report_path = Path(args.verify_report).resolve()
            existing = load_object(report_path)
            inputs = existing.get("inputs", {})
            if "baseReport" in inputs:
                current = build_corrected_report(
                    Path(inputs["baseReport"]), Path(inputs["corrections"])
                )
            else:
                current = build_report(Path(inputs["machineAudit"]), Path(inputs["decisions"]))
            if current != existing:
                raise ValueError("Source-review report does not match replayed evidence")
            print(json.dumps({"ok": True, "decision": "verified", "report": str(report_path)}, ensure_ascii=False))
            return 0
        if not args.output:
            raise ValueError("Generation requires --output")
        if args.base_report or args.corrections:
            if not args.base_report or not args.corrections:
                raise ValueError("Correction generation requires --base-report and --corrections")
            report = build_corrected_report(
                Path(args.base_report).resolve(), Path(args.corrections).resolve()
            )
        else:
            if not args.machine_audit or not args.decisions:
                raise ValueError("Generation requires --machine-audit and --decisions")
            report = build_report(Path(args.machine_audit).resolve(), Path(args.decisions).resolve())
        output = Path(args.output).resolve()
        if output.exists():
            raise ValueError(f"Refusing to overwrite output: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"ok": True, "decision": report["decision"], "output": str(output)}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(json.dumps({"ok": False, "decision": "error", "error": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
