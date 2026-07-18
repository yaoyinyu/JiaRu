from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from PIL import Image
from shapely.geometry import Polygon


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Approve one visually reviewed mask as a topology-safe training-truth candidate."
    )
    evidence_group = parser.add_mutually_exclusive_group(required=True)
    evidence_group.add_argument("--repair-final")
    evidence_group.add_argument("--mask-review-final")
    parser.add_argument(
        "--annotation",
        help="Required with --mask-review-final; its hash must match the bound shard row.",
    )
    parser.add_argument("--image", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--truth-role",
        choices=("train", "val"),
        default="train",
        help="Finalize a training or source-isolated validation truth candidate.",
    )
    parser.add_argument(
        "--role-manifest",
        help="Required for val; binds the image to an annotation workspace whose assignedRole is val.",
    )
    args = parser.parse_args()
    evidence_path = Path(args.repair_final or args.mask_review_final).resolve()
    image_path = Path(args.image).resolve()
    output_path = Path(args.output).resolve()
    errors: list[str] = []
    if not evidence_path.is_file():
        errors.append("visual review final report is missing")
    if not image_path.is_file():
        errors.append("source image is missing")
    if errors:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps({"ok": False, "errors": errors}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise SystemExit(1)

    evidence = read_json(evidence_path)
    evidence_type = "repair"
    if args.repair_final:
        item = evidence.get("item", {})
        if evidence.get("ok") is not True or evidence.get("decision") != "mask_repair_review_complete_final_truth_audit_still_required":
            errors.append("a passing hash-bound repair review is required")
        if item.get("reviewStatus") != "pass" or item.get("annotationTruthStatus") != "reviewed-repair-candidate-not-final-truth":
            errors.append("repair item has not passed original-resolution visual review")
        annotation_path = Path(str(evidence.get("inputs", {}).get("annotation", ""))).resolve()
        expected_annotation_hash = evidence.get("inputs", {}).get("annotationSha256")
    else:
        evidence_type = "direct-mask-review"
        matching_items = [
            candidate
            for candidate in evidence.get("items", [])
            if candidate.get("fileName") == image_path.name
        ]
        item = matching_items[0] if len(matching_items) == 1 else {}
        policy = evidence.get("policy", {})
        if (
            evidence.get("ok") is not True
            or evidence.get("decision") != "mask_review_shard_complete_final_truth_audit_still_required"
            or policy.get("originalResolutionReviewCompleted") is not True
        ):
            errors.append("a passing hash-bound original-resolution mask review is required")
        if len(matching_items) != 1:
            errors.append("mask review must contain exactly one item matching the source image")
        if (
            item.get("reviewStatus") != "pass"
            or item.get("annotationTruthStatus") != "reviewed-candidate-not-final-truth"
            or item.get("finalCompleteMaskCount") != item.get("expectedFullyVisibleNails")
        ):
            errors.append("direct-review item has not passed complete-mask original-resolution review")
        annotation_path = Path(args.annotation).resolve() if args.annotation else Path()
        expected_annotation_hash = None
        shard_path = Path(str(evidence.get("inputs", {}).get("shard", ""))).resolve()
        expected_shard_hash = evidence.get("inputs", {}).get("shardSha256")
        if not args.annotation:
            errors.append("--annotation is required with --mask-review-final")
        if not shard_path.is_file() or sha256_file(shard_path) != expected_shard_hash:
            errors.append("bound mask-review shard is missing or changed")
        else:
            with shard_path.open("r", encoding="utf-8-sig", newline="") as source:
                shard_rows = [row for row in csv.DictReader(source) if row.get("fileName") == image_path.name]
            if len(shard_rows) != 1:
                errors.append("bound shard must contain exactly one row matching the source image")
            else:
                shard_row = shard_rows[0]
                expected_annotation_hash = shard_row.get("annotationSha256")
                if (
                    shard_row.get("sha256") != item.get("sha256")
                    or shard_row.get("sourceGroup") != item.get("sourceGroup")
                    or int(shard_row.get("expectedFullyVisibleNails", "-1")) != item.get("expectedFullyVisibleNails")
                    or int(shard_row.get("candidateCount", "-1")) != item.get("candidateCount")
                ):
                    errors.append("direct-review item identity or counts differ from the bound shard")
    if sha256_file(image_path) != item.get("sha256") or image_path.name != item.get("fileName"):
        errors.append("source image identity or SHA-256 differs from the reviewed item")

    role_manifest_path = Path(args.role_manifest).resolve() if args.role_manifest else None
    if args.truth_role == "val":
        if role_manifest_path is None:
            errors.append("--role-manifest is required for validation truth")
        elif not role_manifest_path.is_file():
            errors.append("validation role manifest is missing")
        else:
            role_manifest = read_json(role_manifest_path)
            if role_manifest.get("ok") is not True or role_manifest.get("decision") != "annotation_workspace_ready_candidate_only":
                errors.append("validation role manifest is not an approved annotation workspace")
            policy = role_manifest.get("policy", {})
            if policy.get("selectionMode") != "val" or policy.get("assignedRole") != "val":
                errors.append("role manifest is not restricted to assignedRole=val")
            role_items = [
                candidate
                for candidate in role_manifest.get("items", [])
                if candidate.get("fileName") == image_path.name
            ]
            if len(role_items) != 1:
                errors.append("validation role manifest must contain exactly one matching image")
            else:
                role_item = role_items[0]
                if (
                    role_item.get("sha256") != item.get("sha256")
                    or role_item.get("sourceGroup") != item.get("sourceGroup")
                    or role_item.get("assignedRole") != "val"
                    or role_item.get("trainingUse") != "prohibited"
                    or int(role_item.get("expectedFullyVisibleNails", -1)) != item.get("expectedFullyVisibleNails")
                ):
                    errors.append("validation role identity, expected count, or training prohibition differs")

    if not annotation_path.is_file() or sha256_file(annotation_path) != expected_annotation_hash:
        errors.append("bound reviewed annotation is missing or changed")
        annotation: dict[str, Any] = {}
    else:
        annotation = read_json(annotation_path)
    if annotation:
        image_meta = annotation.get("image", {})
        with Image.open(image_path) as image:
            width, height = image.size
        if image_meta.get("width") != width or image_meta.get("height") != height:
            errors.append("annotation dimensions differ from the source image")
        if image_meta.get("fileName") != image_path.name or image_meta.get("sourceGroup") != item.get("sourceGroup"):
            errors.append("annotation image identity differs from the reviewed item")
        annotations = annotation.get("annotations", [])
        if len(annotations) != item.get("expectedFullyVisibleNails"):
            errors.append("annotation count differs from the reviewed expected nail count")
        polygons: list[Polygon] = []
        for index, annotation_item in enumerate(annotations, start=1):
            points = annotation_item.get("polygon", [])
            coords = [(float(point["x"]), float(point["y"])) for point in points if isinstance(point, dict) and "x" in point and "y" in point]
            polygon = Polygon(coords) if len(coords) >= 3 else Polygon()
            if polygon.is_empty or not polygon.is_valid or polygon.area <= 0:
                errors.append(f"nail {index} polygon has invalid topology")
            if any(x < 0 or x > width or y < 0 or y > height for x, y in coords):
                errors.append(f"nail {index} polygon is outside the source image")
            polygons.append(polygon)
        overlap_pairs: list[dict[str, Any]] = []
        for left in range(len(polygons)):
            for right in range(left + 1, len(polygons)):
                area = polygons[left].intersection(polygons[right]).area
                if area > 1e-6:
                    overlap_pairs.append({"left": left + 1, "right": right + 1, "intersectionArea": area})
        if overlap_pairs:
            errors.append(f"pairwise polygon overlap is not zero: {overlap_pairs}")
    else:
        polygons = []

    if errors:
        result = {"ok": False, "decision": f"reject_{args.truth_role}_truth_candidate", "errors": errors}
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise SystemExit(1)

    is_validation = args.truth_role == "val"
    truth_label = "validation" if is_validation else "training"
    result = {
        "schemaVersion": 1,
        "ok": True,
        "decision": f"approved_as_{truth_label}_truth_candidate_pending_dataset_materialization",
        "inputs": {
            "truthRole": args.truth_role,
            "visualReviewType": evidence_type,
            "visualReviewFinal": str(evidence_path),
            "visualReviewFinalSha256": sha256_file(evidence_path),
            "image": str(image_path),
            "imageSha256": sha256_file(image_path),
            "annotation": str(annotation_path),
            "annotationSha256": sha256_file(annotation_path),
            "roleManifest": str(role_manifest_path) if role_manifest_path else None,
            "roleManifestSha256": sha256_file(role_manifest_path) if role_manifest_path else None,
        },
        "policy": {
            "targetRole": args.truth_role,
            "originalResolutionVisualReviewRequired": True,
            "polygonTopologyMustBeValid": True,
            "pairwisePolygonIntersectionArea": 0,
            "datasetMaterializationAndSourceIsolationStillRequired": True,
            "trainingUse": "prohibited" if is_validation else "prohibited-until-materialization-audit",
            "validationUse": "prohibited-until-materialization-audit" if is_validation else None,
        },
        "item": {
            "fileName": item["fileName"],
            "sha256": item["sha256"],
            "sourceGroup": item["sourceGroup"],
            "completeMaskCount": len(polygons),
            "invalidPolygonCount": 0,
            "overlapPairCount": 0,
            "annotationTruthStatus": f"approved-as-{truth_label}-truth-candidate",
            "trainingUse": "prohibited" if is_validation else "prohibited-until-materialization-audit",
            "validationUse": "prohibited-until-materialization-audit" if is_validation else None,
        },
        "errors": [],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "fileName": item["fileName"], "completeMaskCount": len(polygons)}, ensure_ascii=True))


if __name__ == "__main__":
    main()
