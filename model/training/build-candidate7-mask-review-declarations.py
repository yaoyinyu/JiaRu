from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_atomic(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def machine_issue_codes(row: dict[str, str]) -> list[str]:
    expected = int(row["expectedFullyVisibleNails"])
    candidates = int(row["candidateCount"])
    suspects = int(row["geometrySuspectCount"])
    issues: list[str] = []
    if candidates < expected:
        issues.append("missing_complete_mask")
    elif candidates > expected:
        issues.append("candidate_count_mismatch")
    if suspects:
        issues.append("geometry_suspect_requires_original_resolution_repair")
    return issues or ["original_resolution_visual_rework_required"]


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build complete, hash-bound candidate7 mask-review declarations from a "
            "human pass allowlist; every non-allowlisted item remains rework."
        )
    )
    parser.add_argument("--review-workspace", required=True)
    parser.add_argument("--assessment", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    workspace_path = Path(args.review_workspace).resolve()
    assessment_path = Path(args.assessment).resolve()
    output_dir = Path(args.output_dir).resolve()
    workspace = read_json(workspace_path)
    assessment = read_json(assessment_path)
    errors: list[str] = []

    if (
        workspace.get("ok") is not True
        or workspace.get("decision")
        != "first_annotation_mask_review_workspace_ready_original_resolution_review_required"
    ):
        errors.append("a passing first-annotation mask review workspace is required")
    if assessment.get("schemaVersion") != 1:
        errors.append("unsupported assessment schemaVersion")
    if assessment.get("decision") != "candidate7_original_resolution_mask_review_assessment":
        errors.append("assessment decision is not candidate7 mask review")
    if assessment.get("reviewWorkspaceSha256") != sha256_file(workspace_path):
        errors.append("assessment does not bind the current review workspace")
    if assessment.get("originalResolutionReviewCompleted") is not True:
        errors.append("assessment must confirm original-resolution review completion")

    pass_files = assessment.get("passFiles", [])
    overrides = assessment.get("reworkOverrides", {})
    if not isinstance(pass_files, list) or any(not isinstance(item, str) or not item for item in pass_files):
        errors.append("passFiles must be a list of non-empty file names")
        pass_files = []
    if len(set(pass_files)) != len(pass_files):
        errors.append("passFiles contains duplicates")
    if not isinstance(overrides, dict):
        errors.append("reworkOverrides must be an object")
        overrides = {}

    all_rows: dict[str, dict[str, str]] = {}
    shard_rows: dict[int, list[dict[str, str]]] = {}
    for shard in workspace.get("shards", []):
        shard_index = int(shard["index"])
        shard_path = Path(str(shard["path"])).resolve()
        if not shard_path.is_file() or sha256_file(shard_path) != shard.get("sha256"):
            errors.append(f"bound shard is missing or changed: {shard_path}")
            continue
        with shard_path.open("r", encoding="utf-8-sig", newline="") as source:
            rows = list(csv.DictReader(source))
        shard_rows[shard_index] = rows
        for row in rows:
            file_name = row["fileName"]
            if file_name in all_rows:
                errors.append(f"duplicate workspace fileName: {file_name}")
            all_rows[file_name] = row

    unknown_passes = sorted(set(pass_files) - set(all_rows))
    unknown_overrides = sorted(set(overrides) - set(all_rows))
    if unknown_passes:
        errors.append(f"unknown pass files: {unknown_passes}")
    if unknown_overrides:
        errors.append(f"unknown rework override files: {unknown_overrides}")

    for file_name in pass_files:
        row = all_rows.get(file_name)
        if row is None:
            continue
        if int(row["candidateCount"]) != int(row["expectedFullyVisibleNails"]):
            errors.append(f"pass candidate count differs from expected: {file_name}")
        if int(row["geometrySuspectCount"]) != 0:
            errors.append(f"pass retains geometry suspects: {file_name}")
    for file_name, override in overrides.items():
        if not isinstance(override, dict):
            errors.append(f"rework override must be an object: {file_name}")
            continue
        issue_codes = override.get("issueCodes", [])
        if not isinstance(issue_codes, list) or any(
            not isinstance(code, str) or not code for code in issue_codes
        ):
            errors.append(f"rework override issueCodes are invalid: {file_name}")
    if errors:
        raise SystemExit("\n".join(errors))

    pass_set = set(pass_files)
    outputs: list[dict[str, Any]] = []
    for shard_index in sorted(shard_rows):
        pages = [
            page
            for page in workspace.get("pages", [])
            if int(page.get("shardIndex", -1)) == shard_index
        ]
        items: list[dict[str, Any]] = []
        for row in shard_rows[shard_index]:
            file_name = row["fileName"]
            if file_name in pass_set:
                items.append(
                    {
                        "fileName": file_name,
                        "sha256": row["sha256"],
                        "sourceGroup": row["sourceGroup"],
                        "reviewStatus": "pass",
                        "finalCompleteMaskCount": int(row["expectedFullyVisibleNails"]),
                        "issueCodes": [],
                        "note": "原分辨率逐甲审核通过；候选数、完整可见甲面数和几何证据一致。",
                    }
                )
                continue
            override = overrides.get(file_name, {})
            issue_codes = override.get("issueCodes") or machine_issue_codes(row)
            items.append(
                {
                    "fileName": file_name,
                    "sha256": row["sha256"],
                    "sourceGroup": row["sourceGroup"],
                    "reviewStatus": "rework",
                    "finalCompleteMaskCount": None,
                    "issueCodes": issue_codes,
                    "note": str(
                        override.get(
                            "note",
                            "原分辨率审核未通过；保持 trainingUse=prohibited，进入精确返修。",
                        )
                    ),
                }
            )
        document = {
            "schemaVersion": 1,
            "decision": "candidate7_original_resolution_mask_review_declaration",
            "reviewWorkspaceSha256": sha256_file(workspace_path),
            "assessmentPath": str(assessment_path),
            "assessmentSha256": sha256_file(assessment_path),
            "shardIndex": shard_index,
            "shardSha256": next(
                str(shard["sha256"])
                for shard in workspace.get("shards", [])
                if int(shard["index"]) == shard_index
            ),
            "originalResolutionReviewCompleted": True,
            "reviewedPageSha256s": [str(page["sha256"]) for page in pages],
            "trainingUse": "prohibited",
            "items": items,
        }
        output = output_dir / f"mask-review-shard-{shard_index:03d}-declaration.json"
        write_json_atomic(output, document)
        outputs.append(
            {
                "path": str(output),
                "sha256": sha256_file(output),
                "items": len(items),
                "pass": sum(item["reviewStatus"] == "pass" for item in items),
                "rework": sum(item["reviewStatus"] == "rework" for item in items),
            }
        )

    print(
        json.dumps(
            {
                "ok": True,
                "assessmentSha256": sha256_file(assessment_path),
                "outputs": outputs,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
