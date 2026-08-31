#!/usr/bin/env python3
"""合并candidate28规范基线与candidate35边界难例真值。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def load_helper() -> Any:
    path = Path(__file__).with_name("build-candidate7-combined-training-truth-index.py")
    spec = importlib.util.spec_from_file_location("candidate35_truth_helper", path)
    if spec is None or spec.loader is None:
        raise ValueError("无法加载训练真值校验器")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-truth-index", required=True, type=Path)
    parser.add_argument("--boundary-truth-index", required=True, type=Path)
    parser.add_argument("--standing-commercial-authorization", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    base_path = args.base_truth_index.resolve()
    boundary_path = args.boundary_truth_index.resolve()
    authorization_path = args.standing_commercial_authorization.resolve()
    output_path = args.output.resolve()
    if output_path.exists() or output_path in {base_path, boundary_path, authorization_path}:
        raise ValueError("输出不得覆盖既有证据")

    helper = load_helper()
    auditor = helper.load_role_auditor()
    helper.validate_standing_authorization(authorization_path)
    base_document, base_truths = helper.validate_index(base_path, "candidate28-base", 274, 1652, auditor)
    boundary_summary = json.loads(boundary_path.read_text(encoding="utf-8")).get("summary", {})
    boundary_images = int(boundary_summary.get("uniqueImageCount", 0))
    boundary_masks = int(boundary_summary.get("completeMaskCount", 0))
    if boundary_images < 11 or boundary_masks < 59:
        raise ValueError("candidate35边界真值不得低于已审核基线11张/59 mask")
    boundary_document, boundary_truths = helper.validate_index(
        boundary_path, "candidate35-boundary", boundary_images, boundary_masks, auditor
    )

    combined: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    seen_hashes: set[str] = set()
    seen_reports: set[str] = set()
    batch_by_file: dict[str, str] = {}
    batches = (
        ("candidate28-base", base_path, base_document, base_truths),
        ("candidate35-boundary", boundary_path, boundary_document, boundary_truths),
    )
    for batch, _, _, truths in batches:
        for truth in truths:
            name = str(truth["fileName"])
            image_hash = str(truth["imageSha256"])
            report = str(Path(str(truth["reportPath"])).resolve()).casefold()
            if name.casefold() in seen_names or image_hash in seen_hashes or report in seen_reports:
                raise ValueError(f"跨批次训练真值身份重复：{name}")
            seen_names.add(name.casefold())
            seen_hashes.add(image_hash)
            seen_reports.add(report)
            batch_by_file[name] = batch
            combined.append(truth)
    combined.sort(key=lambda item: (str(item["sourceGroup"]), str(item["fileName"])))
    expected_images = len(base_truths) + boundary_images
    expected_masks = int(base_document["summary"]["completeMaskCount"]) + boundary_masks
    if len(combined) != expected_images or sum(int(item["completeMaskCount"]) for item in combined) != expected_masks:
        raise ValueError("candidate35合并结果与两个输入索引的权威计数不一致")

    result = {
        "schemaVersion": 1,
        "ok": True,
        "decision": "approved_unique_training_truth_index",
        "inputs": {
            "truthRole": "train",
            "sourceIndexes": [
                {
                    "batch": batch,
                    "path": str(path),
                    "sha256": sha256_path(path),
                    "images": len(truths),
                    "masks": int(document["summary"]["completeMaskCount"]),
                }
                for batch, path, document, truths in batches
            ],
            "standingCommercialAuthorization": {
                "path": str(authorization_path),
                "sha256": sha256_path(authorization_path),
            },
        },
        "policy": {
            "uniqueKey": "item.fileName",
            "canonicalSelection": "two-hash-bound-approved-truth-index-union",
            "sourceIndexesAreImmutableAllowLists": True,
            "crossBatchFileNameImageHashAndReportPathMustBeUnique": True,
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
            batch: {"images": len(truths), "masks": int(document["summary"]["completeMaskCount"])}
            for batch, _, document, truths in batches
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
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{output_path.name}.tmp-", dir=output_path.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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
                "canonicalTruthsSha256": result["canonicalTruthsSha256"],
                "output": str(output_path),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
