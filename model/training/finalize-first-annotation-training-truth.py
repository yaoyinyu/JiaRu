from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
import tempfile
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


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def collect_existing_files(value: Any) -> set[Path]:
    paths: set[Path] = set()
    if isinstance(value, dict):
        for child in value.values():
            paths.update(collect_existing_files(child))
    elif isinstance(value, list):
        for child in value:
            paths.update(collect_existing_files(child))
    elif isinstance(value, str) and value:
        try:
            candidate = Path(value).resolve()
        except OSError:
            return paths
        if candidate.is_file():
            paths.add(candidate)
    return paths


def aliases(left: Path, right: Path) -> bool:
    if left.resolve() == right.resolve():
        return True
    if left.exists() and right.exists():
        try:
            return os.path.samefile(left, right)
        except OSError:
            return False
    return False


def ensure_safe_output(output_path: Path, protected_paths: set[Path]) -> None:
    for protected in protected_paths:
        if aliases(output_path, protected):
            raise ValueError(f"output must not overwrite input evidence: {protected}")


def evidence_hashes(paths: set[Path]) -> dict[str, str]:
    return {str(path.resolve()): sha256_file(path) for path in paths if path.is_file()}


def assert_evidence_unchanged(expected: dict[str, str]) -> None:
    for raw_path, expected_hash in expected.items():
        path = Path(raw_path)
        if not path.is_file() or sha256_file(path) != expected_hash:
            raise ValueError(f"input evidence changed while finalizing: {path}")


def write_json_atomic(output_path: Path, value: dict[str, Any], protected_paths: set[Path]) -> None:
    ensure_safe_output(output_path, protected_paths)
    snapshot = evidence_hashes(protected_paths)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.tmp-", dir=output_path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        assert_evidence_unchanged(snapshot)
        ensure_safe_output(output_path, protected_paths)
        os.replace(temporary, output_path)
        assert_evidence_unchanged(snapshot)
    finally:
        if temporary.exists():
            temporary.unlink()


def replay_release_visual_evidence(evidence_path: Path, evidence: dict[str, Any]) -> None:
    inputs = evidence.get("inputs", {})
    decision = evidence.get("decision")
    script_root = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix="release-truth-visual-replay-") as directory:
        replay_path = Path(directory) / "replayed.json"
        if decision == "mask_review_shard_complete_final_truth_audit_still_required":
            decisions_path = Path(str(inputs.get("decisions", ""))).resolve()
            if not decisions_path.is_file():
                raise ValueError("release-test visual evidence has no current decisions file")
            decisions = read_json(decisions_path)
            shard_index = decisions.get("shardIndex")
            command = [
                sys.executable,
                str(script_root / "finalize-first-annotation-mask-review-shard.py"),
                "--review-workspace",
                str(inputs.get("reviewWorkspace", "")),
                "--shard-index",
                str(shard_index),
                "--decisions",
                str(decisions_path),
                "--output",
                str(replay_path),
            ]
        elif decision == "mask_repair_review_complete_final_truth_audit_still_required":
            report_flag = "--manual-report" if inputs.get("manualReport") else "--sam-report"
            report_path = inputs.get("manualReport") or inputs.get("samReport") or ""
            command = [
                sys.executable,
                str(script_root / "finalize-first-annotation-mask-repair.py"),
                "--initial-shard-final",
                str(inputs.get("initialShardFinal", "")),
                "--file-name",
                str(evidence.get("item", {}).get("fileName", "")),
                "--repair-prompts",
                str(inputs.get("repairPrompts", "")),
                report_flag,
                str(report_path),
                "--geometry-audit",
                str(inputs.get("geometryAudit", "")),
                "--decision",
                str(inputs.get("decision", "")),
            ]
            if inputs.get("visualEvidence"):
                command.extend(["--visual-evidence", str(inputs.get("visualEvidence"))])
            command.extend(["--output", str(replay_path)])
        else:
            raise ValueError("unsupported release-test visual evidence state")
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0 or not replay_path.is_file():
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise ValueError(f"release-test visual evidence deep replay failed: {detail}")
        replayed = read_json(replay_path)
        if canonical_json(replayed) != canonical_json(evidence):
            raise ValueError("release-test visual evidence differs from deep replay")


def replay_release_role_manifest(role_manifest_path: Path) -> None:
    script = Path(__file__).resolve().parent / "build-release-test-annotation-workspace.py"
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--verify-workspace-manifest",
            str(role_manifest_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise ValueError(f"release-test role manifest deep replay failed: {detail}")
    try:
        verified = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ValueError(f"release-test role verifier returned invalid JSON: {error}") from error
    if (
        verified.get("ok") is not True
        or verified.get("decision") != "release_test_annotation_workspace_verified"
    ):
        raise ValueError("release-test role verifier did not approve the current workspace")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Approve one visually reviewed mask as a topology-safe train, validation, "
            "or independent release-test truth candidate."
        )
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
        choices=("train", "val", "release-test"),
        default="train",
        help="Finalize a training, source-isolated validation, or independent release-test truth candidate.",
    )
    parser.add_argument(
        "--role-manifest",
        help=(
            "Required for val and release-test; binds the image to an annotation workspace "
            "whose assignedRole matches --truth-role."
        ),
    )
    args = parser.parse_args()
    evidence_path = Path(args.repair_final or args.mask_review_final).resolve()
    image_path = Path(args.image).resolve()
    output_path = Path(args.output).resolve()
    protected_paths = {evidence_path, image_path}
    if args.annotation:
        protected_paths.add(Path(args.annotation).resolve())
    if args.role_manifest:
        protected_paths.add(Path(args.role_manifest).resolve())
    ensure_safe_output(output_path, {path for path in protected_paths if path.is_file()})
    errors: list[str] = []
    if not evidence_path.is_file():
        errors.append("visual review final report is missing")
    if not image_path.is_file():
        errors.append("source image is missing")
    if errors:
        write_json_atomic(output_path, {"ok": False, "errors": errors}, protected_paths)
        raise SystemExit(1)

    evidence = read_json(evidence_path)
    protected_paths.update(collect_existing_files(evidence))
    ensure_safe_output(output_path, protected_paths)
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
    role_required = args.truth_role in {"val", "release-test"}
    expected_assigned_role = "val" if args.truth_role == "val" else "independent-release-test"
    if role_required:
        if role_manifest_path is None:
            errors.append(f"--role-manifest is required for {args.truth_role} truth")
        elif not role_manifest_path.is_file():
            errors.append(f"{args.truth_role} role manifest is missing")
        else:
            role_manifest = read_json(role_manifest_path)
            protected_paths.update(collect_existing_files(role_manifest))
            ensure_safe_output(output_path, protected_paths)
            if role_manifest.get("ok") is not True or role_manifest.get("decision") != "annotation_workspace_ready_candidate_only":
                errors.append(f"{args.truth_role} role manifest is not an approved annotation workspace")
            policy = role_manifest.get("policy", {})
            if (
                policy.get("selectionMode") != expected_assigned_role
                or policy.get("assignedRole") != expected_assigned_role
            ):
                errors.append(
                    "role manifest is not restricted to "
                    f"assignedRole={expected_assigned_role}"
                )
            role_items = [
                candidate
                for candidate in role_manifest.get("items", [])
                if candidate.get("fileName") == image_path.name
            ]
            if len(role_items) != 1:
                errors.append(
                    f"{args.truth_role} role manifest must contain exactly one matching image"
                )
            else:
                role_item = role_items[0]
                if (
                    role_item.get("sha256") != item.get("sha256")
                    or role_item.get("sourceGroup") != item.get("sourceGroup")
                    or role_item.get("assignedRole") != expected_assigned_role
                    or role_item.get("trainingUse") != "prohibited"
                    or int(role_item.get("expectedFullyVisibleNails", -1)) != item.get("expectedFullyVisibleNails")
                ):
                    errors.append(
                        f"{args.truth_role} role identity, expected count, or training prohibition differs"
                    )

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

    if args.truth_role == "release-test" and not errors:
        try:
            replay_release_visual_evidence(evidence_path, evidence)
            if role_manifest_path is None:
                raise ValueError("release-test role manifest is required for deep replay")
            replay_release_role_manifest(role_manifest_path)
        except (OSError, ValueError) as error:
            errors.append(str(error))

    if errors:
        rejected_role = "release_test" if args.truth_role == "release-test" else args.truth_role
        result = {"ok": False, "decision": f"reject_{rejected_role}_truth_candidate", "errors": errors}
        write_json_atomic(output_path, result, protected_paths)
        raise SystemExit(1)

    is_validation = args.truth_role == "val"
    is_release_test = args.truth_role == "release-test"
    truth_label = "validation" if is_validation else "release_test" if is_release_test else "training"
    decision_suffix = (
        "pending_snapshot_freeze"
        if is_release_test
        else "pending_dataset_materialization"
    )
    training_use = (
        "prohibited" if is_validation or is_release_test else "prohibited-until-materialization-audit"
    )
    result = {
        "schemaVersion": 1,
        "ok": True,
        "decision": f"approved_as_{truth_label}_truth_candidate_{decision_suffix}",
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
            "datasetMaterializationAndSourceIsolationStillRequired": not is_release_test,
            "snapshotFreezeAndSourceIsolationStillRequired": is_release_test,
            "trainingUse": training_use,
            "validationUse": "prohibited-until-materialization-audit" if is_validation else None,
            "evaluationUse": "prohibited-until-snapshot-freeze" if is_release_test else None,
        },
        "item": {
            "fileName": item["fileName"],
            "sha256": item["sha256"],
            "sourceGroup": item["sourceGroup"],
            "completeMaskCount": len(polygons),
            "invalidPolygonCount": 0,
            "overlapPairCount": 0,
            "annotationTruthStatus": (
                "approved-as-release-test-truth-candidate"
                if is_release_test
                else f"approved-as-{truth_label}-truth-candidate"
            ),
            "trainingUse": training_use,
            "validationUse": "prohibited-until-materialization-audit" if is_validation else None,
            "evaluationUse": "prohibited-until-snapshot-freeze" if is_release_test else None,
        },
        "errors": [],
    }
    write_json_atomic(output_path, result, protected_paths)
    print(json.dumps({"ok": True, "fileName": item["fileName"], "completeMaskCount": len(polygons)}, ensure_ascii=True))


if __name__ == "__main__":
    main()
