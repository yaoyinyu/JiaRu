from __future__ import annotations

import argparse
import json
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a machine-checkable human review report for release-test annotation candidates."
    )
    parser.add_argument("--intake", required=True)
    parser.add_argument("--candidate-report", required=True)
    parser.add_argument("--review", required=True)
    parser.add_argument("--annotations", required=True)
    parser.add_argument("--output", required=True)
    return parser


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    args = build_parser().parse_args()
    intake = load_json(Path(args.intake))
    candidate_report = load_json(Path(args.candidate_report))
    review = load_json(Path(args.review))
    annotation_dir = Path(args.annotations).resolve()

    core_entries = {
        entry["fileName"]: entry
        for entry in intake["entries"]
        if entry["decision"] == "core"
    }
    candidate_outputs = {
        item["fileName"]: item for item in candidate_report["outputs"]
    }
    pass_files = set(review["passFiles"])
    exclude_files = set(review["excludeFiles"])
    decided_files = pass_files | exclude_files
    rework_files = set(core_entries) - decided_files
    errors: list[str] = []
    accepted_masks = 0
    accepted_source_groups: set[str] = set()

    for file_name in sorted(decided_files):
        if file_name not in core_entries:
            errors.append(f"review decision is not a core intake file: {file_name}")
    if pass_files & exclude_files:
        errors.append("the same file cannot be both pass and exclude")

    for file_name in sorted(core_entries):
        if file_name not in candidate_outputs:
            errors.append(f"missing candidate report output: {file_name}")

    for file_name in sorted(pass_files):
        annotation_path = annotation_dir / f"{Path(file_name).stem}.json"
        if not annotation_path.exists():
            errors.append(f"missing accepted annotation: {file_name}")
            continue
        annotation = load_json(annotation_path)
        if annotation["image"]["fileName"] != file_name:
            errors.append(f"annotation filename mismatch: {file_name}")
            continue
        polygons = annotation["annotations"]
        if not polygons:
            errors.append(f"accepted annotation has no polygons: {file_name}")
            continue
        for polygon in polygons:
            points = polygon.get("polygon", [])
            if len(points) < 3:
                errors.append(f"accepted annotation has invalid polygon: {file_name}")
                break
        accepted_masks += len(polygons)
        accepted_source_groups.add(core_entries[file_name]["sourceGroup"])

    reasons = review.get("excludeReasons", {})
    for file_name in sorted(exclude_files):
        if not reasons.get(file_name):
            errors.append(f"excluded file is missing a reason: {file_name}")

    report = {
        "schemaVersion": 1,
        "batchId": intake["batchId"],
        "decision": "human_reviewed_candidate_annotations_not_training_truth",
        "ok": not errors,
        "status": "core_review_partial_pass_rework_required" if rework_files else "core_review_complete",
        "counts": {
            "core": len(core_entries),
            "pass": len(pass_files),
            "rework": len(rework_files),
            "excluded": len(exclude_files),
            "acceptedMasks": accepted_masks,
            "acceptedSourceGroups": len(accepted_source_groups),
            "stressPending": intake["counts"].get("stress", 0),
        },
        "passFiles": sorted(pass_files),
        "reworkFiles": sorted(rework_files),
        "excludeFiles": sorted(exclude_files),
        "excludeReasons": reasons,
        "reviewPolicy": review["reviewPolicy"],
        "errors": errors,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output.resolve()), **report["counts"], "ok": report["ok"]}, ensure_ascii=True))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
