from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any


VALID_STATUSES = {"pass", "rework", "exclude"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Finalize one original-resolution first-annotation mask review shard without granting training truth."
    )
    parser.add_argument("--review-workspace", required=True)
    parser.add_argument("--shard-index", required=True, type=int)
    parser.add_argument("--decisions", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    workspace_path = Path(args.review_workspace).resolve()
    decisions_path = Path(args.decisions).resolve()
    output_path = Path(args.output).resolve()
    workspace = read_json(workspace_path)
    decisions = read_json(decisions_path)
    errors: list[str] = []
    if workspace.get("ok") is not True or workspace.get("decision") != "first_annotation_mask_review_workspace_ready_original_resolution_review_required":
        errors.append("a passing first-annotation mask review workspace is required")
    shard = next((item for item in workspace.get("shards", []) if int(item.get("index", -1)) == args.shard_index), None)
    if shard is None:
        errors.append(f"unknown shard index: {args.shard_index}")
        shard_path = Path("missing")
    else:
        shard_path = Path(str(shard.get("path", ""))).resolve()
        if not shard_path.is_file() or sha256_file(shard_path) != shard.get("sha256"):
            errors.append("bound review shard is missing or changed")
    if decisions.get("schemaVersion") != 1:
        errors.append("unsupported decisions schemaVersion")
    if decisions.get("reviewWorkspaceSha256") != sha256_file(workspace_path):
        errors.append("decisions do not bind the current review workspace")
    if decisions.get("shardIndex") != args.shard_index:
        errors.append("decisions shard index differs from the requested shard")
    if shard is not None and decisions.get("shardSha256") != shard.get("sha256"):
        errors.append("decisions do not bind the current shard CSV")

    pages = [page for page in workspace.get("pages", []) if int(page.get("shardIndex", -1)) == args.shard_index]
    expected_page_hashes = [str(page.get("sha256", "")) for page in pages]
    acknowledged_page_hashes = decisions.get("reviewedPageSha256s", [])
    if acknowledged_page_hashes != expected_page_hashes:
        errors.append("all rendered review pages and hashes must be acknowledged in order")
    for page in pages:
        page_path = Path(str(page.get("path", ""))).resolve()
        if not page_path.is_file() or sha256_file(page_path) != page.get("sha256"):
            errors.append(f"review page is missing or changed: {page_path}")

    shard_rows: list[dict[str, str]] = []
    if shard_path.is_file():
        with shard_path.open("r", encoding="utf-8-sig", newline="") as source:
            shard_rows = list(csv.DictReader(source))
    row_by_file = {row["fileName"]: row for row in shard_rows}
    decision_items = decisions.get("items", [])
    decision_by_file: dict[str, dict[str, Any]] = {}
    for item in decision_items:
        file_name = str(item.get("fileName", ""))
        if not file_name or file_name in decision_by_file:
            errors.append(f"duplicate or empty decision fileName: {file_name}")
            continue
        decision_by_file[file_name] = item
    if set(decision_by_file) != set(row_by_file):
        errors.append("decisions must exactly cover the bound review shard")

    reviewed: list[dict[str, Any]] = []
    for file_name, row in row_by_file.items():
        item = decision_by_file.get(file_name)
        if item is None:
            continue
        status = str(item.get("reviewStatus", ""))
        issue_codes = item.get("issueCodes", [])
        final_count = item.get("finalCompleteMaskCount")
        if item.get("sha256") != row.get("sha256") or item.get("sourceGroup") != row.get("sourceGroup"):
            errors.append(f"decision identity differs from shard: {file_name}")
        if status not in VALID_STATUSES:
            errors.append(f"invalid reviewStatus for {file_name}: {status}")
        if not isinstance(issue_codes, list) or any(not isinstance(code, str) or not code for code in issue_codes):
            errors.append(f"issueCodes must be a list of non-empty strings: {file_name}")
            issue_codes = []
        expected_count = int(row["expectedFullyVisibleNails"])
        candidate_count = int(row["candidateCount"])
        if status == "pass":
            if final_count != expected_count or candidate_count != expected_count:
                errors.append(f"pass requires candidate and final counts to equal expected: {file_name}")
            if issue_codes:
                errors.append(f"pass cannot retain issue codes: {file_name}")
        elif status == "rework":
            if not issue_codes:
                errors.append(f"rework requires issue codes: {file_name}")
            if final_count not in (None, 0):
                errors.append(f"rework finalCompleteMaskCount must be null or zero: {file_name}")
        elif status == "exclude":
            if not issue_codes:
                errors.append(f"exclude requires issue codes: {file_name}")
            if final_count not in (None, 0):
                errors.append(f"exclude finalCompleteMaskCount must be null or zero: {file_name}")
        reviewed.append({
            "fileName": file_name,
            "sha256": row["sha256"],
            "sourceGroup": row["sourceGroup"],
            "expectedFullyVisibleNails": expected_count,
            "candidateCount": candidate_count,
            "reviewStatus": status,
            "finalCompleteMaskCount": final_count,
            "issueCodes": issue_codes,
            "note": str(item.get("note", "")),
            "trainingUse": "prohibited",
            "annotationTruthStatus": "reviewed-candidate-not-final-truth" if status == "pass" else status,
        })
    if errors:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps({"ok": False, "errors": errors}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise SystemExit(1)

    counts = {status: sum(item["reviewStatus"] == status for item in reviewed) for status in sorted(VALID_STATUSES)}
    result = {
        "schemaVersion": 1,
        "ok": True,
        "decision": "mask_review_shard_complete_final_truth_audit_still_required",
        "inputs": {
            "reviewWorkspace": str(workspace_path),
            "reviewWorkspaceSha256": sha256_file(workspace_path),
            "shard": str(shard_path),
            "shardSha256": sha256_file(shard_path),
            "decisions": str(decisions_path),
            "decisionsSha256": sha256_file(decisions_path),
            "reviewedPageSha256s": expected_page_hashes,
        },
        "policy": {
            "reviewCompletionDoesNotGrantTrainingUse": True,
            "passItemsStillRequirePolygonTopologyAndFinalTruthAudit": True,
            "trainingUse": "prohibited",
            "originalResolutionReviewCompleted": True,
        },
        "shardIndex": args.shard_index,
        "counts": {"images": len(reviewed), **counts},
        "items": reviewed,
        "errors": [],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, **result["counts"]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
