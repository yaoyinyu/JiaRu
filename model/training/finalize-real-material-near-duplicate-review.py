from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


ALLOWED_DECISIONS = {
    "duplicate-existing-exclude-left",
    "duplicate-batch-keep-left",
    "duplicate-batch-keep-right",
    "distinct-related-keep-both",
    "distinct-keep-both",
    "out-of-domain-exclude-both",
    "out-of-domain-exclude-left",
    "out-of-domain-exclude-right",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def expand_pair_ids(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    text = str(value)
    if ".." not in text:
        return [text]
    left, right = text.split("..", 1)
    if not left.startswith("near-") or not right.startswith("near-"):
        raise ValueError(f"invalid pair range: {text}")
    start = int(left.removeprefix("near-"))
    stop = int(right.removeprefix("near-"))
    if start > stop:
        raise ValueError(f"invalid descending pair range: {text}")
    return [f"near-{index:04d}" for index in range(start, stop + 1)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Finalize an original-resolution near-duplicate visual review.")
    parser.add_argument("--review-report", required=True)
    parser.add_argument("--decisions", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    report_path = Path(args.review_report).resolve()
    decisions_path = Path(args.decisions).resolve()
    output_dir = Path(args.output_dir).resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"output directory must be absent or empty: {output_dir}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    manifest = json.loads(decisions_path.read_text(encoding="utf-8"))
    csv_path = Path(str(report.get("reviewCsv", ""))).resolve()
    errors: list[str] = []
    if report.get("ok") is not True or report.get("decision") != "near_duplicate_visual_review_required":
        errors.append("review report must be a passing near-duplicate review build")
    if not csv_path.is_file() or sha256_file(csv_path) != report.get("reviewCsvSha256"):
        errors.append("review CSV is missing or changed")
    expected_report_hash = manifest.get("reviewReportSha256")
    if expected_report_hash and expected_report_hash != sha256_file(report_path):
        errors.append("decision manifest does not bind the current review report")
    page_hashes = {Path(str(item.get("path"))).name: item.get("sha256") for item in report.get("pages", [])}
    if manifest.get("reviewedPageHashes") != page_hashes:
        errors.append("all rendered review pages and hashes must be acknowledged")

    rows: list[dict[str, str]] = []
    if csv_path.is_file():
        with csv_path.open("r", encoding="utf-8-sig", newline="") as source:
            rows = list(csv.DictReader(source))
    rows_by_id = {row["pairId"]: row for row in rows}
    decisions: dict[str, tuple[str, str]] = {}
    for rule in manifest.get("rules", []):
        decision = str(rule.get("decision", ""))
        note = str(rule.get("note", "")).strip()
        if decision not in ALLOWED_DECISIONS:
            errors.append(f"unsupported decision: {decision}")
            continue
        for pair_id in expand_pair_ids(rule.get("pairIds", [])):
            if pair_id in decisions:
                errors.append(f"duplicate decision: {pair_id}")
            decisions[pair_id] = (decision, note)
    missing = sorted(set(rows_by_id) - set(decisions))
    extra = sorted(set(decisions) - set(rows_by_id))
    if missing:
        errors.append(f"unreviewed pairs: {','.join(missing)}")
    if extra:
        errors.append(f"unknown pairs: {','.join(extra)}")

    excluded: dict[str, dict[str, str]] = {}
    resolved_rows: list[dict[str, str]] = []
    counts: dict[str, int] = {}
    for row in rows:
        decision, note = decisions.get(row["pairId"], ("", ""))
        kind = row["kind"]
        if decision == "duplicate-existing-exclude-left" and kind != "cross-corpus":
            errors.append(f"{row['pairId']}: existing-corpus decision requires cross-corpus pair")
        if decision.startswith("duplicate-batch-") and kind != "batch":
            errors.append(f"{row['pairId']}: batch duplicate decision requires batch pair")
        to_exclude: list[tuple[str, str]] = []
        if decision in {"duplicate-existing-exclude-left", "duplicate-batch-keep-right", "out-of-domain-exclude-left"}:
            to_exclude.append((row["leftName"], "existing-corpus-duplicate" if decision.startswith("duplicate") else "out-of-domain-non-photo"))
        elif decision in {"duplicate-batch-keep-left", "out-of-domain-exclude-right"}:
            to_exclude.append((row["rightName"], "batch-near-duplicate" if decision.startswith("duplicate") else "out-of-domain-non-photo"))
        elif decision == "out-of-domain-exclude-both":
            to_exclude.extend(((row["leftName"], "out-of-domain-non-photo"), (row["rightName"], "out-of-domain-non-photo")))
        for file_name, reason in to_exclude:
            excluded.setdefault(file_name, {"fileName": file_name, "reason": reason, "evidencePairId": row["pairId"]})
        resolved = dict(row)
        resolved["decision"] = decision
        resolved["note"] = note
        resolved_rows.append(resolved)
        counts[decision] = counts.get(decision, 0) + 1

    output_dir.mkdir(parents=True, exist_ok=True)
    result = {
        "ok": not errors,
        "decision": "near_duplicate_visual_review_pass" if not errors else "rejected_near_duplicate_visual_review",
        "inputs": {
            "reviewReport": str(report_path),
            "reviewReportSha256": sha256_file(report_path),
            "reviewCsv": str(csv_path),
            "reviewCsvSha256": sha256_file(csv_path) if csv_path.is_file() else None,
            "decisions": str(decisions_path),
            "decisionsSha256": sha256_file(decisions_path),
        },
        "review": {
            "reviewer": manifest.get("reviewer"),
            "reviewedAt": manifest.get("reviewedAt"),
            "method": manifest.get("method"),
            "originalResolutionVisualReviewRequired": True,
        },
        "counts": {"pairs": len(rows), "excludedCandidates": len(excluded), "byDecision": counts},
        "excludedCandidates": sorted(excluded.values(), key=lambda item: item["fileName"]),
        "errors": errors,
    }
    (output_dir / "near-duplicate-review-final.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if errors:
        raise SystemExit(1)
    fieldnames = list(resolved_rows[0]) if resolved_rows else []
    with (output_dir / "near-duplicate-review-final.csv").open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(resolved_rows)
    print(json.dumps({"ok": True, **result["counts"]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
