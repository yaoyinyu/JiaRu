from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


REQUIRED_USES = {"independent-release-test", "long-term-regression"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a provenance-safe release-test intake for reviewed regions derived from stress images."
    )
    parser.add_argument("--parent-intake", required=True)
    parser.add_argument("--region-report", required=True)
    parser.add_argument("--region-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    parent_intake = load_json(Path(args.parent_intake).resolve())
    region_report = load_json(Path(args.region_report).resolve())
    region_dir = Path(args.region_dir).resolve()
    output_path = Path(args.output).resolve()
    errors: list[str] = []

    authorization = parent_intake.get("authorization", {})
    authorized_uses = set(authorization.get("authorizedUses", []))
    if not REQUIRED_USES.issubset(authorized_uses):
        errors.append("parent intake is missing required release-test/regression authorization")
    if authorization.get("trainingUse") != "prohibited":
        errors.append("parent intake trainingUse must be prohibited")
    if not region_report.get("ok"):
        errors.append("region extraction report must be ok")

    parents = {entry["fileName"]: entry for entry in parent_intake.get("entries", [])}
    entries: list[dict[str, object]] = []
    seen_files: set[str] = set()
    seen_parents: set[str] = set()
    for region in region_report.get("outputs", []):
        parent_name = region["parentFileName"]
        parent = parents.get(parent_name)
        file_name = region["outputFileName"]
        if parent is None:
            errors.append(f"region parent is absent from intake: {parent_name}")
            continue
        if parent.get("decision") != "stress":
            errors.append(f"region parent is not a stress item: {parent_name}")
        if parent.get("sha256") != region.get("parentSha256"):
            errors.append(f"parent sha256 mismatch: {parent_name}")
        if file_name in seen_files:
            errors.append(f"duplicate region output filename: {file_name}")
            continue
        if parent_name in seen_parents:
            errors.append(f"multiple primary regions for the same parent: {parent_name}")
            continue
        seen_files.add(file_name)
        seen_parents.add(parent_name)
        region_path = (region_dir / file_name).resolve()
        if region_path.parent != region_dir or not region_path.is_file():
            errors.append(f"region output is missing or unsafe: {file_name}")
            continue
        actual_sha256 = sha256_file(region_path)
        if actual_sha256 != region.get("outputSha256"):
            errors.append(f"region sha256 mismatch: {file_name}")
        entries.append(
            {
                "fileName": file_name,
                "sha256": actual_sha256,
                "sourceGroup": region["sourceGroup"],
                "decision": "core",
                "reason": "reviewed_primary_photo_region_from_stress_parent",
                "parentFileName": parent_name,
                "parentSha256": region["parentSha256"],
                "parentSourceGroup": parent["sourceGroup"],
                "parentDecision": parent["decision"],
                "regionId": region["regionId"],
                "normalizedBox": region["normalizedBox"],
                "authorizedUses": sorted(REQUIRED_USES),
                "trainingUse": "prohibited",
                "annotationStatus": "pending",
            }
        )

    expected_stress = sum(
        entry.get("decision") == "stress" for entry in parent_intake.get("entries", [])
    )
    if len(entries) != expected_stress:
        errors.append(f"expected {expected_stress} stress regions, built {len(entries)}")

    document = {
        "schemaVersion": 1,
        "batchId": f"{parent_intake['batchId']}-stress-primary-regions-v1",
        "ok": not errors,
        "authorization": {
            "authorizedUses": sorted(REQUIRED_USES),
            "trainingUse": "prohibited",
            "inheritedFrom": parent_intake["batchId"],
        },
        "root": str(region_dir),
        "counts": {
            "parentStress": expected_stress,
            "derivedRegions": len(entries),
            "annotationPending": len(entries),
        },
        "status": "derived_region_intake_pass_annotation_pending" if not errors else "invalid",
        "errors": errors,
        "entries": entries,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output_path), **document["counts"], "ok": document["ok"]}, ensure_ascii=True))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
