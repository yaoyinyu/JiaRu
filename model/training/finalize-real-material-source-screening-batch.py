from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def resolved_path(value: object) -> Path:
    return Path(str(value or "")).resolve()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Finalize every source-screening shard and prove exact queue coverage without granting training eligibility."
    )
    parser.add_argument("--queue-report", required=True)
    parser.add_argument("--reports-root", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    queue_path = Path(args.queue_report).resolve()
    reports_root = Path(args.reports_root).resolve()
    output_dir = Path(args.output_dir).resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"output directory must be absent or empty: {output_dir}")

    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    if queue.get("ok") is not True or queue.get("decision") != "quality_review_queue_ready":
        errors.append("quality review queue report must pass")

    combined_csv = resolved_path(queue.get("combinedReviewCsv"))
    if not combined_csv.is_file() or sha256_file(combined_csv) != queue.get("combinedReviewCsvSha256"):
        errors.append("combined quality review CSV is missing or changed")
        expected_rows: list[dict[str, str]] = []
    else:
        expected_rows = read_csv(combined_csv)

    expected_by_file: dict[str, dict[str, str]] = {}
    for row in expected_rows:
        file_name = row.get("fileName", "")
        if not file_name or file_name in expected_by_file:
            errors.append(f"combined queue contains duplicate or empty fileName: {file_name}")
        else:
            expected_by_file[file_name] = row

    resolved_items: list[dict[str, object]] = []
    report_evidence: list[dict[str, object]] = []
    seen_files: set[str] = set()
    seen_source_groups: dict[str, int] = {}
    by_decision: dict[str, int] = {}

    shards = queue.get("shards", [])
    if not isinstance(shards, list):
        errors.append("quality review queue shards must be an array")
        shards = []

    for shard in shards:
        index = int(shard.get("index", 0))
        shard_id = f"{index:03d}"
        shard_path = resolved_path(shard.get("path"))
        report_path = reports_root / f"source-screening-{shard_id}" / "source-screening-final.json"
        if not shard_path.is_file() or sha256_file(shard_path) != shard.get("sha256"):
            errors.append(f"quality review shard {shard_id} is missing or changed")
            continue
        if not report_path.is_file():
            errors.append(f"source screening report is missing for shard {shard_id}")
            continue

        report = json.loads(report_path.read_text(encoding="utf-8"))
        report_evidence.append(
            {"shardIndex": index, "path": str(report_path), "sha256": sha256_file(report_path)}
        )
        if report.get("ok") is not True or report.get("decision") != "source_screening_shard_pass":
            errors.append(f"source screening report did not pass for shard {shard_id}")

        sheets_path = resolved_path(report.get("inputs", {}).get("sheetsReport"))
        if not sheets_path.is_file() or sha256_file(sheets_path) != report.get("inputs", {}).get("sheetsReportSha256"):
            errors.append(f"screening sheets report is missing or changed for shard {shard_id}")
            continue
        sheets = json.loads(sheets_path.read_text(encoding="utf-8"))
        if sheets.get("inputs", {}).get("queueReportSha256") != sha256_file(queue_path):
            errors.append(f"screening sheets report does not bind the current queue for shard {shard_id}")
        if resolved_path(sheets.get("inputs", {}).get("shard")) != shard_path:
            errors.append(f"screening sheets report binds the wrong shard for {shard_id}")
        if sheets.get("inputs", {}).get("shardSha256") != shard.get("sha256"):
            errors.append(f"screening sheets report binds a stale shard hash for {shard_id}")

        shard_rows = read_csv(shard_path)
        items = report.get("items", [])
        if len(shard_rows) != int(shard.get("images", -1)) or len(items) != len(shard_rows):
            errors.append(f"source screening item count differs from queue shard {shard_id}")
        report_by_file = {str(item.get("fileName", "")): item for item in items}
        if len(report_by_file) != len(items):
            errors.append(f"source screening report contains duplicate fileName values for shard {shard_id}")

        for row in shard_rows:
            file_name = row.get("fileName", "")
            item = report_by_file.get(file_name)
            if item is None:
                errors.append(f"source screening report misses {file_name} in shard {shard_id}")
                continue
            if file_name in seen_files:
                errors.append(f"source screening batch repeats fileName: {file_name}")
                continue
            seen_files.add(file_name)
            if item.get("sha256") != row.get("sha256") or item.get("sourceGroup") != row.get("sourceGroup"):
                errors.append(f"source screening identity differs from queue for {file_name}")
            if item.get("trainingUse") != "prohibited" or item.get("annotationTruthStatus") != "not-started":
                errors.append(f"source screening item improperly grants training or annotation truth: {file_name}")
            decision = str(item.get("decision", ""))
            by_decision[decision] = by_decision.get(decision, 0) + 1
            source_group = str(item.get("sourceGroup", ""))
            seen_source_groups[source_group] = seen_source_groups.get(source_group, 0) + 1
            resolved_items.append(item)

    missing = sorted(set(expected_by_file) - seen_files)
    extra = sorted(seen_files - set(expected_by_file))
    if missing:
        errors.append(f"source screening batch misses {len(missing)} queued images")
    if extra:
        errors.append(f"source screening batch contains {len(extra)} images outside the queue")
    for file_name in sorted(seen_files & set(expected_by_file)):
        expected = expected_by_file[file_name]
        item = next(item for item in resolved_items if item.get("fileName") == file_name)
        if item.get("sha256") != expected.get("sha256") or item.get("sourceGroup") != expected.get("sourceGroup"):
            errors.append(f"source screening batch differs from the combined queue for {file_name}")

    kept = by_decision.get("keep-for-annotation", 0)
    total = len(resolved_items)
    expected_counts = queue.get("counts", {})
    if total != int(expected_counts.get("queuedImages", -1)):
        errors.append("source screening batch image count differs from the queue report")
    if len(report_evidence) != int(expected_counts.get("shards", -1)):
        errors.append("source screening batch report count differs from the queue report")
    if len(seen_source_groups) != int(expected_counts.get("sourceGroups", -1)):
        errors.append("source screening batch source-group count differs from the queue report")

    output_dir.mkdir(parents=True, exist_ok=True)
    output = {
        "schemaVersion": 1,
        "ok": not errors,
        "decision": "source_screening_batch_pass" if not errors else "rejected_source_screening_batch",
        "inputs": {
            "queueReport": str(queue_path),
            "queueReportSha256": sha256_file(queue_path),
            "combinedReviewCsv": str(combined_csv),
            "combinedReviewCsvSha256": sha256_file(combined_csv) if combined_csv.is_file() else None,
            "reportsRoot": str(reports_root),
        },
        "policy": {
            "exactQueueCoverageRequired": True,
            "sourceGroupsRemainAtomicForSplit": True,
            "sourceScreeningDoesNotApproveMasks": True,
            "sourceScreeningDoesNotGrantTrainingUse": True,
        },
        "counts": {
            "images": total,
            "shards": len(report_evidence),
            "sourceGroups": len(seen_source_groups),
            "keptForAnnotation": kept,
            "excluded": total - kept,
            "byDecision": by_decision,
        },
        "shardReports": report_evidence,
        "items": resolved_items,
        "errors": errors,
    }
    output_path = output_dir / "source-screening-batch-final.json"
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if errors:
        raise SystemExit(1)
    print(json.dumps({"ok": True, **output["counts"]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
