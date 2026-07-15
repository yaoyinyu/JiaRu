#!/usr/bin/env python3
"""Freeze reviewed release-test candidates into a reproducible, isolated snapshot.

The resulting snapshot is evidence for a reviewed candidate set. It does not
declare the representative 100-image release gate satisfied and never enables
training use or production promotion.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from PIL import Image
from shapely.geometry import Polygon


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Freeze reviewed release-test candidates.")
    parser.add_argument("--parent-intake", required=True)
    parser.add_argument("--review-summary", required=True)
    parser.add_argument("--core-review", required=True)
    parser.add_argument("--core-image-dir", required=True)
    parser.add_argument("--core-annotations", required=True)
    parser.add_argument("--stress-intake", required=True)
    parser.add_argument("--stress-review", required=True)
    parser.add_argument("--stress-image-dir", required=True)
    parser.add_argument("--stress-annotations", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--minimum-representative-images", type=int, default=100)
    return parser


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def require_authorization(entry: dict[str, Any], file_name: str) -> None:
    uses = set(entry.get("authorizedUses", []))
    if "independent-release-test" not in uses:
        raise ValueError(f"{file_name}: independent-release-test authorization is missing")
    if entry.get("trainingUse") != "prohibited":
        raise ValueError(f"{file_name}: trainingUse must remain prohibited")


def safe_child(root: Path, file_name: str) -> Path:
    path = (root / file_name).resolve()
    if path.parent != root or not path.is_file():
        raise ValueError(f"source file is missing or escapes its root: {file_name}")
    return path


def validate_annotation(
    annotation_path: Path,
    file_name: str,
    source_group: str,
    image_size: tuple[int, int],
) -> tuple[dict[str, Any], int]:
    document = load_json(annotation_path)
    image = document.get("image", {})
    if image.get("fileName") != file_name:
        raise ValueError(f"{file_name}: annotation fileName mismatch")
    if image.get("sourceGroup") != source_group:
        raise ValueError(f"{file_name}: annotation sourceGroup mismatch")
    dimensions = (int(image.get("width", 0)), int(image.get("height", 0)))
    if dimensions != image_size:
        raise ValueError(f"{file_name}: annotation dimensions mismatch")
    annotations = document.get("annotations", [])
    if not annotations:
        raise ValueError(f"{file_name}: annotation has no polygons")
    shapes: list[Polygon] = []
    width, height = image_size
    for index, annotation in enumerate(annotations, start=1):
        points = annotation.get("polygon", [])
        if len(points) < 3:
            raise ValueError(f"{file_name}: nail {index} has fewer than three points")
        coordinates = []
        for point in points:
            x = float(point["x"])
            y = float(point["y"])
            if not (0 <= x < width and 0 <= y < height):
                raise ValueError(f"{file_name}: nail {index} has an out-of-bounds point")
            coordinates.append((x, y))
        shape = Polygon(coordinates)
        if not shape.is_valid or shape.area <= 1:
            raise ValueError(f"{file_name}: nail {index} polygon is invalid")
        shapes.append(shape)
    for first_index, first in enumerate(shapes):
        for second_index in range(first_index + 1, len(shapes)):
            overlap = first.intersection(shapes[second_index]).area
            if overlap > 0:
                raise ValueError(
                    f"{file_name}: nails {first_index + 1} and {second_index + 1} overlap by {overlap:.4f} pixels"
                )
    return document, len(annotations)


def review_passes(review: dict[str, Any], label: str) -> list[str]:
    if not review.get("ok"):
        raise ValueError(f"{label} review report is not ok")
    counts = review.get("counts", {})
    if int(counts.get("rework", -1)) != 0:
        raise ValueError(f"{label} review still contains rework items")
    return list(review.get("passFiles", []))


def build_record(
    *,
    lane: str,
    file_name: str,
    intake_entry: dict[str, Any],
    image_dir: Path,
    annotation_dir: Path,
) -> tuple[dict[str, Any], Path, Path]:
    require_authorization(intake_entry, file_name)
    image_path = safe_child(image_dir, file_name)
    actual_image_sha256 = sha256_path(image_path)
    if actual_image_sha256 != intake_entry.get("sha256"):
        raise ValueError(f"{file_name}: image SHA-256 drift")
    with Image.open(image_path) as image:
        image_size = image.size
        image.verify()
    annotation_path = safe_child(annotation_dir, f"{Path(file_name).stem}.json")
    source_group = str(intake_entry.get("sourceGroup") or "")
    _, mask_count = validate_annotation(annotation_path, file_name, source_group, image_size)
    annotation_sha256 = sha256_path(annotation_path)
    parent_file_name = str(intake_entry.get("parentFileName") or file_name)
    parent_source_group = str(intake_entry.get("parentSourceGroup") or source_group)
    record = {
        "lane": lane,
        "fileName": file_name,
        "parentFileName": parent_file_name,
        "sourceGroup": source_group,
        "parentSourceGroup": parent_source_group,
        "imageSha256": actual_image_sha256,
        "annotationSha256": annotation_sha256,
        "imageAnnotationPairSha256": canonical_sha256(
            {"imageSha256": actual_image_sha256, "annotationSha256": annotation_sha256}
        ),
        "width": image_size[0],
        "height": image_size[1],
        "maskCount": mask_count,
        "authorizedUses": sorted(intake_entry.get("authorizedUses", [])),
        "trainingUse": "prohibited",
    }
    if lane == "stress":
        record.update(
            {
                "parentSha256": intake_entry.get("parentSha256"),
                "regionId": intake_entry.get("regionId"),
                "normalizedBox": intake_entry.get("normalizedBox"),
            }
        )
    return record, image_path, annotation_path


def main() -> None:
    args = build_parser().parse_args()
    report_path = Path(args.report).resolve()
    output_root = Path(args.output_root).resolve()
    errors: list[str] = []
    records: list[dict[str, Any]] = []
    copy_inputs: list[tuple[str, Path, Path]] = []
    manifest_path = output_root / "manifest.json"

    try:
        if args.minimum_representative_images < 1:
            raise ValueError("minimum-representative-images must be positive")
        if output_root.exists():
            raise ValueError(f"output-root already exists: {output_root}")
        parent_intake = load_json(Path(args.parent_intake).resolve())
        summary = load_json(Path(args.review_summary).resolve())
        core_review = load_json(Path(args.core_review).resolve())
        stress_intake = load_json(Path(args.stress_intake).resolve())
        stress_review = load_json(Path(args.stress_review).resolve())
        if not parent_intake.get("ok") or not summary.get("ok") or not stress_intake.get("ok"):
            raise ValueError("an intake or parent summary is not ok")
        require_authorization(parent_intake.get("authorization", {}), "parent-intake")

        parent_entries = {entry["fileName"]: entry for entry in parent_intake.get("entries", [])}
        stress_entries = {entry["fileName"]: entry for entry in stress_intake.get("entries", [])}
        core_pass_files = review_passes(core_review, "core")
        stress_pass_files = review_passes(stress_review, "stress")
        core_image_dir = Path(args.core_image_dir).resolve()
        core_annotation_dir = Path(args.core_annotations).resolve()
        stress_image_dir = Path(args.stress_image_dir).resolve()
        stress_annotation_dir = Path(args.stress_annotations).resolve()

        for file_name in core_pass_files:
            try:
                entry = parent_entries.get(file_name)
                if entry is None or entry.get("decision") != "core":
                    raise ValueError(f"{file_name}: reviewed core file is missing from core intake")
                record, image_path, annotation_path = build_record(
                    lane="core",
                    file_name=file_name,
                    intake_entry=entry,
                    image_dir=core_image_dir,
                    annotation_dir=core_annotation_dir,
                )
                records.append(record)
                copy_inputs.append(("core", image_path, annotation_path))
            except Exception as error:
                errors.append(str(error))

        for file_name in stress_pass_files:
            try:
                entry = stress_entries.get(file_name)
                if entry is None or entry.get("decision") != "core":
                    raise ValueError(f"{file_name}: reviewed stress file is missing from derived intake")
                record, image_path, annotation_path = build_record(
                    lane="stress",
                    file_name=file_name,
                    intake_entry=entry,
                    image_dir=stress_image_dir,
                    annotation_dir=stress_annotation_dir,
                )
                records.append(record)
                copy_inputs.append(("stress", image_path, annotation_path))
            except Exception as error:
                errors.append(str(error))

        if errors:
            raise ValueError("candidate validation failed")

        records.sort(key=lambda item: (item["parentFileName"], item["lane"], item["fileName"]))
        parent_files = [record["parentFileName"] for record in records]
        if len(parent_files) != len(set(parent_files)):
            raise ValueError("multiple frozen records map to the same parent image")
        if sorted(parent_files) != sorted(summary.get("passParentFiles", [])):
            raise ValueError("frozen parent set does not match reviewed parent summary")
        counts = summary.get("counts", {})
        mask_count = sum(record["maskCount"] for record in records)
        parent_groups = {record["parentSourceGroup"] for record in records}
        if len(records) != int(counts.get("pass", -1)):
            raise ValueError("frozen image count does not match parent summary")
        if mask_count != int(counts.get("acceptedMasks", -1)):
            raise ValueError("frozen mask count does not match parent summary")
        if len(parent_groups) != int(counts.get("acceptedSourceGroups", -1)):
            raise ValueError("frozen parent source-group count does not match parent summary")
        if len(core_pass_files) != int(core_review["counts"]["pass"]):
            raise ValueError("core pass count mismatch")
        if len(stress_pass_files) != int(stress_review["counts"]["pass"]):
            raise ValueError("stress pass count mismatch")

        for lane, image_path, annotation_path in copy_inputs:
            image_output = output_root / "images" / lane / image_path.name
            annotation_output = output_root / "annotations" / lane / annotation_path.name
            image_output.parent.mkdir(parents=True, exist_ok=True)
            annotation_output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(image_path, image_output)
            shutil.copy2(annotation_path, annotation_output)

        manifest = {
            "schemaVersion": 1,
            "snapshotId": "real-release-test-2026-07-13-reviewed-candidate-v1",
            "decision": "frozen_reviewed_candidate_not_release_ready",
            "trainingUse": "prohibited",
            "counts": {
                "images": len(records),
                "masks": mask_count,
                "coreImages": len(core_pass_files),
                "stressImages": len(stress_pass_files),
                "parentSourceGroups": len(parent_groups),
            },
            "representativeReleaseGate": {
                "ok": len(records) >= args.minimum_representative_images,
                "actual": len(records),
                "required": args.minimum_representative_images,
                "shortfall": max(0, args.minimum_representative_images - len(records)),
            },
            "itemsSha256": canonical_sha256(records),
            "items": records,
        }
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        if sha256_path(manifest_path) == "":
            raise ValueError("manifest hashing failed")
    except Exception as error:
        if str(error) != "candidate validation failed":
            errors.append(str(error))

    report = {
        "ok": not errors,
        "decision": "frozen_reviewed_candidate_not_release_ready" if not errors else "freeze_failed",
        "outputRoot": str(output_root),
        "manifestPath": str(manifest_path),
        "counts": {
            "images": len(records),
            "masks": sum(record["maskCount"] for record in records),
            "coreImages": sum(record["lane"] == "core" for record in records),
            "stressImages": sum(record["lane"] == "stress" for record in records),
        },
        "representativeReleaseGate": {
            "ok": len(records) >= args.minimum_representative_images,
            "actual": len(records),
            "required": args.minimum_representative_images,
            "shortfall": max(0, args.minimum_representative_images - len(records)),
        },
        "errors": errors,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
