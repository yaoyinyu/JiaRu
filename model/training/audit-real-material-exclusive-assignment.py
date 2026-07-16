from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


HEADER = ["fileName", "reviewStatus", "assignedRole", "note"]
FINAL_STATUSES = {"pass", "exclude"}
ROLES = {"train", "val", "independent-release-test", "archive", "unassigned"}
AUTHORIZED_ROLES = {
    "A": {"train", "val", "independent-release-test"},
    "B": {"independent-release-test"},
    "C": {"archive"},
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit final visual-review assignments with source-group atomicity and training/test exclusivity."
    )
    parser.add_argument("--authorization", required=True)
    parser.add_argument("--review-csv")
    parser.add_argument("--output", required=True)
    return parser


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_review(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    errors: list[str] = []
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames != HEADER:
            errors.append(f"unexpected review header: {reader.fieldnames}; expected {HEADER}")
            return [], errors
        rows = [{key: (value or "").strip() for key, value in row.items()} for row in reader]
    return rows, errors


def main() -> None:
    args = build_parser().parse_args()
    authorization_path = Path(args.authorization).resolve()
    output_path = Path(args.output).resolve()
    document = json.loads(authorization_path.read_text(encoding="utf-8"))
    errors: list[str] = []

    authorization = document.get("authorization", {})
    decision = str(authorization.get("decision", ""))
    entries = document.get("entries", [])
    if document.get("schemaVersion") != 1 or document.get("ok") is not True:
        errors.append("authorization manifest must be a passing schemaVersion=1 document")
    if decision not in AUTHORIZED_ROLES or authorization.get("status") != "confirmed":
        errors.append("authorization decision must be confirmed A, B, or C")
    if not isinstance(entries, list) or not entries:
        errors.append("authorization entries must be non-empty")
        entries = []
    if document.get("entriesSha256") != canonical_sha256(entries):
        errors.append("authorization entriesSha256 mismatch")

    source_path = Path(str(document.get("sourceIntakePath", ""))).resolve()
    if not source_path.is_file() or document.get("sourceIntakeSha256") != sha256_file(source_path):
        errors.append("source candidate intake is missing or changed")
    else:
        source = json.loads(source_path.read_text(encoding="utf-8"))
        if document.get("sourceEntriesSha256") != canonical_sha256(source.get("entries", [])):
            errors.append("source candidate entry hash mismatch")

    root = Path(str(document.get("root", ""))).resolve()
    by_file: dict[str, dict[str, object]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append("authorization contains a non-object entry")
            continue
        file_name = str(entry.get("fileName", ""))
        if not file_name or file_name in by_file:
            errors.append(f"duplicate or empty authorization fileName: {file_name}")
            continue
        by_file[file_name] = entry
        image_path = (root / file_name).resolve()
        if image_path.parent != root or not image_path.is_file() or sha256_file(image_path) != entry.get("sha256"):
            errors.append(f"authorized image is missing, unsafe, or changed: {file_name}")
        if entry.get("trainingUse") != "prohibited":
            errors.append(f"unassigned authorization entry must remain training-prohibited: {file_name}")

    rows: list[dict[str, str]] = []
    if decision == "C" and not args.review_csv:
        rows = [
            {"fileName": file_name, "reviewStatus": "exclude", "assignedRole": "archive", "note": "archive-only"}
            for file_name in sorted(by_file)
        ]
    elif not args.review_csv:
        errors.append("A/B authorization requires --review-csv with full final visual-review coverage")
    else:
        review_path = Path(args.review_csv).resolve()
        if not review_path.is_file():
            errors.append(f"review CSV not found: {review_path}")
        else:
            rows, review_errors = read_review(review_path)
            errors.extend(review_errors)

    seen_rows: set[str] = set()
    group_roles: dict[str, set[str]] = {}
    assignments: list[dict[str, object]] = []
    role_counts = {role: 0 for role in sorted(ROLES)}
    for row in rows:
        file_name = row["fileName"]
        status = row["reviewStatus"]
        role = row["assignedRole"]
        entry = by_file.get(file_name)
        if file_name in seen_rows:
            errors.append(f"duplicate review row: {file_name}")
            continue
        seen_rows.add(file_name)
        if entry is None:
            errors.append(f"review row is not in authorization manifest: {file_name}")
            continue
        if status not in FINAL_STATUSES:
            errors.append(f"{file_name}: reviewStatus must be pass or exclude")
        if role not in ROLES:
            errors.append(f"{file_name}: unsupported assignedRole {role}")
            continue
        if status == "pass" and role not in AUTHORIZED_ROLES.get(decision, set()):
            errors.append(f"{file_name}: role {role} is not authorized by decision {decision}")
        if status == "exclude" and role not in {"unassigned", "archive"}:
            errors.append(f"{file_name}: excluded images cannot be assigned to {role}")
        source_group = str(entry.get("sourceGroup", ""))
        if status == "pass":
            group_roles.setdefault(source_group, set()).add(role)
        role_counts[role] += 1
        assignments.append(
            {
                "fileName": file_name,
                "sha256": entry.get("sha256"),
                "sourceGroup": source_group,
                "reviewStatus": status,
                "assignedRole": role,
                "note": row["note"],
            }
        )

    missing = sorted(set(by_file) - seen_rows)
    if missing:
        errors.append(f"review does not cover {len(missing)} authorization entries")
    leaking_groups = sorted(group for group, roles in group_roles.items() if len(roles) > 1)
    for group in leaking_groups:
        errors.append(f"sourceGroup is assigned to multiple roles: {group} -> {sorted(group_roles[group])}")

    result = {
        "schemaVersion": 1,
        "ok": not errors,
        "decision": "approved_real_material_exclusive_assignment" if not errors else "rejected_real_material_exclusive_assignment",
        "inputs": {
            "authorization": str(authorization_path),
            "authorizationSha256": sha256_file(authorization_path),
            "reviewCsv": str(Path(args.review_csv).resolve()) if args.review_csv else None,
            "reviewCsvSha256": sha256_file(Path(args.review_csv).resolve()) if args.review_csv and Path(args.review_csv).is_file() else None,
            "authorizationDecision": decision,
        },
        "policy": {
            "sourceGroupAtomic": True,
            "fullFinalReviewCoverageRequired": decision != "C",
            "trainingAndIndependentReleaseTestMutuallyExclusive": True,
            "valRequiresSeparateTruthAudit": True,
            "releaseTestTrainingUse": "prohibited",
        },
        "counts": {
            "authorizationEntries": len(by_file),
            "reviewRows": len(rows),
            "assignments": len(assignments),
            "sourceGroups": len(group_roles),
            "leakingSourceGroups": len(leaking_groups),
            "byRole": role_counts,
        },
        "leakingSourceGroups": leaking_groups,
        "assignmentsSha256": canonical_sha256(assignments),
        "errors": errors,
        "assignments": assignments,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output_path), "ok": result["ok"], "decision": result["decision"], **result["counts"]}, ensure_ascii=True))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
