from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
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
        description="Bind a human mask-review declaration to the exact workspace, shard, pages, and image identities."
    )
    parser.add_argument("--review-workspace", required=True)
    parser.add_argument("--shard-index", required=True, type=int)
    parser.add_argument("--declaration", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    workspace_path = Path(args.review_workspace).resolve()
    declaration_path = Path(args.declaration).resolve()
    output_path = Path(args.output).resolve()
    workspace = read_json(workspace_path)
    declaration = read_json(declaration_path)
    errors: list[str] = []

    if workspace.get("ok") is not True or workspace.get("decision") != "first_annotation_mask_review_workspace_ready_original_resolution_review_required":
        errors.append("a passing first-annotation mask review workspace is required")
    if declaration.get("schemaVersion") != 1:
        errors.append("unsupported declaration schemaVersion")
    if declaration.get("shardIndex") != args.shard_index:
        errors.append("declaration shard index differs from the requested shard")
    if declaration.get("originalResolutionReviewCompleted") is not True:
        errors.append("declaration must explicitly confirm original-resolution review completion")

    shard = next((item for item in workspace.get("shards", []) if int(item.get("index", -1)) == args.shard_index), None)
    if shard is None:
        errors.append(f"unknown shard index: {args.shard_index}")
        shard_path = Path("missing")
    else:
        shard_path = Path(str(shard.get("path", ""))).resolve()
        if not shard_path.is_file() or sha256_file(shard_path) != shard.get("sha256"):
            errors.append("bound review shard is missing or changed")

    pages = [page for page in workspace.get("pages", []) if int(page.get("shardIndex", -1)) == args.shard_index]
    expected_page_hashes = [str(page.get("sha256", "")) for page in pages]
    if declaration.get("reviewedPageSha256s") != expected_page_hashes:
        errors.append("declaration must acknowledge every bound page hash in order")
    for page in pages:
        page_path = Path(str(page.get("path", ""))).resolve()
        if not page_path.is_file() or sha256_file(page_path) != page.get("sha256"):
            errors.append(f"review page is missing or changed: {page_path}")

    shard_rows: list[dict[str, str]] = []
    if shard_path.is_file():
        with shard_path.open("r", encoding="utf-8-sig", newline="") as source:
            shard_rows = list(csv.DictReader(source))
    row_by_file = {row["fileName"]: row for row in shard_rows}

    declaration_items = declaration.get("items", [])
    declared_by_file: dict[str, dict[str, Any]] = {}
    for item in declaration_items:
        file_name = str(item.get("fileName", ""))
        if not file_name or file_name in declared_by_file:
            errors.append(f"duplicate or empty declaration fileName: {file_name}")
            continue
        status = str(item.get("reviewStatus", ""))
        issue_codes = item.get("issueCodes", [])
        if status not in VALID_STATUSES:
            errors.append(f"invalid reviewStatus for {file_name}: {status}")
        if not isinstance(issue_codes, list) or any(not isinstance(code, str) or not code for code in issue_codes):
            errors.append(f"issueCodes must be a list of non-empty strings: {file_name}")
        if status != "pass" and not issue_codes:
            errors.append(f"{status} requires issue codes: {file_name}")
        if status == "pass" and issue_codes:
            errors.append(f"pass cannot retain issue codes: {file_name}")
        declared_by_file[file_name] = item
    if set(declared_by_file) != set(row_by_file):
        errors.append("declaration must exactly cover the bound review shard")

    items: list[dict[str, Any]] = []
    for row in shard_rows:
        declared = declared_by_file.get(row["fileName"])
        if declared is None:
            continue
        status = str(declared.get("reviewStatus", ""))
        expected_count = int(row["expectedFullyVisibleNails"])
        candidate_count = int(row["candidateCount"])
        if status == "pass" and candidate_count != expected_count:
            errors.append(f"pass requires candidate count to equal expected: {row['fileName']}")
        items.append({
            "fileName": row["fileName"],
            "sha256": row["sha256"],
            "sourceGroup": row["sourceGroup"],
            "reviewStatus": status,
            "finalCompleteMaskCount": expected_count if status == "pass" else None,
            "issueCodes": declared.get("issueCodes", []),
            "note": str(declared.get("note", "")),
        })

    if errors:
        raise SystemExit("\n".join(errors))

    result = {
        "schemaVersion": 1,
        "reviewWorkspaceSha256": sha256_file(workspace_path),
        "shardIndex": args.shard_index,
        "shardSha256": sha256_file(shard_path),
        "reviewedPageSha256s": expected_page_hashes,
        "reviewDeclaration": str(declaration_path),
        "reviewDeclarationSha256": sha256_file(declaration_path),
        "originalResolutionReviewCompleted": True,
        "trainingUse": "prohibited",
        "items": items,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(f".{output_path.name}.{os.getpid()}.tmp")
    temporary_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary_path, output_path)
    print(json.dumps({"ok": True, "items": len(items), "output": str(output_path)}, ensure_ascii=True))


if __name__ == "__main__":
    main()
