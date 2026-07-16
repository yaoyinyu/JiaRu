from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


HEADER = [
    "fileName",
    "sha256",
    "sourceGroup",
    "width",
    "height",
    "reviewStatus",
    "fullyVisibleNails",
    "completeMasks",
    "issueCodes",
    "assignedRole",
    "note",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build source-group-atomic CSV shards for original-resolution real-material review."
    )
    parser.add_argument("--authorization", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--target-shard-size", type=int, default=50)
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


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=HEADER)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = build_parser().parse_args()
    if args.target_shard_size <= 0:
        raise ValueError("--target-shard-size must be a positive integer")
    authorization_path = Path(args.authorization).resolve()
    output_dir = Path(args.output_dir).resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"output directory must be absent or empty: {output_dir}")

    document = json.loads(authorization_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    authorization = document.get("authorization", {})
    decision = str(authorization.get("decision", ""))
    if document.get("schemaVersion") != 1 or document.get("ok") is not True:
        errors.append("authorization manifest must be a passing schemaVersion=1 document")
    if authorization.get("status") != "confirmed" or decision not in {"A", "B"}:
        errors.append("review workspace requires confirmed A or B authorization")
    entries = document.get("entries", [])
    if not isinstance(entries, list) or not entries:
        errors.append("authorization entries must be non-empty")
        entries = []
    if document.get("entriesSha256") != canonical_sha256(entries):
        errors.append("authorization entriesSha256 mismatch")

    source_path = Path(str(document.get("sourceIntakePath", ""))).resolve()
    if not source_path.is_file() or document.get("sourceIntakeSha256") != sha256_file(source_path):
        errors.append("source candidate intake is missing or changed")

    root = Path(str(document.get("root", ""))).resolve()
    grouped: dict[str, list[dict[str, object]]] = {}
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append("authorization contains a non-object entry")
            continue
        file_name = str(entry.get("fileName", ""))
        source_group = str(entry.get("sourceGroup", ""))
        image_path = (root / file_name).resolve()
        if not file_name or Path(file_name).name != file_name or image_path.parent != root:
            errors.append(f"unsafe candidate filename: {file_name}")
            continue
        if file_name in seen:
            errors.append(f"duplicate candidate filename: {file_name}")
            continue
        seen.add(file_name)
        if not source_group:
            errors.append(f"missing sourceGroup: {file_name}")
            continue
        if not image_path.is_file() or sha256_file(image_path) != entry.get("sha256"):
            errors.append(f"candidate image missing or changed: {file_name}")
            continue
        if entry.get("trainingUse") != "prohibited":
            errors.append(f"unreviewed entry must remain training-prohibited: {file_name}")
        grouped.setdefault(source_group, []).append(entry)

    if errors:
        output_dir.mkdir(parents=True, exist_ok=True)
        report = {
            "schemaVersion": 1,
            "ok": False,
            "decision": "rejected_real_material_review_workspace",
            "inputs": {"authorization": str(authorization_path), "authorizationSha256": sha256_file(authorization_path)},
            "errors": errors,
        }
        (output_dir / "review-workspace-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(report, ensure_ascii=True))
        raise SystemExit(1)

    shards: list[list[dict[str, object]]] = []
    current: list[dict[str, object]] = []
    for source_group in sorted(grouped):
        group_entries = sorted(grouped[source_group], key=lambda entry: str(entry["fileName"]))
        if current and len(current) + len(group_entries) > args.target_shard_size:
            shards.append(current)
            current = []
        current.extend(group_entries)
    if current:
        shards.append(current)

    output_dir.mkdir(parents=True, exist_ok=True)
    shard_dir = output_dir / "shards"
    shard_dir.mkdir(parents=True, exist_ok=True)
    manifest_shards: list[dict[str, object]] = []
    all_rows: list[dict[str, object]] = []
    for index, shard_entries in enumerate(shards, start=1):
        rows = [
            {
                "fileName": entry["fileName"],
                "sha256": entry["sha256"],
                "sourceGroup": entry["sourceGroup"],
                "width": entry.get("width", ""),
                "height": entry.get("height", ""),
                "reviewStatus": "",
                "fullyVisibleNails": "",
                "completeMasks": "",
                "issueCodes": "",
                "assignedRole": "",
                "note": "",
            }
            for entry in shard_entries
        ]
        shard_path = shard_dir / f"review-{index:03d}.csv"
        write_csv(shard_path, rows)
        all_rows.extend(rows)
        manifest_shards.append(
            {
                "index": index,
                "path": str(shard_path),
                "sha256": sha256_file(shard_path),
                "images": len(rows),
                "sourceGroups": sorted({str(row["sourceGroup"]) for row in rows}),
            }
        )

    combined_path = output_dir / "review-all.csv"
    write_csv(combined_path, all_rows)
    report = {
        "schemaVersion": 1,
        "ok": True,
        "decision": "review_workspace_ready_unreviewed",
        "inputs": {
            "authorization": str(authorization_path),
            "authorizationSha256": sha256_file(authorization_path),
            "authorizationDecision": decision,
            "root": str(root),
        },
        "policy": {
            "originalResolutionReviewRequired": True,
            "sourceGroupAtomicShards": True,
            "fullyVisibleNailsRequireOneCompleteMaskEach": True,
            "croppedRequiredNailsMustBeExcluded": True,
            "blankFieldsAreNotApproval": True,
            "trainingUseBeforeFinalAudit": "prohibited",
        },
        "counts": {
            "images": len(all_rows),
            "sourceGroups": len(grouped),
            "shards": len(manifest_shards),
            "targetShardSize": args.target_shard_size,
            "largestShard": max((int(shard["images"]) for shard in manifest_shards), default=0),
        },
        "combinedReviewCsv": str(combined_path),
        "combinedReviewCsvSha256": sha256_file(combined_path),
        "rowsSha256": canonical_sha256(all_rows),
        "shards": manifest_shards,
        "errors": [],
    }
    (output_dir / "review-workspace-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"outputDir": str(output_dir), "ok": True, "decision": report["decision"], **report["counts"]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
