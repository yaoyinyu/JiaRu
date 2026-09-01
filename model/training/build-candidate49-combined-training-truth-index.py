#!/usr/bin/env python3
"""把candidate49逐图终审真值安全追加到既有规范train索引。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def load_json(path: Path, label: str) -> dict[str, Any]:
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


def require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{label}无效")
    int(value, 16)
    return value.lower()


def require_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}为空")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-train-index", required=True, type=Path)
    parser.add_argument("--training-truth-report", required=True, type=Path)
    parser.add_argument("--standing-commercial-authorization", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    current_path = args.current_train_index.resolve()
    report_path = args.training_truth_report.resolve()
    authorization_path = args.standing_commercial_authorization.resolve()
    output_path = args.output.resolve()
    if output_path.exists() or output_path in {current_path, report_path, authorization_path}:
        raise ValueError("输出不得覆盖既有证据")

    current = load_json(current_path, "当前规范train索引")
    truths = current.get("canonicalTruths")
    summary = current.get("summary", {})
    if (
        current.get("ok") is not True
        or current.get("decision") != "approved_unique_training_truth_index"
        or not isinstance(truths, list)
        or len(truths) != summary.get("uniqueImageCount")
        or current.get("errors") not in (None, [])
        or current.get("conflicts") not in (None, [])
    ):
        raise ValueError("当前规范train索引契约无效")

    authorization = load_json(authorization_path, "项目长期商业授权")
    scope = authorization.get("scope", {})
    if (
        authorization.get("decision")
        != "standing_project_commercial_resource_authorization_granted"
        or scope.get("itemizedTrainingAuthorizationRequired") is not False
    ):
        raise ValueError("项目长期商业授权无效")

    report = load_json(report_path, "candidate49训练真值报告")
    inputs = report.get("inputs", {})
    item = report.get("item", {})
    if (
        report.get("ok") is not True
        or report.get("decision")
        != "approved_as_training_truth_candidate_pending_dataset_materialization"
        or inputs.get("truthRole") != "train"
        or report.get("errors") not in (None, [])
        or item.get("invalidPolygonCount") != 0
        or item.get("overlapPairCount") != 0
        or item.get("trainingUse") != "prohibited-until-materialization-audit"
    ):
        raise ValueError("candidate49训练真值报告未通过终审契约")

    image_path = Path(require_text(inputs.get("image"), "图片路径"))
    annotation_path = Path(require_text(inputs.get("annotation"), "标注路径"))
    image_hash = require_sha256(inputs.get("imageSha256"), "图片SHA-256")
    annotation_hash = require_sha256(inputs.get("annotationSha256"), "标注SHA-256")
    if sha256_file(image_path) != image_hash or sha256_file(annotation_path) != annotation_hash:
        raise ValueError("candidate49图片或标注发生写后漂移")
    file_name = require_text(item.get("fileName"), "fileName")
    source_group = require_text(item.get("sourceGroup"), "sourceGroup")
    mask_count = item.get("completeMaskCount")
    if isinstance(mask_count, bool) or not isinstance(mask_count, int) or mask_count < 1:
        raise ValueError("completeMaskCount无效")

    seen_names = {str(value.get("fileName", "")).casefold() for value in truths}
    seen_hashes = {str(value.get("imageSha256", "")).lower() for value in truths}
    seen_reports = {str(value.get("reportPath", "")).casefold() for value in truths}
    seen_groups = {str(value.get("sourceGroup", "")) for value in truths}
    if (
        file_name.casefold() in seen_names
        or image_hash in seen_hashes
        or str(report_path).casefold() in seen_reports
        or source_group in seen_groups
    ):
        raise ValueError("candidate49与当前train存在文件、图片、报告或来源组重复")

    new_truth = {
        "reportPath": str(report_path),
        "reportName": report_path.name,
        "reportSha256": sha256_file(report_path),
        "sequence": 1,
        "fileName": file_name,
        "imageSha256": image_hash,
        "sourceGroup": source_group,
        "completeMaskCount": mask_count,
        "annotationPath": str(annotation_path),
        "annotationSha256": annotation_hash,
    }
    combined = [dict(value) for value in truths] + [new_truth]
    combined.sort(key=lambda value: (str(value["sourceGroup"]), str(value["fileName"])))
    total_masks = sum(int(value["completeMaskCount"]) for value in combined)
    batch_by_file = {
        str(value["fileName"]): (
            "candidate49-reviewed-truth" if value["fileName"] == file_name else "current-canonical"
        )
        for value in combined
    }
    result = {
        "schemaVersion": 1,
        "ok": True,
        "decision": "approved_unique_training_truth_index",
        "inputs": {
            "truthRole": "train",
            "sourceIndexes": [
                {
                    "batch": "current-canonical",
                    "path": str(current_path),
                    "sha256": sha256_file(current_path),
                    "images": len(truths),
                    "masks": int(summary["completeMaskCount"]),
                },
                {
                    "batch": "candidate49-reviewed-truth",
                    "path": str(report_path),
                    "sha256": sha256_file(report_path),
                    "images": 1,
                    "masks": mask_count,
                },
            ],
            "standingCommercialAuthorization": {
                "path": str(authorization_path),
                "sha256": sha256_file(authorization_path),
            },
        },
        "policy": {
            "uniqueKey": "item.fileName",
            "canonicalSelection": "current-canonical-plus-candidate49-reviewed-truth",
            "sourceIndexesAreImmutableAllowLists": True,
            "crossBatchFileNameImageHashReportPathAndSourceGroupMustBeUnique": True,
            "standingCommercialAuthorizationApplied": True,
            "datasetMaterializationAndSourceIsolationStillRequired": True,
            "trainingUse": "prohibited-until-materialization-audit",
        },
        "summary": {
            "approvedReportCount": len(combined),
            "rejectedReportCount": 0,
            "uniqueImageCount": len(combined),
            "completeMaskCount": total_masks,
            "redundantReportCount": 0,
            "redundantImageCount": 0,
            "conflictingImageCount": 0,
            "sourceGroupCount": len({str(value["sourceGroup"]) for value in combined}),
        },
        "batchCounts": {
            "current-canonical": {"images": len(truths), "masks": int(summary["completeMaskCount"])},
            "candidate49-reviewed-truth": {"images": 1, "masks": mask_count},
        },
        "batchByFileNameSha256": canonical_sha256(batch_by_file),
        "canonicalTruthsSha256": canonical_sha256(combined),
        "canonicalTruths": combined,
        "rejectedReports": [],
        "redundantReports": [],
        "conflicts": [],
        "errors": [],
    }

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
                "images": len(combined),
                "masks": total_masks,
                "newImages": 1,
                "newMasks": mask_count,
                "canonicalTruthsSha256": result["canonicalTruthsSha256"],
                "output": str(output_path),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
