from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


DECISIONS = {"keep-for-annotation", "exclude-out-of-domain", "exclude-collage", "exclude-cropped", "exclude-quality"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Finalize one source-screening shard without granting training eligibility.")
    parser.add_argument("--sheets-report", required=True)
    parser.add_argument("--decisions", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    sheets_path = Path(args.sheets_report).resolve()
    decisions_path = Path(args.decisions).resolve()
    output_dir = Path(args.output_dir).resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"output directory must be absent or empty: {output_dir}")
    sheets = json.loads(sheets_path.read_text(encoding="utf-8"))
    manifest = json.loads(decisions_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    if sheets.get("ok") is not True or sheets.get("decision") != "screening_sheets_ready_original_resolution_review_still_required":
        errors.append("screening sheets report must pass")
    if manifest.get("sheetsReportSha256") != sha256_file(sheets_path):
        errors.append("decisions do not bind the current sheets report")
    page_hashes = {Path(str(item.get("path"))).name: item.get("sha256") for item in sheets.get("pages", [])}
    if manifest.get("reviewedPageHashes") != page_hashes:
        errors.append("all screening pages and hashes must be acknowledged")
    shard_path = Path(str(sheets.get("inputs", {}).get("shard", ""))).resolve()
    if not shard_path.is_file() or sha256_file(shard_path) != sheets.get("inputs", {}).get("shardSha256"):
        errors.append("screening shard is missing or changed")
    with shard_path.open("r", encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    by_file = {row["fileName"]: row for row in rows}
    decisions: dict[str, dict[str, object]] = {}
    for item in manifest.get("items", []):
        file_name = str(item.get("fileName", ""))
        decision = str(item.get("decision", ""))
        if not file_name or file_name in decisions:
            errors.append(f"duplicate or empty decision fileName: {file_name}")
            continue
        if decision not in DECISIONS:
            errors.append(f"unsupported screening decision: {decision}")
        nail_count = item.get("fullyVisibleNails")
        if decision == "keep-for-annotation" and (not isinstance(nail_count, int) or nail_count <= 0):
            errors.append(f"kept image requires a positive fullyVisibleNails count: {file_name}")
        decisions[file_name] = item
    missing = sorted(set(by_file) - set(decisions))
    extra = sorted(set(decisions) - set(by_file))
    if missing:
        errors.append(f"screening decisions miss {len(missing)} shard images")
    if extra:
        errors.append(f"screening decisions contain unknown images: {','.join(extra)}")

    resolved: list[dict[str, object]] = []
    counts: dict[str, int] = {}
    for row in rows:
        item = decisions.get(row["fileName"], {})
        decision = str(item.get("decision", ""))
        counts[decision] = counts.get(decision, 0) + 1
        resolved.append({
            "fileName": row["fileName"], "sha256": row["sha256"], "sourceGroup": row["sourceGroup"],
            "decision": decision, "fullyVisibleNails": item.get("fullyVisibleNails"), "note": item.get("note", ""),
            "trainingUse": "prohibited", "annotationTruthStatus": "not-started",
        })
    output_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "schemaVersion": 1, "ok": not errors,
        "decision": "source_screening_shard_pass" if not errors else "rejected_source_screening_shard",
        "inputs": {"sheetsReport": str(sheets_path), "sheetsReportSha256": sha256_file(sheets_path), "decisions": str(decisions_path), "decisionsSha256": sha256_file(decisions_path)},
        "review": {"reviewer": manifest.get("reviewer"), "reviewedAt": manifest.get("reviewedAt"), "method": manifest.get("method")},
        "policy": {"sourceScreeningDoesNotApproveMasks": True, "sourceScreeningDoesNotGrantTrainingUse": True, "originalResolutionReviewRequiredForKeptImages": True},
        "counts": {"images": len(rows), "keptForAnnotation": counts.get("keep-for-annotation", 0), "excluded": len(rows) - counts.get("keep-for-annotation", 0), "byDecision": counts},
        "items": resolved, "errors": errors,
    }
    (output_dir / "source-screening-final.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if errors:
        raise SystemExit(1)
    print(json.dumps({"ok": True, **report["counts"]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
