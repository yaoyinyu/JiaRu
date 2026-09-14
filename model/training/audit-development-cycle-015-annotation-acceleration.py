from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.tmp-", dir=path.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def build(args: argparse.Namespace) -> dict[str, Any]:
    inputs = {
        "yoloVisualDecision": Path(args.yolo_visual_decision).resolve(),
        "samReport": Path(args.sam_report).resolve(),
        "samGeometry": Path(args.sam_geometry).resolve(),
        "samVisualDecision": Path(args.sam_visual_decision).resolve(),
        "residualManualReport": Path(args.residual_manual_report).resolve(),
        "finalCandidateReport": Path(args.final_candidate_report).resolve(),
        "finalGeometry": Path(args.final_geometry).resolve(),
        "maskReviewFinal": Path(args.mask_review_final).resolve(),
        "developmentTruthIndex": Path(args.development_truth_index).resolve(),
        "roleManifest": Path(args.role_manifest).resolve(),
        "invalidatedTrainAttempt": Path(args.invalidated_train_attempt).resolve(),
    }
    errors: list[str] = []
    documents: dict[str, dict[str, Any]] = {}
    for label, path in inputs.items():
        if not path.is_file():
            errors.append(f"{label} is missing: {path}")
            continue
        try:
            documents[label] = read_json(path)
        except (OSError, json.JSONDecodeError) as error:
            errors.append(f"{label} is unreadable: {error}")

    if errors:
        return {"schemaVersion": 1, "ok": False, "decision": "reject_annotation_acceleration_evidence", "errors": errors}

    yolo = documents["yoloVisualDecision"]
    sam = documents["samReport"]
    sam_geometry = documents["samGeometry"]
    sam_review = documents["samVisualDecision"]
    residual = documents["residualManualReport"]
    final_candidate = documents["finalCandidateReport"]
    final_geometry = documents["finalGeometry"]
    mask_review = documents["maskReviewFinal"]
    truth_index = documents["developmentTruthIndex"]
    role_manifest = documents["roleManifest"]
    invalidation = documents["invalidatedTrainAttempt"]

    require(yolo.get("ok") is True and yolo.get("decision") == "all_45_yolo_masks_rejected_for_boundary_rework", "YOLO boundary-review decision mismatch", errors)
    require(yolo.get("review", {}).get("reviewedNails") == 45 and yolo.get("review", {}).get("accepted") == 0 and yolo.get("review", {}).get("rework") == 45, "YOLO 0/45 baseline mismatch", errors)
    sam_polygon_count = sum(int(item.get("polygonCount", 0)) for item in sam.get("outputs", []))
    require(sam.get("ok") is True and sam.get("imageCount") == 9 and sam.get("promptCount") == 45 and sam_polygon_count == 45, "PCA multipoint SAM count mismatch", errors)
    require(sam.get("boxOnlyFallbackPromptCount") == 0 and sam.get("errors") == [], "PCA multipoint SAM used fallback or reported errors", errors)
    sam_geometry_counts = sam_geometry.get("summary", {}).get("cycle015-nine-image-sam21l-pca-multipoint-v1", {})
    require(sam_geometry_counts == {"pass": 45, "suspect": 0, "missing": 0}, "PCA multipoint SAM geometry mismatch", errors)
    require(sam_review.get("ok") is True and sam_review.get("review", {}).get("accepted") == 44 and sam_review.get("review", {}).get("rework") == 1, "PCA multipoint SAM visual-review result mismatch", errors)
    require(residual.get("ok") is True and residual.get("imageCount") == 1 and residual.get("polygonCount") == 5 and residual.get("manualPolygonCount") == 1 and residual.get("pairwiseOverlapCount") == 0, "residual manual repair mismatch", errors)
    require(final_candidate.get("ok") is True and final_candidate.get("imageCount") == 13 and final_candidate.get("polygonCount") == 85 and final_candidate.get("pairwiseOverlapCount") == 0, "final candidate batch mismatch", errors)
    final_geometry_counts = final_geometry.get("summary", {}).get("cycle015-final-candidate-v1", {})
    require(final_geometry_counts == {"pass": 85, "suspect": 0, "missing": 0}, "final geometry audit mismatch", errors)
    require(mask_review.get("ok") is True and mask_review.get("counts") == {"images": 13, "exclude": 0, "pass": 13, "rework": 0}, "final original-resolution review mismatch", errors)
    require(truth_index.get("ok") is True and truth_index.get("decision") == "approved_unique_development_evaluation_truth_index", "development-evaluation truth index mismatch", errors)
    require(truth_index.get("inputs", {}).get("truthRole") == "development-evaluation" and truth_index.get("policy", {}).get("trainingUse") == "prohibited", "development-evaluation role was not preserved", errors)
    require(truth_index.get("summary", {}).get("uniqueImageCount") == 13 and truth_index.get("summary", {}).get("completeMaskCount") == 85 and truth_index.get("summary", {}).get("conflictingImageCount") == 0, "development-evaluation truth totals mismatch", errors)
    role_items = role_manifest.get("items", [])
    require(role_manifest.get("ok") is True and len(role_items) == 13 and all(item.get("assignedRole") == "development-evaluation-extension" and item.get("trainingUse") == "prohibited" for item in role_items), "frozen development-evaluation role manifest mismatch", errors)
    require(invalidation.get("decision") == "invalidated_role_mismatch_evidence_preserved" and invalidation.get("policy", {}).get("artifactsMustNotBeUsedForTraining") is True, "invalid train-role attempt was not preserved and rejected", errors)

    reviewed = 45
    accepted = 44
    residual_manual = 1
    result = {
        "schemaVersion": 1,
        "ok": not errors,
        "decision": (
            "adopt_pca_multipoint_sam_for_exact_count_candidates_residual_manual_only"
            if not errors
            else "reject_annotation_acceleration_evidence"
        ),
        "inputs": {label: {"path": str(path), "sha256": sha256_file(path)} for label, path in inputs.items()},
        "scope": "nine exact-count images only; multi-hand count-mismatch cases retain the reviewed hybrid repair path",
        "metrics": {
            "images": 9,
            "nails": reviewed,
            "directYoloAccepted": 0,
            "directYoloRework": 45,
            "pcaMultipointSamAccepted": accepted,
            "residualManualNails": residual_manual,
            "pcaMultipointSamAcceptanceRate": accepted / reviewed,
            "manualBoundaryInterventionsAvoided": 44,
            "manualBoundaryInterventionReductionRate": 44 / reviewed,
            "finalBatchImages": 13,
            "finalBatchMasks": 85,
        },
        "policy": {
            "originalResolutionReviewStillRequired": True,
            "geometryAuditDoesNotReplaceVisualReview": True,
            "developmentEvaluationTrainingUse": "prohibited",
            "protectedRolesUnchanged": True,
            "releaseState": "hold",
            "productState": "hold",
        },
        "errors": errors,
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay the cycle015 annotation acceleration evidence.")
    for name in (
        "yolo-visual-decision", "sam-report", "sam-geometry", "sam-visual-decision",
        "residual-manual-report", "final-candidate-report", "final-geometry",
        "mask-review-final", "development-truth-index", "role-manifest",
        "invalidated-train-attempt",
    ):
        parser.add_argument(f"--{name}", required=False)
    parser.add_argument("--output")
    parser.add_argument("--verify-report")
    args = parser.parse_args()
    if args.verify_report:
        expected_path = Path(args.verify_report).resolve()
        expected = read_json(expected_path)
        for key, value in expected.get("inputs", {}).items():
            setattr(args, {
                "yoloVisualDecision": "yolo_visual_decision",
                "samReport": "sam_report",
                "samGeometry": "sam_geometry",
                "samVisualDecision": "sam_visual_decision",
                "residualManualReport": "residual_manual_report",
                "finalCandidateReport": "final_candidate_report",
                "finalGeometry": "final_geometry",
                "maskReviewFinal": "mask_review_final",
                "developmentTruthIndex": "development_truth_index",
                "roleManifest": "role_manifest",
                "invalidatedTrainAttempt": "invalidated_train_attempt",
            }[key], value["path"])
        actual = build(args)
        if actual != expected:
            raise SystemExit("report differs from replay")
        print(json.dumps({"ok": True, "decision": actual["decision"], "reportSha256": sha256_file(expected_path)}, ensure_ascii=True))
        return
    missing = [name for name, value in vars(args).items() if name not in {"output", "verify_report"} and not value]
    if missing or not args.output:
        parser.error(f"all evidence arguments and --output are required; missing: {', '.join(missing)}")
    result = build(args)
    write_json_atomic(Path(args.output).resolve(), result)
    print(json.dumps({"ok": result["ok"], "decision": result["decision"], "metrics": result.get("metrics")}, ensure_ascii=True))
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
