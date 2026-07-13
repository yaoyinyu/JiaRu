from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path


ALLOWED_DECISIONS = {"core", "stress", "exclude"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def expand_decisions(config: dict[str, object], expected_count: int) -> dict[int, dict[str, str]]:
    decisions: dict[int, dict[str, str]] = {}
    for rule in config.get("rules", []):
        decision = str(rule["decision"])
        if decision not in ALLOWED_DECISIONS:
            raise ValueError(f"unsupported decision: {decision}")
        reason = str(rule["reason"])
        for start, end in rule["ranges"]:
            for index in range(int(start), int(end) + 1):
                if index in decisions:
                    raise ValueError(f"visual decision overlaps at index {index}")
                decisions[index] = {"decision": decision, "reason": reason}
    expected = set(range(1, expected_count + 1))
    missing = sorted(expected - set(decisions))
    extra = sorted(set(decisions) - expected)
    if missing or extra:
        raise ValueError(f"visual decision coverage mismatch: missing={missing}, extra={extra}")
    return decisions


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a source-isolated release-test intake report from audited images."
    )
    parser.add_argument("--rename-manifest", required=True)
    parser.add_argument("--corpus-audit", required=True)
    parser.add_argument("--decisions", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-csv", required=True)
    args = parser.parse_args()

    manifest = read_json(Path(args.rename_manifest).resolve())
    audit = read_json(Path(args.corpus_audit).resolve())
    config = read_json(Path(args.decisions).resolve())
    output_json = Path(args.output_json).resolve()
    output_csv = Path(args.output_csv).resolve()

    if manifest.get("status") != "applied":
        raise ValueError("rename manifest must have status=applied")
    root = Path(str(manifest["root"])).resolve()
    entries = list(manifest["entries"])
    audit_images = {str(item["path"]): item for item in audit["images"]}
    decisions = expand_decisions(config, len(entries))
    exact_cross_candidates = {
        str(item["candidate"])
        for item in audit.get("comparisons", {}).get("exactMatches", [])
    }

    errors: list[str] = []
    rows: list[dict[str, object]] = []
    for entry in entries:
        index = int(entry["index"])
        file_name = str(entry["renamedName"])
        path = root / file_name
        audit_record = audit_images.get(file_name)
        decision = decisions[index]
        if not path.is_file():
            errors.append(f"missing image: {file_name}")
        elif sha256_file(path) != entry["sha256"]:
            errors.append(f"sha256 mismatch: {file_name}")
        if audit_record is None or audit_record.get("sha256") != entry["sha256"]:
            errors.append(f"audit mismatch: {file_name}")
        if file_name in exact_cross_candidates and decision["decision"] != "exclude":
            errors.append(f"cross-corpus exact duplicate must be excluded: {file_name}")
        rows.append(
            {
                "index": index,
                "fileName": file_name,
                "sha256": entry["sha256"],
                "sourceGroup": entry["sourceGroup"],
                "sourceTitle": entry["sourceTitle"],
                "sourceAuthor": entry["sourceAuthor"],
                "sourceSequence": entry["sourceSequence"],
                "decision": decision["decision"],
                "reason": decision["reason"],
                "crossCorpusExactDuplicate": file_name in exact_cross_candidates,
                "authorizedUses": config["authorizedUses"],
                "trainingUse": "prohibited",
                "annotationStatus": "pending",
            }
        )

    counts = Counter(str(row["decision"]) for row in rows)
    accepted = [row for row in rows if row["decision"] in {"core", "stress"}]
    accepted_groups = {str(row["sourceGroup"]) for row in accepted}
    report = {
        "schemaVersion": 1,
        "batchId": config["batchId"],
        "ok": not errors,
        "authorization": {
            "authorizedUses": config["authorizedUses"],
            "trainingUse": "prohibited",
            "confirmedBy": "user",
            "confirmedOn": config["authorizationDate"],
        },
        "root": str(root),
        "counts": {
            "total": len(rows),
            "core": counts["core"],
            "stress": counts["stress"],
            "excluded": counts["exclude"],
            "accepted": len(accepted),
            "acceptedSourceGroups": len(accepted_groups),
            "crossCorpusExactDuplicates": len(exact_cross_candidates),
            "annotationPending": len(accepted),
        },
        "status": "intake_pass_annotation_pending" if not errors else "failed",
        "errors": errors,
        "entries": rows,
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    print(json.dumps({"ok": report["ok"], "counts": report["counts"], "status": report["status"]}, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
