from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


VALID_STATUSES = {"pass", "rework", "exclude"}


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
        description="Finalize one hash-bound first-annotation mask repair review without granting training truth."
    )
    parser.add_argument("--initial-shard-final", required=True)
    parser.add_argument("--file-name", required=True)
    parser.add_argument("--repair-prompts", required=True)
    candidate_report = parser.add_mutually_exclusive_group(required=True)
    candidate_report.add_argument("--sam-report")
    candidate_report.add_argument("--manual-report")
    parser.add_argument("--geometry-audit", required=True)
    parser.add_argument("--decision", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    report_key = "samReport" if args.sam_report else "manualReport"
    report_value = args.sam_report or args.manual_report
    paths = {
        "initialShardFinal": Path(args.initial_shard_final).resolve(),
        "repairPrompts": Path(args.repair_prompts).resolve(),
        report_key: Path(report_value).resolve(),
        "geometryAudit": Path(args.geometry_audit).resolve(),
        "decision": Path(args.decision).resolve(),
    }
    output_path = Path(args.output).resolve()
    errors: list[str] = []
    for label, path in paths.items():
        if not path.is_file():
            errors.append(f"missing {label}: {path}")
    if errors:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps({"ok": False, "errors": errors}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise SystemExit(1)

    initial = read_json(paths["initialShardFinal"])
    prompts = read_json(paths["repairPrompts"])
    candidate_report_data = read_json(paths[report_key])
    geometry = read_json(paths["geometryAudit"])
    decision = read_json(paths["decision"])
    file_name = args.file_name
    manual_mode = report_key == "manualReport"

    if initial.get("ok") is not True or initial.get("decision") != "mask_review_shard_complete_final_truth_audit_still_required":
        errors.append("a passing initial mask review shard final report is required")
    initial_item = next((item for item in initial.get("items", []) if item.get("fileName") == file_name), None)
    if initial_item is None:
        errors.append("file is absent from the initial shard final report")
    elif initial_item.get("reviewStatus") != "rework":
        errors.append("only an initial rework item may enter repair finalization")

    prompt_item = next((item for item in prompts.get("images", []) if item.get("fileName") == file_name), None)
    expected_prompt_decision = (
        "candidate_only_not_training_or_test_truth"
        if manual_mode
        else "sam_repair_candidate_only_not_test_truth"
    )
    if prompts.get("decision") != expected_prompt_decision or prompt_item is None:
        errors.append("repair prompts must contain the requested candidate-only image")
    candidate_output = next(
        (item for item in candidate_report_data.get("outputs", []) if item.get("fileName") == file_name),
        None,
    )
    if manual_mode:
        manual_report_valid = (
            candidate_report_data.get("ok") is True
            and candidate_report_data.get("method")
            == "reviewed-hybrid-original-resolution-manual-polygon-repair"
            and candidate_report_data.get("decision") == "candidate_only_not_training_or_test_truth"
            and candidate_output is not None
        )
        if not manual_report_valid:
            errors.append("a passing candidate-only manual polygon report is required")
        elif (
            candidate_output.get("validPolygonCount") != candidate_output.get("polygonCount")
            or candidate_output.get("pairwiseOverlapCount") != 0
            or candidate_report_data.get("pairwiseOverlapCount") != 0
        ):
            errors.append("manual polygon report requires all polygons valid and pairwise zero overlap")
    elif (
        candidate_report_data.get("ok") is not True
        or candidate_report_data.get("decision") != "sam_candidate_only_not_training_truth"
        or candidate_output is None
    ):
        errors.append("a passing candidate-only SAM report is required")

    annotation_path = (
        Path(str(candidate_output.get("annotationPath", ""))).resolve()
        if candidate_output
        else Path("missing")
    )
    overlay_path = (
        Path(str(candidate_output.get("overlayPath", ""))).resolve()
        if candidate_output
        else Path("missing")
    )
    if not annotation_path.is_file():
        errors.append("bound repair annotation is missing")
        annotation: dict[str, Any] = {}
    else:
        annotation = read_json(annotation_path)
    if not overlay_path.is_file():
        errors.append("bound repair overlay is missing")

    if decision.get("schemaVersion") != 1 or decision.get("fileName") != file_name:
        errors.append("unsupported decision schema or fileName mismatch")
    for key, path in paths.items():
        if key == "decision":
            continue
        expected_key = f"{key}Sha256"
        if decision.get(expected_key) != sha256_file(path):
            errors.append(f"decision does not bind {key}")
    if initial_item is not None:
        if decision.get("sha256") != initial_item.get("sha256") or decision.get("sourceGroup") != initial_item.get("sourceGroup"):
            errors.append("decision identity differs from the initial reviewed item")
    if prompt_item is not None and initial_item is not None and prompt_item.get("sourceGroup") != initial_item.get("sourceGroup"):
        errors.append("repair prompt sourceGroup differs from the initial reviewed item")
    if annotation:
        image = annotation.get("image", {})
        if image.get("fileName") != file_name or (initial_item and image.get("sourceGroup") != initial_item.get("sourceGroup")):
            errors.append("repair annotation image identity differs from the reviewed item")
        expected_annotation_decision = (
            "candidate_only_not_training_or_test_truth"
            if manual_mode
            else "candidate_only_not_training_truth"
        )
        if annotation.get("trainingUse") != "prohibited" or annotation.get("decision") != expected_annotation_decision:
            errors.append("repair annotation must remain candidate-only and training prohibited")

    if annotation_path.is_file() and decision.get("annotationSha256") != sha256_file(annotation_path):
        errors.append("decision does not bind the repair annotation")
    if overlay_path.is_file() and decision.get("reviewedOverlaySha256") != sha256_file(overlay_path):
        errors.append("decision does not acknowledge the reviewed original-resolution overlay")

    status = str(decision.get("reviewStatus", ""))
    issue_codes = decision.get("issueCodes", [])
    final_count = decision.get("finalCompleteMaskCount")
    expected_count = int(initial_item.get("expectedFullyVisibleNails", 0)) if initial_item else 0
    polygon_count = len(annotation.get("annotations", [])) if annotation else 0
    prompt_count = len(prompt_item.get("boxes", [])) if prompt_item else 0
    geometry_rows = [row for row in geometry.get("rows", []) if row.get("fileName") == file_name]
    geometry_suspects = sum(row.get("status") != "pass" for row in geometry_rows)
    if status not in VALID_STATUSES:
        errors.append(f"invalid reviewStatus: {status}")
    if not isinstance(issue_codes, list) or any(not isinstance(code, str) or not code for code in issue_codes):
        errors.append("issueCodes must be a list of non-empty strings")
        issue_codes = []
    if status == "pass":
        if issue_codes:
            errors.append("pass cannot retain issue codes")
        if final_count != expected_count or prompt_count != expected_count or polygon_count != expected_count:
            errors.append("pass requires expected prompt, polygon, and final complete-mask counts")
        if len(geometry_rows) != expected_count or geometry_suspects:
            errors.append("pass requires a geometry-pass row for every repaired polygon")
    else:
        if not issue_codes:
            errors.append(f"{status} requires issue codes")
        if final_count not in (None, 0):
            errors.append(f"{status} finalCompleteMaskCount must be null or zero")

    if errors:
        result = {"ok": False, "errors": errors}
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise SystemExit(1)

    result = {
        "schemaVersion": 1,
        "ok": True,
        "decision": "mask_repair_review_complete_final_truth_audit_still_required",
        "inputs": {
            **{key: str(path) for key, path in paths.items()},
            **{f"{key}Sha256": sha256_file(path) for key, path in paths.items()},
            "annotation": str(annotation_path),
            "annotationSha256": sha256_file(annotation_path),
            "reviewedOverlay": str(overlay_path),
            "reviewedOverlaySha256": sha256_file(overlay_path),
        },
        "policy": {
            "repairReviewDoesNotGrantTrainingUse": True,
            "passStillRequiresPolygonTopologyAndFinalTruthAudit": True,
            "trainingUse": "prohibited",
            "originalResolutionReviewCompleted": True,
        },
        "item": {
            "fileName": file_name,
            "sha256": initial_item["sha256"],
            "sourceGroup": initial_item["sourceGroup"],
            "expectedFullyVisibleNails": expected_count,
            "promptCount": prompt_count,
            "polygonCount": polygon_count,
            "geometryPass": len(geometry_rows) - geometry_suspects,
            "geometrySuspect": geometry_suspects,
            "reviewStatus": status,
            "finalCompleteMaskCount": final_count,
            "issueCodes": issue_codes,
            "note": str(decision.get("note", "")),
            "trainingUse": "prohibited",
            "annotationTruthStatus": "reviewed-repair-candidate-not-final-truth" if status == "pass" else status,
            "repairEvidenceType": "manual-polygon" if manual_mode else "sam",
        },
        "errors": [],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "fileName": file_name, "reviewStatus": status}, ensure_ascii=True))


if __name__ == "__main__":
    main()
