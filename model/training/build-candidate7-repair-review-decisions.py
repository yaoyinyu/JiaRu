from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_atomic(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def require_bound_input(
    assessment: dict[str, Any], key: str, path: Path, errors: list[str]
) -> None:
    if assessment.get(f"{key}Path") != str(path):
        errors.append(f"assessment {key}Path differs from requested input")
    if assessment.get(f"{key}Sha256") != sha256_file(path):
        errors.append(f"assessment does not bind current {key}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build schema-v2, hash-bound per-image candidate7 repair review decisions "
            "from a completed original-resolution human assessment."
        )
    )
    parser.add_argument("--initial-final-dir", required=True)
    parser.add_argument("--repair-prompts", required=True)
    parser.add_argument("--sam-report", required=True)
    parser.add_argument("--geometry-audit", required=True)
    parser.add_argument("--visual-evidence", required=True)
    parser.add_argument("--contact-sheet-report", required=True)
    parser.add_argument("--assessment", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    initial_dir = Path(args.initial_final_dir).resolve()
    paths = {
        "repairPrompts": Path(args.repair_prompts).resolve(),
        "samReport": Path(args.sam_report).resolve(),
        "geometryAudit": Path(args.geometry_audit).resolve(),
        "visualEvidence": Path(args.visual_evidence).resolve(),
        "contactSheetReport": Path(args.contact_sheet_report).resolve(),
        "assessment": Path(args.assessment).resolve(),
    }
    output_dir = Path(args.output_dir).resolve()
    errors: list[str] = []
    for label, path in paths.items():
        if not path.is_file():
            errors.append(f"missing {label}: {path}")
    initial_paths = sorted(initial_dir.glob("mask-review-shard-*-report.json"))
    if not initial_paths:
        initial_paths = sorted(initial_dir.glob("review-report-*.json"))
    if not initial_paths:
        errors.append(f"no initial final reports found: {initial_dir}")
    if errors:
        raise SystemExit("\n".join(errors))

    prompts = read_json(paths["repairPrompts"])
    sam_report = read_json(paths["samReport"])
    geometry = read_json(paths["geometryAudit"])
    visual = read_json(paths["visualEvidence"])
    contact = read_json(paths["contactSheetReport"])
    assessment = read_json(paths["assessment"])

    if assessment.get("schemaVersion") != 1 or assessment.get("decision") != "candidate7_repair_original_resolution_review_assessment":
        errors.append("unsupported assessment schema or decision")
    if assessment.get("originalResolutionReviewCompleted") is not True:
        errors.append("assessment must confirm original-resolution review completion")
    if assessment.get("trainingUse") != "prohibited":
        errors.append("assessment must keep trainingUse prohibited")
    for key in ("repairPrompts", "samReport", "geometryAudit", "visualEvidence", "contactSheetReport"):
        require_bound_input(assessment, key, paths[key], errors)

    if prompts.get("decision") not in {
        "sam_repair_candidate_only_not_test_truth",
        "sam_candidate_only_not_training_truth",
    }:
        errors.append("repair prompts are not candidate-only")
    if sam_report.get("ok") is not True or sam_report.get("decision") != "sam_candidate_only_not_training_truth":
        errors.append("SAM report is not a passing candidate-only report")
    if visual.get("ok") is not True or visual.get("decision") != "sam_visual_review_evidence_ready_not_truth":
        errors.append("visual evidence is not a passing candidate-only report")
    if contact.get("ok") is not True or contact.get("decision") != "candidate7_repair_contact_sheets_ready_original_resolution_review_required":
        errors.append("contact sheet report is not ready for original-resolution review")

    initial_by_file: dict[str, tuple[Path, dict[str, Any]]] = {}
    for path in initial_paths:
        report = read_json(path)
        if report.get("ok") is not True or report.get("decision") != "mask_review_shard_complete_final_truth_audit_still_required":
            errors.append(f"invalid initial final report: {path}")
            continue
        for item in report.get("items", []):
            file_name = str(item.get("fileName", ""))
            if file_name in initial_by_file:
                errors.append(f"duplicate initial item: {file_name}")
            initial_by_file[file_name] = (path, item)

    prompt_by_file = {str(item.get("fileName")): item for item in prompts.get("images", [])}
    output_by_file = {str(item.get("fileName")): item for item in sam_report.get("outputs", [])}
    visual_by_file = {str(item.get("fileName")): item for item in visual.get("items", [])}
    repair_files = set(prompt_by_file)
    if repair_files != set(output_by_file) or repair_files != set(visual_by_file):
        errors.append("prompts, SAM outputs, and visual evidence must cover the same files")
    if not repair_files.issubset(initial_by_file):
        errors.append("repair inputs contain files absent from initial review")

    pass_files = assessment.get("passFiles", [])
    exclude_files = assessment.get("excludeFiles", {})
    rework_overrides = assessment.get("reworkOverrides", {})
    if not isinstance(pass_files, list) or len(set(pass_files)) != len(pass_files):
        errors.append("passFiles must be a unique list")
        pass_files = []
    if not isinstance(exclude_files, dict) or not isinstance(rework_overrides, dict):
        errors.append("excludeFiles and reworkOverrides must be objects")
        exclude_files, rework_overrides = {}, {}
    declared = set(pass_files) | set(exclude_files) | set(rework_overrides)
    if declared != repair_files:
        errors.append(
            "assessment must exactly classify every repair file; "
            f"missing={sorted(repair_files - declared)}, extra={sorted(declared - repair_files)}"
        )
    if (set(pass_files) & set(exclude_files)) or (set(pass_files) & set(rework_overrides)) or (set(exclude_files) & set(rework_overrides)):
        errors.append("assessment classifications must be disjoint")

    geometry_rows: dict[str, list[dict[str, Any]]] = {}
    for row in geometry.get("rows", []):
        geometry_rows.setdefault(str(row.get("fileName")), []).append(row)

    if errors:
        raise SystemExit("\n".join(errors))

    outputs: list[dict[str, Any]] = []
    for file_name in sorted(repair_files):
        initial_path, initial_item = initial_by_file[file_name]
        prompt_item = prompt_by_file[file_name]
        candidate = output_by_file[file_name]
        visual_item = visual_by_file[file_name]
        annotation_path = Path(str(candidate.get("annotationPath", ""))).resolve()
        overlay_path = Path(str(candidate.get("overlayPath", ""))).resolve()
        if not annotation_path.is_file() or not overlay_path.is_file():
            raise SystemExit(f"missing candidate annotation or overlay: {file_name}")
        expected = int(initial_item.get("expectedFullyVisibleNails", 0))
        polygon_count = len(read_json(annotation_path).get("annotations", []))
        rows = geometry_rows.get(file_name, [])
        suspect_count = sum(row.get("status") != "pass" for row in rows)

        if file_name in pass_files:
            if len(prompt_item.get("boxes", [])) != expected or polygon_count != expected or len(rows) != expected or suspect_count:
                raise SystemExit(f"pass item does not satisfy count and geometry gates: {file_name}")
            status = "pass"
            issue_codes: list[str] = []
            note = "原分辨率逐甲叠加图及每个甲面的2倍源图/蒙版裁片终审通过；完整甲面一一对应且无污染。"
            final_count: int | None = expected
        else:
            status = "exclude" if file_name in exclude_files else "rework"
            payload = (exclude_files if status == "exclude" else rework_overrides)[file_name]
            if not isinstance(payload, dict):
                raise SystemExit(f"invalid assessment payload: {file_name}")
            issue_codes = payload.get("issueCodes", [])
            if not isinstance(issue_codes, list) or not issue_codes:
                raise SystemExit(f"{status} requires issueCodes: {file_name}")
            note = str(payload.get("note", ""))
            final_count = None

        if visual_item.get("annotationSha256") != sha256_file(annotation_path) or visual_item.get("overlaySha256") != sha256_file(overlay_path):
            raise SystemExit(f"visual evidence drifted from candidate output: {file_name}")
        decision = {
            "schemaVersion": 2,
            "fileName": file_name,
            "sha256": initial_item["sha256"],
            "sourceGroup": initial_item["sourceGroup"],
            "initialShardFinalSha256": sha256_file(initial_path),
            "repairPromptsSha256": sha256_file(paths["repairPrompts"]),
            "samReportSha256": sha256_file(paths["samReport"]),
            "geometryAuditSha256": sha256_file(paths["geometryAudit"]),
            "visualEvidenceSha256": sha256_file(paths["visualEvidence"]),
            "annotationSha256": sha256_file(annotation_path),
            "reviewedOverlaySha256": sha256_file(overlay_path),
            "reviewStatus": status,
            "finalCompleteMaskCount": final_count,
            "issueCodes": issue_codes,
            "note": note,
            "trainingUse": "prohibited",
        }
        decision_path = output_dir / "decisions" / f"{file_name}.review.json"
        write_json_atomic(decision_path, decision)
        outputs.append(
            {
                "fileName": file_name,
                "reviewStatus": status,
                "initialShardFinalPath": str(initial_path),
                "decisionPath": str(decision_path),
                "decisionSha256": sha256_file(decision_path),
            }
        )

    report = {
        "schemaVersion": 1,
        "ok": True,
        "decision": "candidate7_repair_review_decisions_ready_for_finalization",
        "inputs": {
            **{key: str(path) for key, path in paths.items()},
            **{f"{key}Sha256": sha256_file(path) for key, path in paths.items()},
            "initialFinalReports": [
                {"path": str(path), "sha256": sha256_file(path)} for path in initial_paths
            ],
        },
        "summary": {
            "images": len(outputs),
            "pass": sum(item["reviewStatus"] == "pass" for item in outputs),
            "rework": sum(item["reviewStatus"] == "rework" for item in outputs),
            "exclude": sum(item["reviewStatus"] == "exclude" for item in outputs),
        },
        "policy": {"trainingUse": "prohibited", "finalTruthAuditStillRequired": True},
        "items": outputs,
        "errors": [],
    }
    report_path = output_dir / "report.json"
    write_json_atomic(report_path, report)
    print(json.dumps({"ok": True, **report["summary"], "report": str(report_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
