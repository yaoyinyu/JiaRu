from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import datetime
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


def single_summary(report: dict[str, Any]) -> dict[str, Any]:
    values = list(report.get("summary", {}).values())
    return values[0] if len(values) == 1 and isinstance(values[0], dict) else {}


def checked_duration(report: dict[str, Any], stage: str, expected: float, errors: list[str]) -> float:
    require(report.get("stage") == stage, f"{stage} timing stage mismatch", errors)
    try:
        start = datetime.fromisoformat(str(report["startedAt"]))
        end = datetime.fromisoformat(str(report["endedAt"]))
        measured = (end - start).total_seconds()
        declared = float(report["durationSeconds"])
    except (KeyError, TypeError, ValueError):
        errors.append(f"{stage} timing is invalid")
        return 0.0
    require(abs(measured - declared) < 0.001 and abs(declared - expected) < 0.001, f"{stage} timing mismatch", errors)
    return declared


def build(args: argparse.Namespace) -> dict[str, Any]:
    argument_names = (
        "source_audit", "workspace", "prelabel_audit", "prompts", "sam", "sam_geometry",
        "sam_visual_decision", "targeted_sam", "targeted_sam_rejection", "detected_sam",
        "detected_sam_rejection", "rejected_final_v1", "rejected_final_v2", "rejected_final_v3",
        "final_candidate", "final_geometry", "mask_review_final", "truth_index", "prior_batch3_audit",
        "timing_prelabel", "timing_sam", "timing_targeted", "timing_final_review", "prelabel_script",
    )
    paths = {name: Path(getattr(args, name)).resolve() for name in argument_names}
    errors: list[str] = []
    documents: dict[str, dict[str, Any]] = {}
    for label, path in paths.items():
        if not path.is_file():
            errors.append(f"{label} is missing: {path}")
            continue
        if label != "prelabel_script":
            try:
                documents[label] = read_json(path)
            except (OSError, json.JSONDecodeError) as error:
                errors.append(f"{label} is unreadable: {error}")
    if errors:
        return {"schemaVersion": 1, "ok": False, "decision": "reject_batch4_annotation_acceleration", "errors": errors}

    source = documents["source_audit"]
    workspace = documents["workspace"]
    prelabel = documents["prelabel_audit"]
    prompts = documents["prompts"]
    sam = documents["sam"]
    sam_geometry = documents["sam_geometry"]
    visual = documents["sam_visual_decision"]
    targeted_sam = documents["targeted_sam"]
    targeted_rejection = documents["targeted_sam_rejection"]
    detected_sam = documents["detected_sam"]
    detected_rejection = documents["detected_sam_rejection"]
    final = documents["final_candidate"]
    final_geometry = documents["final_geometry"]
    review = documents["mask_review_final"]
    truth = documents["truth_index"]
    prior = documents["prior_batch3_audit"]

    require(source.get("ok") is True and source.get("decision") == "freeze_43_cumulative_source_qualified_candidates_continue_to_133", "source audit decision mismatch", errors)
    require(source.get("counts") == {"generatedImages": 44, "sourceQualifiedImages": 43, "sourceGroups": 43, "fullyVisibleNails": 265, "identityOrRoleOverlaps": 0, "targetSourceQualifiedImages": 133, "remainingSourceQualifiedImages": 90}, "source audit totals mismatch", errors)
    require(source.get("policy", {}).get("sourceGateDoesNotPermitTraining") is True and source.get("policy", {}).get("protectedOrConsumedDataReused") is False, "source role policy mismatch", errors)

    expected_workspace_counts = {"images": 10, "sourceGroups": 10, "shards": 10, "expectedFullyVisibleNails": 60, "truthFileNameOverlaps": 0, "truthImageSha256Overlaps": 0, "truthSourceGroupOverlaps": 0, "copiedImages": 10, "cumulativeSourceQualifiedImages": 43, "existingDevelopmentEvaluationTruthImages": 33, "pendingIncrementImages": 10}
    require(workspace.get("ok") is True and workspace.get("counts") == expected_workspace_counts, "workspace totals mismatch", errors)
    require(workspace.get("policy", {}).get("workspaceDoesNotGrantTrainingUse") is True and workspace.get("policy", {}).get("originalResolutionPerNailReviewRequired") is True, "workspace role policy mismatch", errors)

    expected_prelabel_counts = {"images": 10, "expectedFullyVisibleNails": 60, "candidates": 60, "cappedCountCoverage": 0.983333, "zeroCandidateImages": 0, "underCandidateImages": 1, "exactCandidateImages": 8, "overCandidateImages": 1, "duplicateOverlapPairs": 0, "machineErrors": 0}
    require(prelabel.get("ok") is True and prelabel.get("counts") == expected_prelabel_counts, "guarded prelabel audit mismatch", errors)
    require(prompts.get("imageCount") == 9 and prompts.get("promptCount") == 55 and prompts.get("trimmedOverpredictionCandidateCount") == 1, "PCA prompt totals mismatch", errors)
    require(len(prompts.get("skippedImages", [])) == 1 and prompts["skippedImages"][0].get("fileName") == "0040_masculine_olive_short_natural.png" and prompts["skippedImages"][0].get("expected") == 5 and prompts["skippedImages"][0].get("candidates") == 4, "undercount routing mismatch", errors)
    require(prompts.get("policy", {}).get("trainingUse") == "prohibited", "prompt role policy mismatch", errors)

    sam_polygons = sum(int(item.get("polygonCount", 0)) for item in sam.get("outputs", []))
    require(sam.get("ok") is True and sam.get("imageCount") == 9 and sam.get("promptCount") == 55 and sam_polygons == 55 and sam.get("errors") == [], "bulk SAM result mismatch", errors)
    require(single_summary(sam_geometry) == {"pass": 55, "suspect": 0, "missing": 0}, "bulk SAM geometry mismatch", errors)
    require(visual.get("ok") is True and visual.get("decision") == "sam_55_accepted_zero_residual_rework_for_nine_images" and visual.get("review") == {"method": "original-resolution full-image overlay and hash-bound 2x per-nail evidence", "reviewedImages": 9, "reviewedNails": 55, "accepted": 55, "rework": 0}, "bulk SAM original-resolution review mismatch", errors)
    require(visual.get("policy", {}).get("trimmedOverpredictionCandidateWasConfirmedAtOriginalResolutionAsNonNail") is True and visual.get("policy", {}).get("modelUndercoverageDidNotChangeTruthDenominator") is True, "count-protection review mismatch", errors)

    require(targeted_sam.get("ok") is True and targeted_sam.get("imageCount") == 1 and targeted_sam.get("promptCount") == 1 and sum(int(item.get("polygonCount", 0)) for item in targeted_sam.get("outputs", [])) == 1, "targeted SAM candidate mismatch", errors)
    require(targeted_rejection.get("ok") is True and targeted_rejection.get("decision") == "reject_0040_missing_thumb_sam_background_segmentation" and targeted_rejection.get("review", {}).get("accepted") == 0 and targeted_rejection.get("review", {}).get("rejected") == 1, "targeted SAM rejection evidence mismatch", errors)
    require(detected_sam.get("ok") is True and detected_sam.get("imageCount") == 1 and detected_sam.get("promptCount") == 4 and sum(int(item.get("polygonCount", 0)) for item in detected_sam.get("outputs", [])) == 4, "detected-nail SAM candidate mismatch", errors)
    require(detected_rejection.get("ok") is True and detected_rejection.get("decision") == "reject_0040_detected_nail_sam_background_contamination" and detected_rejection.get("review", {}).get("accepted") == 1 and detected_rejection.get("review", {}).get("rejected") == 3, "detected-nail SAM rejection evidence mismatch", errors)

    expected_rejections = {
        "rejected_final_v1": "reject_batch4_final_candidate_v1_thumb_proximal_undercoverage",
        "rejected_final_v2": "reject_batch4_final_candidate_v2_correction_target_mismatch",
        "rejected_final_v3": "reject_batch4_final_candidate_v3_inherited_0044_dual_definition",
    }
    for label, decision in expected_rejections.items():
        require(documents[label].get("ok") is True and documents[label].get("decision") == decision, f"{label} evidence mismatch", errors)

    require(final.get("ok") is True and final.get("decision") == "candidate_only_not_training_or_test_truth" and final.get("imageCount") == 10 and final.get("polygonCount") == 60 and final.get("retainedPolygonCount") == 55 and final.get("manualPolygonCount") == 5 and final.get("pairwiseOverlapCount") == 0 and final.get("errors") == [], "final candidate mismatch", errors)
    require(single_summary(final_geometry) == {"pass": 60, "suspect": 0, "missing": 0}, "final geometry mismatch", errors)
    require(review.get("ok") is True and review.get("decision") == "mask_review_shard_complete_final_truth_audit_still_required" and review.get("counts") == {"images": 10, "exclude": 0, "pass": 10, "rework": 0} and review.get("policy", {}).get("trainingUse") == "prohibited", "final original-resolution review mismatch", errors)
    require(truth.get("ok") is True and truth.get("decision") == "approved_unique_development_evaluation_truth_index" and truth.get("summary") == {"approvedReportCount": 43, "rejectedReportCount": 0, "uniqueImageCount": 43, "completeMaskCount": 265, "redundantReportCount": 0, "redundantImageCount": 0, "conflictingImageCount": 0}, "cumulative development truth mismatch", errors)
    require(truth.get("policy", {}).get("trainingUse") == "prohibited" and truth.get("policy", {}).get("evaluationUse") == "prohibited-until-clean-development-materialization-audit", "development truth role mismatch", errors)
    require(prior.get("ok") is True and prior.get("metrics", {}).get("combinedLastTwoBatchNails") == 120 and prior.get("metrics", {}).get("combinedLastTwoBatchSamAccepted") == 111, "prior batch-3 baseline mismatch", errors)

    prelabel_seconds = checked_duration(documents["timing_prelabel"], "guardedPrelabel", 5.3227996, errors)
    sam_seconds = checked_duration(documents["timing_sam"], "samPcaMultipoint", 33.7137651, errors)
    targeted_seconds = checked_duration(documents["timing_targeted"], "targetedSamMissingThumb", 5.859423, errors)
    final_review_seconds = checked_duration(documents["timing_final_review"], "finalOriginalResolutionReview", 248.534482, errors)

    prelabel_source = paths["prelabel_script"].read_text(encoding="utf-8")
    main_position = prelabel_source.find("def main")
    install_position = prelabel_source.find("install_read_only_ultralytics_image_check()", main_position)
    model_position = prelabel_source.find("model = YOLO(str(model_path))", main_position)
    require(main_position >= 0 and install_position > main_position and model_position > install_position, "prelabel read-only guard is not installed before model load", errors)

    current_acceptance = 55 / 60
    combined_acceptance = (111 + 55) / (120 + 60)
    machine_seconds = prelabel_seconds + sam_seconds + targeted_seconds
    return {
        "schemaVersion": 1,
        "ok": not errors,
        "decision": "retain_guarded_pca_sam_and_count_mismatch_stoploss" if not errors else "reject_batch4_annotation_acceleration",
        "inputs": {name: {"path": str(path), "sha256": sha256_file(path)} for name, path in paths.items()},
        "metrics": {
            "incrementalImages": 10,
            "incrementalNails": 60,
            "guardedPrelabelCandidates": 60,
            "cappedCountCoverage": 0.983333,
            "originalResolutionConfirmedNonNailCandidatesTrimmed": 1,
            "undercountImages": 1,
            "bulkSamAccepted": 55,
            "residualManualBoundaryInterventions": 5,
            "samAcceptanceRate": current_acceptance,
            "combinedLastThreeBatchNails": 180,
            "combinedLastThreeBatchSamAccepted": 166,
            "combinedLastThreeBatchSamAcceptanceRate": combined_acceptance,
            "finalApprovedImages": 10,
            "finalApprovedMasks": 60,
            "cumulativeSourceQualifiedImages": 43,
            "cumulativeDevelopmentEvaluationImages": 43,
            "cumulativeDevelopmentEvaluationMasks": 265,
            "remainingToDevelopmentEvaluationTarget90": 47,
            "remainingToSourceQualifiedTarget133": 90,
            "minimumNewApprovedPositiveGap": 381,
            "measuredCanonicalMachineSeconds": machine_seconds,
            "observedFinalReviewWindowSeconds": final_review_seconds,
        },
        "routeValidation": {
            "valid": not errors,
            "measuredBenefit": "55_of_60_final_boundaries_avoided_manual_polygon_authoring",
            "bulkEligibleSamAcceptance": "55_of_55",
            "countMismatchPolicy": "exact counts or at-most-two original-resolution-confirmed non-nail trims may enter bulk SAM; undercount routes to one targeted attempt then full-image manual truth",
            "failedAttemptsPreserved": [targeted_rejection.get("decision"), detected_rejection.get("decision"), *(documents[label].get("decision") for label in expected_rejections)],
            "criticalPath": "source qualification and original-resolution final review remain the schedule bottleneck",
            "limitation": "the 248.534482-second review window includes evidence-build failure and correction iterations, so it is not a clean active-labor comparator",
        },
        "scheduleConclusion": "route_is_valid_and_reduces_boundary_drawing_but_formal_release_still_requires_47_more_clean_development_images_then_quality_remeasurement_and_all_release_gates",
        "policy": {
            "originalResolutionReviewStillRequired": True,
            "geometryAuditDoesNotReplaceVisualReview": True,
            "developmentEvaluationTrainingUse": "prohibited",
            "protectedRolesUnchanged": True,
            "qualityThresholdsUnchanged": True,
            "failedEvidencePreserved": True,
            "releaseState": "hold",
            "productState": "hold",
        },
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay cycle015 batch-4 annotation acceleration and count-mismatch stop-loss evidence.")
    names = (
        "source-audit", "workspace", "prelabel-audit", "prompts", "sam", "sam-geometry",
        "sam-visual-decision", "targeted-sam", "targeted-sam-rejection", "detected-sam",
        "detected-sam-rejection", "rejected-final-v1", "rejected-final-v2", "rejected-final-v3",
        "final-candidate", "final-geometry", "mask-review-final", "truth-index", "prior-batch3-audit",
        "timing-prelabel", "timing-sam", "timing-targeted", "timing-final-review", "prelabel-script",
    )
    for name in names:
        parser.add_argument(f"--{name}")
    parser.add_argument("--output")
    parser.add_argument("--verify-report")
    args = parser.parse_args()
    if args.verify_report:
        expected_path = Path(args.verify_report).resolve()
        expected = read_json(expected_path)
        for name in (entry.replace("-", "_") for entry in names):
            value = expected.get("inputs", {}).get(name)
            if value:
                setattr(args, name, value["path"])
        actual = build(args)
        if actual != expected:
            raise SystemExit("report differs from replay")
        print(json.dumps({"ok": True, "decision": actual["decision"], "reportSha256": sha256_file(expected_path)}))
        return
    missing = [name for name in (entry.replace("-", "_") for entry in names) if not getattr(args, name)]
    if missing or not args.output:
        parser.error(f"all evidence arguments and --output are required; missing: {', '.join(missing)}")
    result = build(args)
    write_json_atomic(Path(args.output).resolve(), result)
    print(json.dumps({"ok": result["ok"], "decision": result["decision"], "metrics": result.get("metrics")}, ensure_ascii=True))


if __name__ == "__main__":
    main()
