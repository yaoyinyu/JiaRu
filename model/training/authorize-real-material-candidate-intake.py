from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


DECISIONS = {
    "A": {
        "name": "commercial-training-release-regression",
        "authorizedUses": [
            "commercial-model-training",
            "independent-release-test",
            "long-term-regression",
        ],
        "trainingUse": "permitted-after-visual-review-and-source-isolation",
        "status": "authorized_for_review_assignment_training_or_release_test",
    },
    "B": {
        "name": "release-regression-only",
        "authorizedUses": ["independent-release-test", "long-term-regression"],
        "trainingUse": "prohibited",
        "status": "authorized_for_review_assignment_release_test_only",
    },
    "C": {
        "name": "archive-only",
        "authorizedUses": ["archive-only"],
        "trainingUse": "prohibited",
        "status": "authorized_archive_only",
    },
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bind a user A/B/C usage decision to a real-material candidate intake without copying images."
    )
    parser.add_argument("--intake", required=True)
    parser.add_argument("--decision", required=True, choices=sorted(DECISIONS))
    parser.add_argument("--confirmed-by", required=True)
    parser.add_argument("--confirmation-note", required=True)
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


def main() -> None:
    args = build_parser().parse_args()
    intake_path = Path(args.intake).resolve()
    output_path = Path(args.output).resolve()
    intake = json.loads(intake_path.read_text(encoding="utf-8"))
    decision = DECISIONS[args.decision]
    errors: list[str] = []

    if intake.get("schemaVersion") != 1 or intake.get("ok") is not True:
        errors.append("candidate intake must be a passing schemaVersion=1 document")
    authorization = intake.get("authorization", {})
    if (
        authorization.get("status") != "pending-user-confirmation"
        or authorization.get("authorizedUses") != []
        or authorization.get("trainingUse") != "prohibited"
    ):
        errors.append("candidate intake must still be pending and training-prohibited")
    if intake.get("status") != "candidate_inventory_pass_authorization_and_visual_review_pending":
        errors.append("candidate intake status is not awaiting authorization")

    root = Path(str(intake.get("root", ""))).resolve()
    if not root.is_dir():
        errors.append(f"candidate root not found: {root}")
    entries = intake.get("entries", [])
    if not isinstance(entries, list) or not entries:
        errors.append("candidate intake entries must be a non-empty array")
        entries = []
    if int(intake.get("counts", {}).get("images", -1)) != len(entries):
        errors.append("candidate intake image count does not match entries")

    verified_entries: list[dict[str, object]] = []
    seen_files: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append("candidate intake contains a non-object entry")
            continue
        file_name = str(entry.get("fileName", ""))
        image_path = (root / file_name).resolve()
        if not file_name or Path(file_name).name != file_name or image_path.parent != root:
            errors.append(f"unsafe candidate filename: {file_name}")
            continue
        if file_name in seen_files:
            errors.append(f"duplicate candidate filename: {file_name}")
            continue
        seen_files.add(file_name)
        if not image_path.is_file():
            errors.append(f"candidate image missing: {file_name}")
            continue
        if sha256_file(image_path) != entry.get("sha256"):
            errors.append(f"candidate image sha256 drift: {file_name}")
            continue
        if entry.get("trainingUse") != "prohibited":
            errors.append(f"candidate entry was not training-prohibited before authorization: {file_name}")
            continue

        next_entry = dict(entry)
        next_entry["authorizedUses"] = decision["authorizedUses"]
        # Authorization grants a possible future use; it never promotes an
        # unreviewed image into training. A later reviewed, source-isolated
        # assignment step must change this field deliberately.
        next_entry["trainingUse"] = "prohibited"
        next_entry["trainingEligibility"] = decision["trainingUse"]
        next_entry["decision"] = (
            "archive-only" if args.decision == "C" else "pending-original-resolution-visual-review-and-exclusive-assignment"
        )
        verified_entries.append(next_entry)

    if len(verified_entries) != len(entries):
        errors.append(f"verified {len(verified_entries)} of {len(entries)} candidate entries")

    document = {
        "schemaVersion": 1,
        "batchId": intake.get("batchId"),
        "ok": not errors,
        "sourceIntakePath": str(intake_path),
        "sourceIntakeSha256": sha256_file(intake_path),
        "sourceEntriesSha256": canonical_sha256(entries),
        "root": str(root),
        "authorization": {
            "status": "confirmed",
            "decision": args.decision,
            "decisionName": decision["name"],
            "authorizedUses": decision["authorizedUses"],
            "trainingUse": decision["trainingUse"],
            "confirmedBy": args.confirmed_by.strip(),
            "confirmationNote": args.confirmation_note.strip(),
            "confirmedAt": datetime.now(timezone.utc).isoformat(),
        },
        "assignmentPolicy": {
            "sourceGroupAtomic": True,
            "visualReviewRequired": args.decision != "C",
            "trainingAndIndependentReleaseTestMutuallyExclusive": True,
            "trainingRequiresCompleteNailReview": args.decision == "A",
            "unreviewedTrainingUse": "prohibited",
        },
        "status": decision["status"] if not errors else "invalid",
        "counts": {
            "images": len(verified_entries),
            "sourceGroups": len({str(entry.get("sourceGroup", "")) for entry in verified_entries}),
        },
        "entriesSha256": canonical_sha256(verified_entries),
        "errors": errors,
        "entries": verified_entries,
    }
    if not args.confirmed_by.strip() or not args.confirmation_note.strip():
        document["errors"].append("confirmed-by and confirmation-note must be non-empty")
        document["ok"] = False
        document["status"] = "invalid"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output_path),
                "ok": document["ok"],
                "status": document["status"],
                "decision": args.decision,
                **document["counts"],
            },
            ensure_ascii=True,
        )
    )
    if not document["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
