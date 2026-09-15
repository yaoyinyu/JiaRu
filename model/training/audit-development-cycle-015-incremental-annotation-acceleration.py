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
    paths = {
        "workspace": Path(args.workspace).resolve(),
        "prelabel": Path(args.prelabel).resolve(),
        "canonicalComparison": Path(args.canonical_comparison).resolve(),
        "prompts": Path(args.prompts).resolve(),
        "sam": Path(args.sam).resolve(),
        "samVisualDecision": Path(args.sam_visual_decision).resolve(),
        "finalCandidate": Path(args.final_candidate).resolve(),
        "finalGeometry": Path(args.final_geometry).resolve(),
        "maskReview": Path(args.mask_review).resolve(),
        "truthIndex": Path(args.truth_index).resolve(),
        "baselineAudit": Path(args.baseline_audit).resolve(),
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
        return {"schemaVersion": 1, "ok": False, "decision": "reject_incremental_annotation_acceleration", "errors": errors}

    workspace = documents["workspace"]
    prelabel = documents["prelabel"]
    comparison = documents["canonicalComparison"]
    prompts = documents["prompts"]
    sam = documents["sam"]
    visual = documents["samVisualDecision"]
    final_candidate = documents["finalCandidate"]
    geometry = documents["finalGeometry"]
    mask_review = documents["maskReview"]
    truth = documents["truthIndex"]
    baseline = documents["baselineAudit"]
    prelabel_source = paths["prelabelScript"].read_text(encoding="utf-8")

    expected_images = int(workspace.get("counts", {}).get("images", -1))
    expected_nails = int(workspace.get("counts", {}).get("expectedFullyVisibleNails", -1))
    require(workspace.get("ok") is True and expected_images == 10 and expected_nails == 60, "workspace totals mismatch", errors)
    require(all(item.get("assignedRole") == "development-evaluation-extension" and item.get("trainingUse") == "prohibited" for item in workspace.get("items", [])), "workspace role isolation mismatch", errors)
    require(prelabel.get("ok") is True and prelabel.get("imageCount") == expected_images and prelabel.get("totalCandidates") == 63, "guarded prelabel totals mismatch", errors)
    require(comparison.get("ok") is True and comparison.get("decision") == "guarded_rerun_is_canonical_prior_run_excluded" and comparison.get("differingAnnotationCount") == 0, "canonical guarded rerun mismatch", errors)
    install_position = prelabel_source.find("install_read_only_ultralytics_image_check()", prelabel_source.find("def main"))
    model_position = prelabel_source.find("model = YOLO(str(model_path))", prelabel_source.find("def main"))
    require(install_position >= 0 and model_position > install_position, "prelabel read-only guard is not installed before model load", errors)
    require(prompts.get("imageCount") == expected_images and prompts.get("promptCount") == expected_nails and prompts.get("trimmedOverpredictionCandidateCount") == 3, "PCA multipoint prompt totals mismatch", errors)
    sam_polygons = sum(int(item.get("polygonCount", 0)) for item in sam.get("outputs", []))
    require(sam.get("ok") is True and sam.get("promptCount") == expected_nails and sam_polygons == expected_nails and sam.get("boxOnlyFallbackPromptCount") == 0 and sam.get("errors") == [], "SAM candidate result mismatch", errors)
    review = visual.get("review", {})
    require(visual.get("ok") is True and review.get("reviewedNails") == expected_nails and review.get("accepted") == expected_nails and review.get("rework") == 0, "original-resolution SAM review mismatch", errors)
    require(final_candidate.get("ok") is True and final_candidate.get("imageCount") == expected_images and final_candidate.get("polygonCount") == expected_nails and final_candidate.get("manualPolygonCount") == 0 and final_candidate.get("pairwiseOverlapCount") == 0, "final candidate mismatch", errors)
    geometry_counts = next(iter(geometry.get("summary", {}).values()), {})
    require(geometry_counts == {"pass": expected_nails, "suspect": 0, "missing": 0}, "final geometry mismatch", errors)
    require(mask_review.get("ok") is True and mask_review.get("counts") == {"images": expected_images, "exclude": 0, "pass": expected_images, "rework": 0}, "final mask review mismatch", errors)
    truth_summary = truth.get("summary", {})
    require(truth.get("ok") is True and truth.get("decision") == "approved_unique_development_evaluation_truth_index", "development truth index mismatch", errors)
    require(truth.get("policy", {}).get("trainingUse") == "prohibited" and truth_summary.get("uniqueImageCount") == 23 and truth_summary.get("completeMaskCount") == 145 and truth_summary.get("conflictingImageCount") == 0, "cumulative development truth totals or role mismatch", errors)
    baseline_metrics = baseline.get("metrics", {})
    require(baseline.get("ok") is True and baseline_metrics.get("pcaMultipointSamAccepted") == 44 and baseline_metrics.get("nails") == 45, "prior measured baseline mismatch", errors)

    current_rate = expected_nails / expected_nails
    baseline_rate = 44 / 45
    return {
        "schemaVersion": 1,
        "ok": not errors,
        "decision": "adopt_guarded_pca_multipoint_incremental_annotation_route" if not errors else "reject_incremental_annotation_acceleration",
        "inputs": {label: {"path": str(path), "sha256": sha256_file(path)} for label, path in paths.items()},
        "metrics": {
            "incrementalImages": expected_images,
            "incrementalNails": expected_nails,
            "prelabelCandidates": 63,
            "reviewedNonNailCandidatesTrimmed": 3,
            "samAccepted": expected_nails,
            "residualManualBoundaryInterventions": 0,
            "samAcceptanceRate": current_rate,
            "priorMeasuredSamAcceptanceRate": baseline_rate,
            "acceptanceRateChangePercentagePoints": (current_rate - baseline_rate) * 100,
            "manualBoundaryInterventionsAvoidedAgainstPerMaskManualBaseline": expected_nails,
            "cumulativeDevelopmentEvaluationImages": 23,
            "cumulativeDevelopmentEvaluationMasks": 145,
        },
        "scheduleConclusion": "validated_annotation_boundary_rework_reduction_only_end_to_end_release_date_not_yet_measured",
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
    parser = argparse.ArgumentParser(description="Replay the guarded cycle015 incremental annotation acceleration evidence.")
    for name in ("workspace", "prelabel", "canonical-comparison", "prompts", "sam", "sam-visual-decision", "final-candidate", "final-geometry", "mask-review", "truth-index", "baseline-audit", "prelabel-script"):
        parser.add_argument(f"--{name}")
    parser.add_argument("--output")
    parser.add_argument("--verify-report")
    args = parser.parse_args()
    if args.verify_report:
        expected_path = Path(args.verify_report).resolve()
        expected = read_json(expected_path)
        mapping = {"canonicalComparison": "canonical_comparison", "samVisualDecision": "sam_visual_decision", "finalCandidate": "final_candidate", "finalGeometry": "final_geometry", "maskReview": "mask_review", "truthIndex": "truth_index", "baselineAudit": "baseline_audit", "prelabelScript": "prelabel_script"}
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
