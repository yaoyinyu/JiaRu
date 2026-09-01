#!/usr/bin/env python3
"""把candidate48新终审真值追加到candidate47规范train索引。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
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


def load_auditor() -> Any:
    path = Path(__file__).with_name("_protected_role_evidence.py")
    spec = importlib.util.spec_from_file_location("candidate48_role_evidence", path)
    if spec is None or spec.loader is None:
        raise ValueError("无法加载角色证据审计器")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_standing_authorization(path: Path) -> None:
    document = load_json(path, "项目长期商业授权")
    scope = document.get("scope", {})
    protected = set(document.get("roleRestrictionsNotRelaxed") or [])
    if (
        document.get("schemaVersion") != 1
        or document.get("decision")
        != "standing_project_commercial_resource_authorization_granted"
        or document.get("authorizedBy") != "user"
        or scope.get("projectScopedImageResources") != "commercial-use-permitted"
        or scope.get("localComputeResources") != "commercial-model-work-permitted"
        or scope.get("itemizedTrainingAuthorizationRequired") is not False
        or scope.get("trainingStartAuthorizationRequired") is not False
        or not {
            "validation-remains-calibration-only",
            "frozen-test-remains-training-prohibited",
            "consumed-holdout-remains-training-prohibited",
            "future-independent-holdout-must-be-unseen-and-source-isolated",
        }.issubset(protected)
    ):
        raise ValueError("项目长期商业授权或角色隔离条款无效")


def validate_index(
    path: Path, label: str, auditor: Any, *, require_formal_minimum: bool
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    document = load_json(path, label)
    summary = document.get("summary", {})
    truths = document.get("canonicalTruths")
    if (
        document.get("schemaVersion") != 1
        or document.get("ok") is not True
        or document.get("decision") != "approved_unique_training_truth_index"
        or not isinstance(summary, dict)
        or not isinstance(truths, list)
        or len(truths) != summary.get("uniqueImageCount")
        or document.get("errors") not in (None, [])
        or document.get("conflicts") not in (None, [])
    ):
        raise ValueError(f"{label}不符合训练真值索引契约")
    if require_formal_minimum:
        auditor.validate_truth_index("train", document)
    elif len(truths) < 1 or summary.get("completeMaskCount", 0) < 1:
        raise ValueError(f"{label}没有可追加真值")
    return document, truths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-train-index", required=True, type=Path)
    parser.add_argument("--new-truth-index", required=True, type=Path)
    parser.add_argument("--standing-commercial-authorization", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    current_path = args.current_train_index.resolve()
    new_path = args.new_truth_index.resolve()
    authorization_path = args.standing_commercial_authorization.resolve()
    output_path = args.output.resolve()
    if output_path.exists() or output_path in {current_path, new_path, authorization_path}:
        raise ValueError("输出不得覆盖既有证据")

    auditor = load_auditor()
    validate_standing_authorization(authorization_path)
    current_document, current_truths = validate_index(
        current_path,
        "candidate47规范train索引",
        auditor,
        require_formal_minimum=True,
    )
    new_document, new_truths = validate_index(
        new_path,
        "candidate48新增真值索引",
        auditor,
        require_formal_minimum=False,
    )
    if len(new_truths) < 1:
        raise ValueError("candidate48新增真值索引为空")

    combined: list[dict[str, Any]] = []
    batch_by_file: dict[str, str] = {}
    seen_names: set[str] = set()
    seen_hashes: set[str] = set()
    seen_reports: set[str] = set()
    for batch, truths in (
        ("candidate47-current-canonical", current_truths),
        ("candidate48-new-reviewed-truth", new_truths),
    ):
        for item in truths:
            file_name = auditor.require_nonempty(item.get("fileName"), f"{batch} fileName")
            image_hash = auditor.require_sha256(
                item.get("imageSha256"), f"{batch} {file_name} image SHA-256"
            )
            report_path = auditor.require_current_file(
                item.get("reportPath"), item.get("reportSha256"), f"{batch} {file_name} report"
            )
            annotation_path = auditor.require_current_file(
                item.get("annotationPath"),
                item.get("annotationSha256"),
                f"{batch} {file_name} annotation",
            )
            auditor.require_nonempty(item.get("sourceGroup"), f"{batch} {file_name} sourceGroup")
            mask_count = item.get("completeMaskCount")
            if isinstance(mask_count, bool) or not isinstance(mask_count, int) or mask_count < 1:
                raise ValueError(f"{batch} {file_name} completeMaskCount无效")
            name_key = file_name.casefold()
            report_key = str(report_path).casefold()
            if name_key in seen_names or image_hash in seen_hashes or report_key in seen_reports:
                raise ValueError(f"跨批次训练真值身份重复：{file_name}")
            seen_names.add(name_key)
            seen_hashes.add(image_hash)
            seen_reports.add(report_key)
            normalized = dict(item)
            normalized["reportPath"] = str(report_path)
            normalized["annotationPath"] = str(annotation_path)
            combined.append(normalized)
            batch_by_file[file_name] = batch

    combined.sort(key=lambda item: (str(item["sourceGroup"]), str(item["fileName"])))
    total_masks = sum(int(item["completeMaskCount"]) for item in combined)
    current_images = int(current_document["summary"]["uniqueImageCount"])
    current_masks = int(current_document["summary"]["completeMaskCount"])
    new_masks = int(new_document["summary"]["completeMaskCount"])
    result = {
        "schemaVersion": 1,
        "ok": True,
        "decision": "approved_unique_training_truth_index",
        "inputs": {
            "truthRole": "train",
            "sourceIndexes": [
                {
                    "batch": "candidate47-current-canonical",
                    "path": str(current_path),
                    "sha256": sha256_file(current_path),
                    "images": current_images,
                    "masks": current_masks,
                },
                {
                    "batch": "candidate48-new-reviewed-truth",
                    "path": str(new_path),
                    "sha256": sha256_file(new_path),
                    "images": len(new_truths),
                    "masks": new_masks,
                },
            ],
            "standingCommercialAuthorization": {
                "path": str(authorization_path),
                "sha256": sha256_file(authorization_path),
            },
        },
        "policy": {
            "uniqueKey": "item.fileName",
            "canonicalSelection": "candidate47-canonical-plus-candidate48-new-reviewed-truth",
            "sourceIndexesAreImmutableAllowLists": True,
            "crossBatchFileNameImageHashAndReportPathMustBeUnique": True,
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
            "sourceGroupCount": len({str(item["sourceGroup"]) for item in combined}),
        },
        "batchCounts": {
            "candidate47-current-canonical": {"images": current_images, "masks": current_masks},
            "candidate48-new-reviewed-truth": {"images": len(new_truths), "masks": new_masks},
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
                "images": len(combined),
                "masks": total_masks,
                "newImages": len(new_truths),
                "newMasks": new_masks,
                "canonicalTruthsSha256": result["canonicalTruthsSha256"],
                "output": str(output_path),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
