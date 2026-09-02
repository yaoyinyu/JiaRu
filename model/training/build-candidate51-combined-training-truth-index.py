#!/usr/bin/env python3
"""把candidate51逐图终审真值安全追加到candidate50规范train索引。"""

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
        raise ValueError(f"{label}不是JSON对象")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def require_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{label}无效")
    int(value, 16)
    return value.lower()


def verify_truth_report(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    report = load_json(path, "candidate51训练真值报告")
    inputs = report.get("inputs", {})
    item = report.get("item", {})
    if (
        report.get("ok") is not True
        or report.get("decision") != "approved_as_training_truth_candidate_pending_dataset_materialization"
        or inputs.get("truthRole") != "train"
        or report.get("errors") not in (None, [])
        or item.get("invalidPolygonCount") != 0
        or item.get("overlapPairCount") != 0
        or item.get("trainingUse") != "prohibited-until-materialization-audit"
        or report.get("policy", {}).get("pairwisePolygonIntersectionArea") != 0
    ):
        raise ValueError(f"candidate51训练真值报告契约无效：{path}")
    evidence_pairs = (
        ("decision", "decisionSha256"),
        ("sourceSelection", "sourceSelectionSha256"),
        ("standingCommercialAuthorization", "standingCommercialAuthorizationSha256"),
        ("image", "imageSha256"),
        ("annotation", "annotationSha256"),
        ("manualReport", "manualReportSha256"),
        ("geometryAudit", "geometryAuditSha256"),
        ("reviewedOverlay", "reviewedOverlaySha256"),
    )
    for path_key, hash_key in evidence_pairs:
        evidence_path = Path(str(inputs.get(path_key, ""))).resolve()
        if not evidence_path.is_file() or sha256_file(evidence_path) != require_sha(inputs.get(hash_key), hash_key):
            raise ValueError(f"训练真值上游证据缺失或漂移：{path_key}")
    image_path = Path(str(inputs["image"])).resolve()
    annotation_path = Path(str(inputs["annotation"])).resolve()
    if (
        image_path.name != item.get("fileName")
        or inputs.get("imageSha256") != item.get("sha256")
        or not isinstance(item.get("sourceGroup"), str)
        or not item.get("sourceGroup")
        or isinstance(item.get("completeMaskCount"), bool)
        or not isinstance(item.get("completeMaskCount"), int)
        or item.get("completeMaskCount") < 1
    ):
        raise ValueError("训练真值条目身份或mask数无效")
    return report, {
        "reportPath": str(path),
        "reportName": path.name,
        "reportSha256": sha256_file(path),
        "sequence": 1,
        "fileName": item["fileName"],
        "imageSha256": item["sha256"],
        "sourceGroup": item["sourceGroup"],
        "completeMaskCount": item["completeMaskCount"],
        "annotationPath": str(annotation_path),
        "annotationSha256": inputs["annotationSha256"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-train-index", required=True, type=Path)
    parser.add_argument("--training-truth-report", required=True, action="append", type=Path)
    parser.add_argument("--standing-commercial-authorization", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    current_path = args.current_train_index.resolve()
    authorization_path = args.standing_commercial_authorization.resolve()
    report_paths = [path.resolve() for path in args.training_truth_report]
    output_path = args.output.resolve()
    protected = {current_path, authorization_path, *report_paths}
    if output_path.exists() or output_path in protected:
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
    if (
        authorization.get("decision") != "standing_project_commercial_resource_authorization_granted"
        or authorization.get("scope", {}).get("itemizedTrainingAuthorizationRequired") is not False
    ):
        raise ValueError("项目长期商业授权无效")
    if len(report_paths) < 1 or len(set(report_paths)) != len(report_paths):
        raise ValueError("candidate51训练真值报告必须非空且路径唯一")

    additions: list[dict[str, Any]] = []
    for report_path in report_paths:
        _, truth = verify_truth_report(report_path)
        additions.append(truth)
    existing_names = {str(value.get("fileName", "")).casefold() for value in truths}
    existing_hashes = {str(value.get("imageSha256", "")).lower() for value in truths}
    existing_reports = {str(value.get("reportPath", "")).casefold() for value in truths}
    addition_names: set[str] = set()
    addition_hashes: set[str] = set()
    addition_reports: set[str] = set()
    for truth in additions:
        name = str(truth["fileName"]).casefold()
        image_hash = str(truth["imageSha256"]).lower()
        report_name = str(truth["reportPath"]).casefold()
        if (
            name in existing_names or name in addition_names
            or image_hash in existing_hashes or image_hash in addition_hashes
            or report_name in existing_reports or report_name in addition_reports
        ):
            raise ValueError("candidate51与当前train或同批存在文件、图片或报告重复")
        addition_names.add(name)
        addition_hashes.add(image_hash)
        addition_reports.add(report_name)

    combined = [dict(value) for value in truths] + additions
    combined.sort(key=lambda value: (str(value["sourceGroup"]), str(value["fileName"])))
    total_masks = sum(int(value["completeMaskCount"]) for value in combined)
    batch_by_file = {
        str(value["fileName"]): (
            "candidate51-reviewed-truth" if str(value["fileName"]).casefold() in addition_names else "candidate50-canonical"
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
                    "batch": "candidate50-canonical",
                    "path": str(current_path),
                    "sha256": sha256_file(current_path),
                    "images": len(truths),
                    "masks": int(summary["completeMaskCount"]),
                },
                {
                    "batch": "candidate51-reviewed-truth",
                    "paths": [str(path) for path in report_paths],
                    "sha256": [sha256_file(path) for path in report_paths],
                    "images": len(additions),
                    "masks": sum(int(value["completeMaskCount"]) for value in additions),
                },
            ],
            "standingCommercialAuthorization": {
                "path": str(authorization_path),
                "sha256": sha256_file(authorization_path),
            },
        },
        "policy": {
            "uniqueKey": "item.fileName",
            "canonicalSelection": "candidate50-canonical-plus-candidate51-reviewed-truth",
            "sourceIndexesAreImmutableAllowLists": True,
            "fileNameImageHashAndReportPathMustBeUnique": True,
            "sameTrainRoleMayContainMultipleImagesFromOneSourceGroup": True,
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
            "candidate50-canonical": {"images": len(truths), "masks": int(summary["completeMaskCount"])},
            "candidate51-reviewed-truth": {
                "images": len(additions),
                "masks": sum(int(value["completeMaskCount"]) for value in additions),
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

    snapshot = {path: sha256_file(path) for path in protected}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{output_path.name}.tmp-", dir=output_path.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for path, expected in snapshot.items():
            if sha256_file(path) != expected:
                raise ValueError(f"输入证据在合并期间变化：{path}")
        os.replace(temporary, output_path)
    finally:
        if temporary.exists():
            temporary.unlink()
    print(json.dumps({
        "ok": True,
        "images": len(combined),
        "masks": total_masks,
        "newImages": len(additions),
        "newMasks": sum(int(value["completeMaskCount"]) for value in additions),
        "canonicalTruthsSha256": result["canonicalTruthsSha256"],
        "output": str(output_path),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
