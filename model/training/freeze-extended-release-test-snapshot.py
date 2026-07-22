#!/usr/bin/env python3
"""Merge a reviewed frozen release-test snapshot with finalized supplemental truth.

The output remains evaluation-only and training-prohibited.  The tool deeply
replays file hashes, polygon topology and train/val/release source isolation
before copying any files into a new immutable snapshot directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image
from shapely.geometry import Polygon


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Freeze an extended source-isolated release-test snapshot.")
    result.add_argument("--base-snapshot", required=True)
    result.add_argument("--supplemental-truth-index", required=True)
    result.add_argument("--train-truth-index", required=True)
    result.add_argument("--validation-truth-index", required=True)
    result.add_argument("--output-root", required=True)
    result.add_argument("--report", required=True)
    result.add_argument("--minimum-representative-images", type=int, default=100)
    return result


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


def safe_file(path: Path, label: str) -> Path:
    resolved = path.resolve()
    if not resolved.is_file():
        raise ValueError(f"{label} is missing: {resolved}")
    return resolved


def validate_annotation(
    annotation_path: Path,
    file_name: str,
    source_group: str,
    image_size: tuple[int, int],
) -> tuple[int, str]:
    document = load_json(annotation_path)
    image = document.get("image", {})
    if image.get("fileName") != file_name:
        raise ValueError(f"{file_name}: annotation fileName mismatch")
    if image.get("sourceGroup") != source_group:
        raise ValueError(f"{file_name}: annotation sourceGroup mismatch")
    if (int(image.get("width", 0)), int(image.get("height", 0))) != image_size:
        raise ValueError(f"{file_name}: annotation dimensions mismatch")
    annotations = document.get("annotations", [])
    if not annotations:
        raise ValueError(f"{file_name}: annotation has no polygons")
    width, height = image_size
    shapes: list[Polygon] = []
    for index, annotation in enumerate(annotations, start=1):
        points = annotation.get("polygon", [])
        if len(points) < 3:
            raise ValueError(f"{file_name}: nail {index} has fewer than three points")
        coordinates = [(float(point["x"]), float(point["y"])) for point in points]
        if any(not (0 <= x < width and 0 <= y < height) for x, y in coordinates):
            raise ValueError(f"{file_name}: nail {index} has an out-of-bounds point")
        shape = Polygon(coordinates)
        if not shape.is_valid or shape.area <= 1:
            raise ValueError(f"{file_name}: nail {index} polygon is invalid")
        shapes.append(shape)
    for first_index, first in enumerate(shapes):
        for second_index in range(first_index + 1, len(shapes)):
            overlap = first.intersection(shapes[second_index]).area
            if overlap > 0:
                raise ValueError(
                    f"{file_name}: nails {first_index + 1} and {second_index + 1} "
                    f"overlap by {overlap:.4f} pixels"
                )
    return len(annotations), sha256_path(annotation_path)


def validate_truth_index(path: Path, role: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    document = load_json(path)
    if not document.get("ok"):
        raise ValueError(f"{role} truth index is not ok")
    summary = document.get("summary", {})
    if int(summary.get("conflictingImageCount", -1)) != 0 or document.get("conflicts"):
        raise ValueError(f"{role} truth index contains conflicts")
    truths = list(document.get("canonicalTruths", []))
    if len(truths) != int(summary.get("uniqueImageCount", -1)):
        raise ValueError(f"{role} truth index unique image count mismatch")
    return document, truths


def identity_sets(records: list[dict[str, Any]]) -> dict[str, set[str]]:
    return {
        "fileName": {str(item["fileName"]) for item in records},
        "imageSha256": {str(item["imageSha256"]) for item in records},
        "sourceGroup": {
            str(group)
            for item in records
            for group in (item.get("sourceGroup"), item.get("parentSourceGroup"))
            if group
        },
    }


def assert_disjoint(left: dict[str, set[str]], right: dict[str, set[str]], label: str) -> None:
    for key in ("fileName", "imageSha256", "sourceGroup"):
        overlap = sorted(left[key] & right[key])
        if overlap:
            raise ValueError(f"{label} {key} overlap: {overlap[:3]}")


def validate_base_snapshot(manifest_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[tuple[Path, Path]]]:
    manifest = load_json(manifest_path)
    if manifest.get("trainingUse") != "prohibited":
        raise ValueError("base snapshot trainingUse must be prohibited")
    records = list(manifest.get("items", []))
    if len(records) != int(manifest.get("counts", {}).get("images", -1)):
        raise ValueError("base snapshot image count mismatch")
    if canonical_sha256(records) != manifest.get("itemsSha256"):
        raise ValueError("base snapshot itemsSha256 drift")
    root = manifest_path.parent
    copy_inputs: list[tuple[Path, Path]] = []
    masks = 0
    for record in records:
        file_name = str(record["fileName"])
        lane = str(record["lane"])
        if record.get("trainingUse") != "prohibited":
            raise ValueError(f"{file_name}: base item trainingUse must be prohibited")
        image_path = safe_file(root / "images" / lane / file_name, f"{file_name} base image")
        annotation_path = safe_file(
            root / "annotations" / lane / f"{Path(file_name).stem}.json",
            f"{file_name} base annotation",
        )
        if sha256_path(image_path) != record.get("imageSha256"):
            raise ValueError(f"{file_name}: base image SHA-256 drift")
        with Image.open(image_path) as image:
            size = image.size
            image.verify()
        count, annotation_sha = validate_annotation(
            annotation_path, file_name, str(record["sourceGroup"]), size
        )
        if annotation_sha != record.get("annotationSha256") or count != int(record.get("maskCount", -1)):
            raise ValueError(f"{file_name}: base annotation evidence drift")
        pair_sha = canonical_sha256({"imageSha256": record["imageSha256"], "annotationSha256": annotation_sha})
        if pair_sha != record.get("imageAnnotationPairSha256"):
            raise ValueError(f"{file_name}: base image/annotation pair hash drift")
        masks += count
        copy_inputs.append((image_path, annotation_path))
    if masks != int(manifest.get("counts", {}).get("masks", -1)):
        raise ValueError("base snapshot mask count mismatch")
    return manifest, records, copy_inputs


def validate_supplemental_truths(
    truths: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[tuple[Path, Path]]]:
    records: list[dict[str, Any]] = []
    copy_inputs: list[tuple[Path, Path]] = []
    for truth in truths:
        file_name = str(truth["fileName"])
        report_path = safe_file(Path(str(truth["reportPath"])), f"{file_name} truth report")
        if sha256_path(report_path) != truth.get("reportSha256"):
            raise ValueError(f"{file_name}: truth report SHA-256 drift")
        report = load_json(report_path)
        item = report.get("item", {})
        inputs = report.get("inputs", {})
        policy = report.get("policy", {})
        if not report.get("ok") or report.get("decision") != "approved_as_release_test_truth_candidate_pending_snapshot_freeze":
            raise ValueError(f"{file_name}: truth report is not approved for release-test freeze")
        if inputs.get("truthRole") != "release-test" or policy.get("targetRole") != "release-test":
            raise ValueError(f"{file_name}: truth role mismatch")
        if item.get("trainingUse") != "prohibited" or policy.get("trainingUse") != "prohibited":
            raise ValueError(f"{file_name}: trainingUse must remain prohibited")
        image_path = safe_file(Path(str(inputs["image"])), f"{file_name} supplemental image")
        annotation_path = safe_file(Path(str(inputs["annotation"])), f"{file_name} supplemental annotation")
        image_sha = sha256_path(image_path)
        annotation_sha = sha256_path(annotation_path)
        expected = {
            "fileName": file_name,
            "imageSha256": image_sha,
            "sourceGroup": str(item["sourceGroup"]),
            "completeMaskCount": int(item["completeMaskCount"]),
            "annotationPath": str(annotation_path),
            "annotationSha256": annotation_sha,
        }
        for key, value in expected.items():
            truth_value = str(Path(str(truth[key])).resolve()) if key == "annotationPath" else truth.get(key)
            expected_value = str(Path(str(value)).resolve()) if key == "annotationPath" else value
            if truth_value != expected_value:
                raise ValueError(f"{file_name}: supplemental truth {key} drift")
        if inputs.get("imageSha256") != image_sha or inputs.get("annotationSha256") != annotation_sha:
            raise ValueError(f"{file_name}: truth input hash drift")
        with Image.open(image_path) as image:
            size = image.size
            image.verify()
        mask_count, checked_annotation_sha = validate_annotation(
            annotation_path, file_name, str(item["sourceGroup"]), size
        )
        if mask_count != int(item["completeMaskCount"]) or checked_annotation_sha != annotation_sha:
            raise ValueError(f"{file_name}: supplemental annotation evidence drift")
        record = {
            "lane": "core",
            "fileName": file_name,
            "parentFileName": file_name,
            "sourceGroup": str(item["sourceGroup"]),
            "parentSourceGroup": str(item["sourceGroup"]),
            "imageSha256": image_sha,
            "annotationSha256": annotation_sha,
            "imageAnnotationPairSha256": canonical_sha256(
                {"imageSha256": image_sha, "annotationSha256": annotation_sha}
            ),
            "width": size[0],
            "height": size[1],
            "maskCount": mask_count,
            "authorizedUses": ["independent-release-test", "long-term-regression"],
            "trainingUse": "prohibited",
            "provenanceLane": "supplemental-release-test-truth",
            "truthReportSha256": truth["reportSha256"],
        }
        records.append(record)
        copy_inputs.append((image_path, annotation_path))
    return records, copy_inputs


def main() -> None:
    args = parser().parse_args()
    report_path = Path(args.report).resolve()
    output_root = Path(args.output_root).resolve()
    staging_root: Path | None = None
    errors: list[str] = []
    counts: dict[str, int] = {}
    manifest_sha256: str | None = None
    try:
        if args.minimum_representative_images < 1:
            raise ValueError("minimum-representative-images must be positive")
        if output_root.exists():
            raise ValueError(f"output-root already exists: {output_root}")
        base_path = safe_file(Path(args.base_snapshot), "base snapshot")
        supplemental_path = safe_file(Path(args.supplemental_truth_index), "supplemental truth index")
        train_path = safe_file(Path(args.train_truth_index), "train truth index")
        validation_path = safe_file(Path(args.validation_truth_index), "validation truth index")
        base_manifest, base_records, base_inputs = validate_base_snapshot(base_path)
        supplemental_index, supplemental_truths = validate_truth_index(supplemental_path, "supplemental release-test")
        _, train_truths = validate_truth_index(train_path, "train")
        _, validation_truths = validate_truth_index(validation_path, "validation")
        supplemental_records, supplemental_inputs = validate_supplemental_truths(supplemental_truths)
        base_identity = identity_sets(base_records)
        supplemental_identity = identity_sets(supplemental_records)
        train_identity = identity_sets(train_truths)
        validation_identity = identity_sets(validation_truths)
        assert_disjoint(base_identity, supplemental_identity, "base/supplemental release-test")
        release_identity = identity_sets(base_records + supplemental_records)
        assert_disjoint(train_identity, validation_identity, "train/validation")
        assert_disjoint(train_identity, release_identity, "train/release-test")
        assert_disjoint(validation_identity, release_identity, "validation/release-test")
        records = sorted(base_records + supplemental_records, key=lambda item: (item["lane"], item["fileName"]))
        if len(records) != len({item["fileName"] for item in records}):
            raise ValueError("combined release-test contains duplicate file names")
        masks = sum(int(item["maskCount"]) for item in records)
        counts = {
            "images": len(records),
            "masks": masks,
            "baseImages": len(base_records),
            "supplementalImages": len(supplemental_records),
            "coreImages": sum(item["lane"] == "core" for item in records),
            "stressImages": sum(item["lane"] == "stress" for item in records),
            "sourceGroups": len({item["sourceGroup"] for item in records}),
            "parentSourceGroups": len({item["parentSourceGroup"] for item in records}),
            "sourceIdentityGroups": len(release_identity["sourceGroup"]),
        }
        gate = {
            "ok": len(records) >= args.minimum_representative_images,
            "actual": len(records),
            "required": args.minimum_representative_images,
            "shortfall": max(0, args.minimum_representative_images - len(records)),
        }
        output_root.parent.mkdir(parents=True, exist_ok=True)
        staging_root = Path(tempfile.mkdtemp(prefix=f".{output_root.name}-staging-", dir=output_root.parent))
        for record, (image_path, annotation_path) in zip(
            base_records + supplemental_records, base_inputs + supplemental_inputs, strict=True
        ):
            lane = str(record["lane"])
            image_output = staging_root / "images" / lane / image_path.name
            annotation_output = staging_root / "annotations" / lane / annotation_path.name
            image_output.parent.mkdir(parents=True, exist_ok=True)
            annotation_output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(image_path, image_output)
            shutil.copy2(annotation_path, annotation_output)
        manifest = {
            "schemaVersion": 2,
            "snapshotId": "real-release-test-reviewed-100-v2",
            "decision": "frozen_reviewed_candidate_not_release_ready",
            "trainingUse": "prohibited",
            "evaluationUse": "approved-for-source-isolated-frozen-evaluation",
            "inputs": {
                "baseSnapshot": str(base_path),
                "baseSnapshotSha256": sha256_path(base_path),
                "supplementalTruthIndex": str(supplemental_path),
                "supplementalTruthIndexSha256": sha256_path(supplemental_path),
                "trainTruthIndex": str(train_path),
                "trainTruthIndexSha256": sha256_path(train_path),
                "validationTruthIndex": str(validation_path),
                "validationTruthIndexSha256": sha256_path(validation_path),
            },
            "counts": counts,
            "representativeReleaseGate": gate,
            "sourceIsolation": {
                "ok": True,
                "identityKeys": ["fileName", "imageSha256", "sourceGroup", "parentSourceGroup"],
                "trainValidationOverlap": 0,
                "trainReleaseTestOverlap": 0,
                "validationReleaseTestOverlap": 0,
                "baseSupplementalOverlap": 0,
            },
            "itemsSha256": canonical_sha256(records),
            "aggregateSha256": {
                "items": canonical_sha256(records),
                "images": canonical_sha256(
                    [{"lane": item["lane"], "fileName": item["fileName"], "sha256": item["imageSha256"]} for item in records]
                ),
                "annotations": canonical_sha256(
                    [{"lane": item["lane"], "fileName": item["fileName"], "sha256": item["annotationSha256"]} for item in records]
                ),
                "imageAnnotationPairs": canonical_sha256(
                    [{"lane": item["lane"], "fileName": item["fileName"], "sha256": item["imageAnnotationPairSha256"]} for item in records]
                ),
            },
            "baseSnapshotId": base_manifest.get("snapshotId"),
            "supplementalTruthDecision": supplemental_index.get("decision"),
            "items": records,
        }
        manifest_path = staging_root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        manifest_sha256 = sha256_path(manifest_path)
        staging_root.replace(output_root)
        staging_root = None
    except Exception as error:
        errors.append(str(error))
        if staging_root is not None and staging_root.exists():
            shutil.rmtree(staging_root)
    report = {
        "ok": not errors,
        "decision": (
            "frozen_reviewed_representative_candidate_pending_model_quality" if not errors else "freeze_failed"
        ),
        "outputRoot": str(output_root),
        "manifestPath": str(output_root / "manifest.json"),
        "manifestSha256": manifest_sha256,
        "counts": counts,
        "representativeReleaseGate": {
            "ok": bool(counts) and counts.get("images", 0) >= args.minimum_representative_images,
            "actual": counts.get("images", 0),
            "required": args.minimum_representative_images,
            "shortfall": max(0, args.minimum_representative_images - counts.get("images", 0)),
        },
        "errors": errors,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
