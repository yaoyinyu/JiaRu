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


def duration_seconds(stage: dict[str, Any]) -> float:
    start = datetime.fromisoformat(str(stage["start"]))
    end = datetime.fromisoformat(str(stage["end"]))
    return (end - start).total_seconds()


def build(args: argparse.Namespace) -> dict[str, Any]:
    paths = {
        "workspace": Path(args.workspace).resolve(),
        "prelabelAudit": Path(args.prelabel_audit).resolve(),
        "prompts": Path(args.prompts).resolve(),
        "sam": Path(args.sam).resolve(),
        "samVisualDecision": Path(args.sam_visual_decision).resolve(),
        "failedRepairGeometry": Path(args.failed_repair_geometry).resolve(),
        "rejectedFinalV1": Path(args.rejected_final_v1).resolve(),
        "finalCandidate": Path(args.final_candidate).resolve(),
        "finalGeometry": Path(args.final_geometry).resolve(),
        "maskReviewFinal": Path(args.mask_review_final).resolve(),
        "truthIndex": Path(args.truth_index).resolve(),
        "priorIncrementalAudit": Path(args.prior_incremental_audit).resolve(),
        "timing": Path(args.timing).resolve(),
        "prelabelScript": Path(args.prelabel_script).resolve(),
    }
    errors: list[str] = []
    documents: dict[str, dict[str, Any]] = {}
    for label, path in paths.items():
        if not path.is_file():
            errors.append(f"{label} is missing: {path}")
            continue
        if label != "prelabelScript":
            try:
                documents[label] = read_json(path)
            except (OSError, json.JSONDecodeError) as error:
                errors.append(f"{label} is unreadable: {error}")
    if errors:
        return {"schemaVersion": 1, "ok": False, "decision": "reject_batch3_annotation_acceleration", "errors": errors}

    workspace = documents["workspace"]
    prelabel = documents["prelabelAudit"]
    prompts = documents["prompts"]
    sam = documents["sam"]
    visual = documents["samVisualDecision"]
    failed_repair = documents["failedRepairGeometry"]
    rejected_v1 = documents["rejectedFinalV1"]
    final_candidate = documents["finalCandidate"]
    final_geometry = documents["finalGeometry"]
    mask_review = documents["maskReviewFinal"]
    truth = documents["truthIndex"]
    prior = documents["priorIncrementalAudit"]
    timing = documents["timing"]

    expected_images = 10
    expected_nails = 60
    require(workspace.get("ok") is True and workspace.get("counts", {}).get("images") == expected_images and workspace.get("counts", {}).get("expectedFullyVisibleNails") == expected_nails, "workspace totals mismatch", errors)
    require(all(item.get("assignedRole") == "development-evaluation-extension" and item.get("trainingUse") == "prohibited" for item in workspace.get("items", [])), "workspace role isolation mismatch", errors)
    require(prelabel.get("ok") is True and prelabel.get("counts") == {"images": 10, "expectedFullyVisibleNails": 60, "candidates": 60, "cappedCountCoverage": 0.933333, "zeroCandidateImages": 0, "underCandidateImages": 1, "exactCandidateImages": 7, "overCandidateImages": 2, "duplicateOverlapPairs": 2, "machineErrors": 0}, "guarded prelabel audit mismatch", errors)
    require(prompts.get("imageCount") == 10 and prompts.get("promptCount") == 60 and prompts.get("trimmedOverpredictionCandidateCount") == 4 and prompts.get("manualPromptRecoveryCount") == 5, "PCA/manual recovery prompt totals mismatch", errors)
    require(prompts.get("policy", {}).get("trainingUse") == "prohibited", "prompt role policy mismatch", errors)
    sam_polygons = sum(int(item.get("polygonCount", 0)) for item in sam.get("outputs", []))
    require(sam.get("ok") is True and sam.get("promptCount") == 60 and sam_polygons == 60 and sam.get("errors") == [], "SAM candidate result mismatch", errors)
    review = visual.get("review", {})
    require(visual.get("ok") is True and visual.get("decision") == "sam_51_accepted_9_residual_manual_rework" and review.get("reviewedNails") == 60 and review.get("accepted") == 51 and review.get("rework") == 9, "original-resolution SAM review mismatch", errors)
    failed_summary = next(iter(failed_repair.get("summary", {}).values()), {})
    require(failed_summary == {"pass": 0, "suspect": 5, "missing": 0}, "failed tight-repair stop-loss evidence mismatch", errors)
    require(rejected_v1.get("ok") is True and rejected_v1.get("decision") == "reject_final_candidate_v1_original_resolution_skin_contamination", "rejected final-v1 evidence mismatch", errors)
    require(final_candidate.get("ok") is True and final_candidate.get("imageCount") == 10 and final_candidate.get("polygonCount") == 60 and final_candidate.get("retainedPolygonCount") == 51 and final_candidate.get("manualPolygonCount") == 9 and final_candidate.get("pairwiseOverlapCount") == 0, "corrected final candidate mismatch", errors)
    geometry_counts = next(iter(final_geometry.get("summary", {}).values()), {})
    require(geometry_counts == {"pass": 60, "suspect": 0, "missing": 0}, "corrected final geometry mismatch", errors)
    require(mask_review.get("ok") is True and mask_review.get("decision") == "mask_review_shard_complete_final_truth_audit_still_required" and mask_review.get("counts") == {"images": 10, "exclude": 0, "pass": 10, "rework": 0}, "final original-resolution review mismatch", errors)
    truth_summary = truth.get("summary", {})
    require(truth.get("ok") is True and truth.get("decision") == "approved_unique_development_evaluation_truth_index" and truth.get("policy", {}).get("trainingUse") == "prohibited" and truth_summary.get("uniqueImageCount") == 33 and truth_summary.get("completeMaskCount") == 205 and truth_summary.get("conflictingImageCount") == 0, "cumulative development truth mismatch", errors)
    prior_metrics = prior.get("metrics", {})
    require(prior.get("ok") is True and prior_metrics.get("incrementalNails") == 60 and prior_metrics.get("samAccepted") == 60 and prior_metrics.get("residualManualBoundaryInterventions") == 0, "prior incremental baseline mismatch", errors)

    required_durations = {
        "guardedPrelabel": 4.9215545,
        "samPcaMultipoint": 34.3688273,
        "failedTightRepair": 7.3470087,
        "finalCandidateV1Materialization": 5.292,
        "finalCandidateV2CorrectionMaterialization": 5.1776776,
        "finalOriginalResolutionReview": 99.8829805,
    }
    for label, expected in required_durations.items():
        stage = timing.get("stages", {}).get(label, {})
        try:
            measured = duration_seconds(stage)
        except (KeyError, TypeError, ValueError):
            errors.append(f"{label} timing is invalid")
            continue
        require(abs(measured - expected) < 0.002 and abs(float(stage.get("durationSeconds", -1)) - expected) < 0.002, f"{label} timing mismatch", errors)
    require(timing.get("limitations", {}).get("manualPolygonAuthoringActiveSeconds") is None and timing.get("limitations", {}).get("suspendedWallTimeExcluded") is True, "timing limitation disclosure mismatch", errors)

    prelabel_source = paths["prelabelScript"].read_text(encoding="utf-8")
    install_position = prelabel_source.find("install_read_only_ultralytics_image_check()", prelabel_source.find("def main"))
    model_position = prelabel_source.find("model = YOLO(str(model_path))", prelabel_source.find("def main"))
    require(install_position >= 0 and model_position > install_position, "prelabel read-only guard is not installed before model load", errors)

    current_acceptance = 51 / 60
    combined_acceptance = (60 + 51) / 120
    return {
        "schemaVersion": 1,
        "ok": not errors,
        "decision": "retain_guarded_pca_sam_with_one_retry_stoploss_and_residual_manual" if not errors else "reject_batch3_annotation_acceleration",
        "inputs": {label: {"path": str(path), "sha256": sha256_file(path)} for label, path in paths.items()},
        "metrics": {
            "incrementalImages": 10,
            "incrementalNails": 60,
            "guardedPrelabelCandidates": 60,
            "cappedCountCoverage": 0.933333,
            "reviewedDuplicateCandidatesTrimmed": 4,
            "manualPromptRecoveries": 5,
            "samAccepted": 51,
            "residualManualBoundaryInterventions": 9,
            "samAcceptanceRate": current_acceptance,
            "combinedLastTwoBatchNails": 120,
            "combinedLastTwoBatchSamAccepted": 111,
            "combinedLastTwoBatchSamAcceptanceRate": combined_acceptance,
            "finalApprovedImages": 10,
            "finalApprovedMasks": 60,
            "cumulativeDevelopmentEvaluationImages": 33,
            "cumulativeDevelopmentEvaluationMasks": 205,
            "measuredMachineSecondsBeforeHumanReview": required_durations["guardedPrelabel"] + required_durations["samPcaMultipoint"],
            "measuredFinalReviewSeconds": required_durations["finalOriginalResolutionReview"],
        },
        "route": {
            "continue": "guarded coarse candidates to PCA three-point SAM to original-resolution review",
            "stopLoss": "after one failed targeted SAM repair, switch the residual boundary to original-resolution manual polygon",
            "countProtection": "model undercoverage never reduces the fully-visible-nail denominator",
            "overpredictionProtection": "trim only original-resolution-confirmed duplicate candidates that represent no additional nail instance",
        },
        "scheduleConclusion": "validated_lower_manual_boundary_work_for_111_of_120_recent_masks_release_date_still_requires_remaining_clean_truth_and_training_gates",
        "policy": {
            "originalResolutionReviewStillRequired": True,
            "geometryAuditDoesNotReplaceVisualReview": True,
            "developmentEvaluationTrainingUse": "prohibited",
            "protectedRolesUnchanged": True,
            "qualityThresholdsUnchanged": True,
            "releaseState": "hold",
            "productState": "hold",
        },
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay cycle015 batch-3 annotation acceleration and stop-loss evidence.")
    names = ("workspace", "prelabel-audit", "prompts", "sam", "sam-visual-decision", "failed-repair-geometry", "rejected-final-v1", "final-candidate", "final-geometry", "mask-review-final", "truth-index", "prior-incremental-audit", "timing", "prelabel-script")
    for name in names:
        parser.add_argument(f"--{name}")
    parser.add_argument("--output")
    parser.add_argument("--verify-report")
    args = parser.parse_args()
    if args.verify_report:
        expected_path = Path(args.verify_report).resolve()
        expected = read_json(expected_path)
        mapping = {"prelabelAudit": "prelabel_audit", "samVisualDecision": "sam_visual_decision", "failedRepairGeometry": "failed_repair_geometry", "rejectedFinalV1": "rejected_final_v1", "finalCandidate": "final_candidate", "finalGeometry": "final_geometry", "maskReviewFinal": "mask_review_final", "truthIndex": "truth_index", "priorIncrementalAudit": "prior_incremental_audit", "prelabelScript": "prelabel_script"}
        for key, value in expected.get("inputs", {}).items():
            setattr(args, mapping.get(key, key), value["path"])
        actual = build(args)
        if actual != expected:
            raise SystemExit("report differs from replay")
        print(json.dumps({"ok": True, "decision": actual["decision"], "reportSha256": sha256_file(expected_path)}))
        return
    missing = [name for name, value in vars(args).items() if name not in {"output", "verify_report"} and not value]
    if missing or not args.output:
        parser.error(f"all evidence arguments and --output are required; missing: {', '.join(missing)}")
    result = build(args)
    write_json_atomic(Path(args.output).resolve(), result)
    print(json.dumps({"ok": result["ok"], "decision": result["decision"], "metrics": result.get("metrics")}, ensure_ascii=True))


if __name__ == "__main__":
    main()
