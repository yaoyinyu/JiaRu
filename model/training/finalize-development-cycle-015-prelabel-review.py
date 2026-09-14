#!/usr/bin/env python3
"""复验循环015首轮YOLO mask候选的原分辨率审核处置。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


DECISION = "cycle015_initial_mask_review_disposition_ready_rework_and_per_nail_review_required"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_object(path: Path, label: str) -> dict[str, Any]:
    path = path.resolve()
    if not path.is_file():
        raise ValueError(f"{label}不存在：{path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label}不是JSON对象")
    return value


def required_disposition(expected: int, candidates: int) -> str:
    if candidates < expected:
        return "rework_missing_nails"
    if candidates > expected:
        return "rework_duplicate_or_spurious_candidates"
    return "advance_to_per_nail_boundary_review"


def build_report(
    workspace_path: Path, prelabel_path: Path, audit_path: Path, review_path: Path
) -> dict[str, Any]:
    workspace_path = workspace_path.resolve()
    prelabel_path = prelabel_path.resolve()
    audit_path = audit_path.resolve()
    review_path = review_path.resolve()
    workspace = read_object(workspace_path, "标注工作区")
    prelabel = read_object(prelabel_path, "YOLO候选报告")
    audit = read_object(audit_path, "YOLO候选机器审计")
    review = read_object(review_path, "原分辨率审核声明")
    if (
        workspace.get("ok") is not True
        or workspace.get("decision") != "development_cycle_015_generated_annotation_workspace_ready_candidate_only"
        or workspace.get("trainingUse") != "prohibited"
    ):
        raise ValueError("循环015标注工作区合同无效")
    if (
        prelabel.get("ok") is not True
        or prelabel.get("decision") != "candidate_only_not_training_truth"
        or prelabel.get("trainingUse") != "prohibited"
        or prelabel.get("workspaceManifestSha256") != sha256_file(workspace_path)
    ):
        raise ValueError("YOLO候选报告未绑定当前工作区或角色漂移")
    inputs = audit.get("inputs") or {}
    if (
        audit.get("ok") is not True
        or audit.get("decision") != "prelabel_candidate_audit_pass_original_resolution_review_required"
        or (inputs.get("workspaceManifestSha256") != sha256_file(workspace_path))
        or (inputs.get("prelabelReportSha256") != sha256_file(prelabel_path))
    ):
        raise ValueError("YOLO候选机器审计未绑定当前输入")
    if (
        review.get("reviewScale") != "original-resolution"
        or review.get("reviewedBy") != "Codex"
        or review.get("trainingUse") != "prohibited"
        or review.get("masksApprovedAsTruth") is not False
    ):
        raise ValueError("原分辨率审核声明越权或不完整")

    workspace_by_name = {str(item["fileName"]): item for item in workspace.get("items") or []}
    prelabel_by_name = {str(item["fileName"]): item for item in prelabel.get("items") or []}
    review_rows = review.get("items")
    if not isinstance(review_rows, list):
        raise ValueError("审核声明缺少items数组")
    review_by_name = {str(item.get("fileName") or ""): item for item in review_rows}
    if len(review_by_name) != len(review_rows) or set(review_by_name) != set(workspace_by_name) or set(prelabel_by_name) != set(workspace_by_name):
        raise ValueError("工作区、候选与审核声明覆盖不一致")

    items: list[dict[str, Any]] = []
    for name in sorted(workspace_by_name):
        workspace_item = workspace_by_name[name]
        prelabel_item = prelabel_by_name[name]
        review_item = review_by_name[name]
        expected = int(workspace_item["expectedFullyVisibleNails"])
        candidates = int(prelabel_item["candidateCount"])
        disposition = required_disposition(expected, candidates)
        overlay_path = Path(str(prelabel_item.get("overlayPath") or "")).resolve()
        annotation_path = Path(str(prelabel_item.get("annotationPath") or "")).resolve()
        if (
            review_item.get("expectedFullyVisibleNails") != expected
            or review_item.get("candidateCount") != candidates
            or review_item.get("disposition") != disposition
            or review_item.get("sourceGroup") != workspace_item.get("sourceGroup")
            or review_item.get("imageSha256") != workspace_item.get("sha256")
            or not overlay_path.is_file()
            or not annotation_path.is_file()
            or review_item.get("overlaySha256") != sha256_file(overlay_path)
            or review_item.get("annotationSha256") != sha256_file(annotation_path)
        ):
            raise ValueError(f"审核处置、身份或候选制品漂移：{name}")
        issue_codes = review_item.get("issueCodes")
        if not isinstance(issue_codes, list):
            raise ValueError(f"审核处置缺少issueCodes：{name}")
        if disposition.startswith("rework_") and not issue_codes:
            raise ValueError(f"返修处置缺少问题代码：{name}")
        items.append({
            "fileName": name,
            "imageSha256": workspace_item["sha256"],
            "sourceGroup": workspace_item["sourceGroup"],
            "expectedFullyVisibleNails": expected,
            "candidateCount": candidates,
            "disposition": disposition,
            "issueCodes": issue_codes,
            "note": str(review_item.get("note") or ""),
            "annotationPath": str(annotation_path),
            "annotationSha256": sha256_file(annotation_path),
            "overlayPath": str(overlay_path),
            "overlaySha256": sha256_file(overlay_path),
            "trainingUse": "prohibited",
        })

    return {
        "schemaVersion": 1,
        "ok": True,
        "decision": DECISION,
        "inputs": {
            "workspace": {"path": str(workspace_path), "sha256": sha256_file(workspace_path)},
            "prelabel": {"path": str(prelabel_path), "sha256": sha256_file(prelabel_path)},
            "machineAudit": {"path": str(audit_path), "sha256": sha256_file(audit_path)},
            "visualReview": {"path": str(review_path), "sha256": sha256_file(review_path)},
        },
        "counts": {
            "images": len(items),
            "expectedFullyVisibleNails": sum(item["expectedFullyVisibleNails"] for item in items),
            "initialCandidateMasks": sum(item["candidateCount"] for item in items),
            "exactCountImages": sum(item["disposition"] == "advance_to_per_nail_boundary_review" for item in items),
            "underCountImages": sum(item["disposition"] == "rework_missing_nails" for item in items),
            "overCountImages": sum(item["disposition"] == "rework_duplicate_or_spurious_candidates" for item in items),
            "reworkImages": sum(item["disposition"].startswith("rework_") for item in items),
        },
        "policy": {
            "countMatchDoesNotApproveBoundaries": True,
            "fullImageOverlayReviewDoesNotReplacePerNailCropReview": True,
            "reworkMustRestoreEveryFullyVisibleNail": True,
            "originalResolutionPerNailReviewStillRequired": True,
        },
        "items": items,
        "trainingUse": "prohibited",
        "masksApprovedAsTruth": False,
        "formalPromotionAllowed": False,
        "nextAction": "repair_four_images_then_review_all_85_masks_at_original_resolution",
        "releaseState": "hold",
        "productState": "hold",
        "errors": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace")
    parser.add_argument("--prelabel")
    parser.add_argument("--machine-audit")
    parser.add_argument("--visual-review")
    parser.add_argument("--output")
    parser.add_argument("--verify-report")
    args = parser.parse_args()
    if args.verify_report:
        output = Path(args.verify_report).resolve()
        existing = read_object(output, "待重放审核处置")
        inputs = existing.get("inputs") or {}
        replay = build_report(
            Path(inputs["workspace"]["path"]), Path(inputs["prelabel"]["path"]),
            Path(inputs["machineAudit"]["path"]), Path(inputs["visualReview"]["path"]),
        )
        if replay != existing:
            raise ValueError("审核处置报告与绑定输入重放不一致")
        print(json.dumps({"ok": True, "decision": existing["decision"], "reportSha256": sha256_file(output)}, ensure_ascii=False))
        return 0
    if not all((args.workspace, args.prelabel, args.machine_audit, args.visual_review, args.output)):
        raise ValueError("构建模式缺少必填参数")
    output = Path(args.output).resolve()
    if output.exists():
        raise ValueError(f"输出已存在，禁止覆盖：{output}")
    report = build_report(Path(args.workspace), Path(args.prelabel), Path(args.machine_audit), Path(args.visual_review))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"], "counts": report["counts"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
