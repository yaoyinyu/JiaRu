#!/usr/bin/env python3
"""把candidate47精确清单中的既有终审真值安全合并到当前规范train索引。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def load_module(file_name: str, module_name: str) -> Any:
    path = Path(__file__).with_name(file_name)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"无法加载模块：{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"{label}不存在：{path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label}不是JSON对象：{path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection-plan", required=True, type=Path)
    parser.add_argument("--current-train-index", required=True, type=Path)
    parser.add_argument("--legacy-truth-index", required=True, type=Path)
    parser.add_argument("--standing-commercial-authorization", required=True, type=Path)
    parser.add_argument("--revalidated-report-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    plan_path = args.selection_plan.resolve()
    current_path = args.current_train_index.resolve()
    legacy_path = args.legacy_truth_index.resolve()
    authorization_path = args.standing_commercial_authorization.resolve()
    report_dir = args.revalidated_report_dir.resolve()
    output_path = args.output.resolve()
    if output_path.exists() or report_dir.exists() or output_path in {
        plan_path,
        current_path,
        legacy_path,
        authorization_path,
    }:
        raise ValueError("输出不得覆盖既有证据")

    helper = load_module(
        "build-candidate7-combined-training-truth-index.py", "candidate47_truth_helper"
    )
    auditor = helper.load_role_auditor()
    helper.validate_standing_authorization(authorization_path)

    plan = read_json(plan_path, "candidate47源图选择计划")
    reuse = plan.get("existingTruthReuse")
    selected_names = plan.get("selectedFileNames")
    if (
        plan.get("schemaVersion") != 1
        or plan.get("ok") is not True
        or plan.get("decision") != "source_selection_frozen_before_model_assistance"
        or plan.get("trainingUse") != "prohibited"
        or not isinstance(reuse, dict)
        or not isinstance(selected_names, list)
        or canonical_sha256(selected_names) != plan.get("selectedFileNamesSha256")
    ):
        raise ValueError("candidate47源图选择计划无效或已漂移")
    if (
        Path(str(reuse.get("currentCanonicalTrainIndex", ""))).resolve() != current_path
        or reuse.get("currentCanonicalTrainIndexSha256") != sha256_file(current_path)
        or Path(str(reuse.get("legacyReviewedTruthIndex", ""))).resolve() != legacy_path
        or reuse.get("legacyReviewedTruthIndexSha256") != sha256_file(legacy_path)
    ):
        raise ValueError("candidate47计划未绑定当前输入索引或输入哈希已漂移")

    current_document = read_json(current_path, "当前规范train索引")
    current_summary = current_document.get("summary", {})
    current_images = int(current_summary.get("uniqueImageCount", 0))
    current_masks = int(current_summary.get("completeMaskCount", 0))
    _, current_truths = helper.validate_index(
        current_path, "current-canonical-train", current_images, current_masks, auditor
    )

    legacy_document = read_json(legacy_path, "既有终审真值索引")
    legacy_truths = legacy_document.get("canonicalTruths")
    if not isinstance(legacy_truths, list):
        raise ValueError("既有终审真值索引缺少canonicalTruths")
    selected_set = set(str(name) for name in selected_names)
    reusable_by_name: dict[str, dict[str, Any]] = {}
    for item in legacy_truths:
        if not isinstance(item, dict):
            raise ValueError("既有终审真值包含非对象条目")
        file_name = str(item.get("fileName", ""))
        if file_name not in selected_set:
            continue
        previous = reusable_by_name.get(file_name)
        if previous is not None and (
            previous.get("imageSha256") != item.get("imageSha256")
            or previous.get("annotationSha256") != item.get("annotationSha256")
            or previous.get("completeMaskCount") != item.get("completeMaskCount")
        ):
            raise ValueError(f"既有终审真值存在冲突记录：{file_name}")
        reusable_by_name[file_name] = item

    reusable = sorted(
        reusable_by_name.values(),
        key=lambda item: (str(item.get("sourceGroup", "")), str(item.get("fileName", ""))),
    )
    reusable_names = sorted(str(item["fileName"]) for item in reusable)
    reusable_masks = sum(int(item.get("completeMaskCount", 0)) for item in reusable)
    if (
        len(reusable) != int(reuse.get("reusableApprovedImages", -1))
        or reusable_masks != int(reuse.get("reusableApprovedMasks", -1))
        or canonical_sha256(reusable_names) != reuse.get("reusableFileNamesSha256")
    ):
        raise ValueError("可复用终审真值数量、mask或精确文件清单与冻结计划不一致")
    new_names = sorted(selected_set - set(reusable_names))
    if (
        len(new_names) != int(reuse.get("newAnnotationCandidateImages", -1))
        or canonical_sha256(new_names)
        != reuse.get("newAnnotationCandidateFileNamesSha256")
    ):
        raise ValueError("仍需新标注的精确文件清单与冻结计划不一致")

    current_names = {str(item["fileName"]).casefold() for item in current_truths}
    current_hashes = {str(item["imageSha256"]) for item in current_truths}
    current_reports = {
        str(Path(str(item["reportPath"])).resolve()).casefold() for item in current_truths
    }
    reused_names: set[str] = set()
    reused_hashes: set[str] = set()
    reused_reports: set[str] = set()
    revalidated: list[dict[str, Any]] = []
    report_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary_report_dir = Path(
        tempfile.mkdtemp(prefix=f".{report_dir.name}.tmp-", dir=report_dir.parent)
    )
    for sequence, item in enumerate(reusable, start=1):
        file_name = auditor.require_nonempty(item.get("fileName"), "reused truth fileName")
        image_hash = auditor.require_sha256(
            item.get("imageSha256"), f"reused truth {file_name} image SHA-256"
        )
        auditor.require_nonempty(
            item.get("sourceGroup"), f"reused truth {file_name} sourceGroup"
        )
        report_path = auditor.require_current_file(
            item.get("reportPath"),
            item.get("reportSha256"),
            f"reused truth {file_name} report",
        )
        annotation_path = auditor.require_current_file(
            item.get("annotationPath"),
            item.get("annotationSha256"),
            f"reused truth {file_name} annotation",
        )
        mask_count = item.get("completeMaskCount")
        if isinstance(mask_count, bool) or not isinstance(mask_count, int) or mask_count < 1:
            raise ValueError(f"reused truth {file_name} completeMaskCount无效")
        report_key = str(report_path).casefold()
        if (
            file_name.casefold() in current_names
            or image_hash in current_hashes
            or report_key in current_reports
            or file_name.casefold() in reused_names
            or image_hash in reused_hashes
            or report_key in reused_reports
        ):
            raise ValueError(f"candidate47复用真值与当前train或批内身份重复：{file_name}")
        report = read_json(report_path, f"reused truth {file_name} report")
        report_inputs = report.get("inputs", {})
        report_policy = report.get("policy", {})
        report_item = report.get("item", {})
        if (
            report.get("ok") is not True
            or report.get("decision")
            != "approved_as_training_truth_candidate_pending_dataset_materialization"
            or report_policy.get("originalResolutionVisualReviewRequired") is not True
            or report_policy.get("polygonTopologyMustBeValid") is not True
            or report_policy.get("pairwisePolygonIntersectionArea") != 0
            or report_policy.get("trainingUse")
            != "prohibited-until-materialization-audit"
            or report_item.get("fileName") != file_name
            or report_item.get("sha256") != image_hash
            or report_item.get("sourceGroup") != item.get("sourceGroup")
            or report_item.get("completeMaskCount") != mask_count
            or report_item.get("invalidPolygonCount") != 0
            or report_item.get("overlapPairCount") != 0
            or report_item.get("trainingUse")
            != "prohibited-until-materialization-audit"
            or str(Path(str(report_inputs.get("annotation", ""))).resolve())
            != str(annotation_path)
            or report_inputs.get("annotationSha256") != item.get("annotationSha256")
        ):
            raise ValueError(f"candidate47复用报告不再满足完整训练真值契约：{file_name}")
        reused_names.add(file_name.casefold())
        reused_hashes.add(image_hash)
        reused_reports.add(report_key)

        revalidated_path = report_dir / f"training-truth-candidate47-revalidated-{sequence:03d}.json"
        revalidated_report = {
            "schemaVersion": 1,
            "ok": True,
            "decision": "approved_as_training_truth_candidate_pending_dataset_materialization",
            "inputs": {
                "truthRole": "train",
                "legacyFinalReport": str(report_path),
                "legacyFinalReportSha256": item["reportSha256"],
                "selectionPlan": str(plan_path),
                "selectionPlanSha256": sha256_file(plan_path),
                "standingCommercialAuthorization": str(authorization_path),
                "standingCommercialAuthorizationSha256": sha256_file(authorization_path),
                "image": str(Path(str(report_inputs["image"])).resolve()),
                "imageSha256": image_hash,
                "annotation": str(annotation_path),
                "annotationSha256": item["annotationSha256"],
            },
            "policy": {
                "originalResolutionVisualReviewRequired": True,
                "polygonTopologyMustBeValid": True,
                "pairwisePolygonIntersectionArea": 0,
                "legacyReportAndAnnotationHashesRevalidated": True,
                "datasetMaterializationAndSourceIsolationStillRequired": True,
                "trainingUse": "prohibited-until-materialization-audit",
            },
            "item": {
                "fileName": file_name,
                "sha256": image_hash,
                "sourceGroup": item["sourceGroup"],
                "completeMaskCount": mask_count,
                "invalidPolygonCount": 0,
                "overlapPairCount": 0,
                "annotationTruthStatus": "approved-as-training-truth-candidate",
                "trainingUse": "prohibited-until-materialization-audit",
            },
            "errors": [],
        }
        temporary_report_path = temporary_report_dir / revalidated_path.name
        temporary_report_path.write_text(
            json.dumps(revalidated_report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        transformed = dict(item)
        transformed["reportPath"] = str(revalidated_path)
        transformed["reportName"] = revalidated_path.name
        transformed["reportSha256"] = sha256_file(temporary_report_path)
        revalidated.append(transformed)

    os.replace(temporary_report_dir, report_dir)

    combined = [*current_truths, *revalidated]
    combined.sort(key=lambda item: (str(item["sourceGroup"]), str(item["fileName"])))
    expected_images = current_images + len(reusable)
    expected_masks = current_masks + reusable_masks
    batch_by_file = {
        str(item["fileName"]): (
            "candidate47-reused-reviewed-truth"
            if str(item["fileName"]) in reusable_by_name
            else "candidate46-current-canonical"
        )
        for item in combined
    }
    result = {
        "schemaVersion": 1,
        "ok": True,
        "decision": "approved_unique_training_truth_index",
        "inputs": {
            "truthRole": "train",
            "sourceIndexes": [
                {
                    "batch": "candidate46-current-canonical",
                    "path": str(current_path),
                    "sha256": sha256_file(current_path),
                    "images": current_images,
                    "masks": current_masks,
                },
                {
                    "batch": "candidate47-reused-reviewed-truth",
                    "path": str(legacy_path),
                    "sha256": sha256_file(legacy_path),
                    "selectionPlan": str(plan_path),
                    "selectionPlanSha256": sha256_file(plan_path),
                    "selectedFileNamesSha256": reuse["reusableFileNamesSha256"],
                    "images": len(reusable),
                    "masks": reusable_masks,
                },
            ],
            "standingCommercialAuthorization": {
                "path": str(authorization_path),
                "sha256": sha256_file(authorization_path),
            },
        },
        "policy": {
            "uniqueKey": "item.fileName",
            "canonicalSelection": "current-canonical-plus-hash-revalidated-legacy-truths",
            "sourceIndexesAreImmutableAllowLists": True,
            "crossBatchFileNameImageHashAndReportPathMustBeUnique": True,
            "legacyReportAndAnnotationHashesRevalidated": True,
            "standingCommercialAuthorizationApplied": True,
            "datasetMaterializationAndSourceIsolationStillRequired": True,
            "trainingUse": "prohibited-until-materialization-audit",
        },
        "summary": {
            "approvedReportCount": expected_images,
            "rejectedReportCount": 0,
            "uniqueImageCount": expected_images,
            "completeMaskCount": expected_masks,
            "redundantReportCount": 0,
            "redundantImageCount": 0,
            "conflictingImageCount": 0,
            "sourceGroupCount": len({str(item["sourceGroup"]) for item in combined}),
        },
        "batchCounts": {
            "candidate46-current-canonical": {
                "images": current_images,
                "masks": current_masks,
            },
            "candidate47-reused-reviewed-truth": {
                "images": len(reusable),
                "masks": reusable_masks,
            },
        },
        "batchByFileNameSha256": canonical_sha256(batch_by_file),
        "canonicalTruthsSha256": canonical_sha256(combined),
        "canonicalTruths": combined,
        "rejectedReports": [],
        "redundantReports": [],
        "conflicts": [],
        "errors": [],
    }
    auditor.validate_truth_index("train", result)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.tmp-", dir=output_path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(temporary, output_path)
    finally:
        if temporary.exists():
            temporary.unlink()
    print(
        json.dumps(
            {
                "ok": True,
                "images": expected_images,
                "masks": expected_masks,
                "reusedImages": len(reusable),
                "reusedMasks": reusable_masks,
                "newAnnotationCandidates": len(new_names),
                "canonicalTruthsSha256": result["canonicalTruthsSha256"],
                "output": str(output_path),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
