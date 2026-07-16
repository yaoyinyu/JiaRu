from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rows_hash(rows: list[dict[str, str]], fieldnames: list[str]) -> str:
    payload = "\n".join("\x1f".join(row.get(field, "") for field in fieldnames) for row in rows)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a source-group-atomic quality review queue after deduplication.")
    parser.add_argument("--workspace-report", required=True)
    parser.add_argument("--near-duplicate-final", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--target-shard-size", type=int, default=50)
    args = parser.parse_args()
    if args.target_shard_size <= 0:
        raise ValueError("--target-shard-size must be positive")

    workspace_path = Path(args.workspace_report).resolve()
    duplicate_path = Path(args.near_duplicate_final).resolve()
    output_dir = Path(args.output_dir).resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"output directory must be absent or empty: {output_dir}")
    workspace = json.loads(workspace_path.read_text(encoding="utf-8"))
    duplicate = json.loads(duplicate_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    if workspace.get("ok") is not True or workspace.get("decision") != "review_workspace_ready_unreviewed":
        errors.append("workspace report must be a passing unreviewed workspace")
    if duplicate.get("ok") is not True or duplicate.get("decision") != "near_duplicate_visual_review_pass":
        errors.append("near-duplicate final report must pass")
    review_csv = Path(str(workspace.get("combinedReviewCsv", ""))).resolve()
    if not review_csv.is_file() or sha256_file(review_csv) != workspace.get("combinedReviewCsvSha256"):
        errors.append("workspace review CSV is missing or changed")
    with review_csv.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    if any(row.get("reviewStatus") or row.get("assignedRole") for row in rows):
        errors.append("quality queue must be built before review decisions are entered")
    excluded = {str(item.get("fileName")) for item in duplicate.get("excludedCandidates", [])}
    known = {row.get("fileName", "") for row in rows}
    unknown_exclusions = sorted(excluded - known)
    if unknown_exclusions:
        errors.append(f"near-duplicate exclusions are outside workspace: {','.join(unknown_exclusions)}")
    kept = [row for row in rows if row.get("fileName") not in excluded]
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in kept:
        groups[row["sourceGroup"]].append(row)
    ordered_groups = sorted(groups.items(), key=lambda item: item[0])
    shards: list[list[dict[str, str]]] = []
    current: list[dict[str, str]] = []
    for _, group_rows in ordered_groups:
        if current and len(current) + len(group_rows) > args.target_shard_size:
            shards.append(current)
            current = []
        current.extend(group_rows)
    if current:
        shards.append(current)

    output_dir.mkdir(parents=True, exist_ok=True)
    shard_dir = output_dir / "shards"
    shard_dir.mkdir()
    combined_path = output_dir / "quality-review-all.csv"
    with combined_path.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(kept)
    shard_reports: list[dict[str, object]] = []
    seen_groups: set[str] = set()
    for index, shard_rows in enumerate(shards, start=1):
        path = shard_dir / f"quality-review-{index:03d}.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(shard_rows)
        shard_groups = sorted({row["sourceGroup"] for row in shard_rows})
        overlap = seen_groups.intersection(shard_groups)
        if overlap:
            errors.append(f"source groups cross shards: {','.join(sorted(overlap))}")
        seen_groups.update(shard_groups)
        shard_reports.append({"index": index, "path": str(path), "sha256": sha256_file(path), "images": len(shard_rows), "sourceGroups": shard_groups})

    report = {
        "schemaVersion": 1,
        "ok": not errors,
        "decision": "quality_review_queue_ready" if not errors else "rejected_quality_review_queue",
        "inputs": {
            "workspaceReport": str(workspace_path),
            "workspaceReportSha256": sha256_file(workspace_path),
            "nearDuplicateFinal": str(duplicate_path),
            "nearDuplicateFinalSha256": sha256_file(duplicate_path),
        },
        "policy": {
            "originalResolutionReviewRequired": True,
            "sourceGroupAtomicShards": True,
            "fullyVisibleNailsRequireOneCompleteMaskEach": True,
            "croppedRequiredNailsMustBeExcluded": True,
            "trainingUseBeforeFinalAudit": "prohibited",
        },
        "counts": {
            "workspaceImages": len(rows),
            "deduplicationExclusions": len(excluded),
            "queuedImages": len(kept),
            "sourceGroups": len(groups),
            "shards": len(shards),
            "largestShard": max((len(shard) for shard in shards), default=0),
        },
        "combinedReviewCsv": str(combined_path),
        "combinedReviewCsvSha256": sha256_file(combined_path),
        "rowsSha256": rows_hash(kept, fieldnames),
        "shards": shard_reports,
        "errors": errors,
    }
    (output_dir / "quality-review-queue-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if errors:
        raise SystemExit(1)
    print(json.dumps({"ok": True, **report["counts"]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
