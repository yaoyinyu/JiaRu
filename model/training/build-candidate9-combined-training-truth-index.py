#!/usr/bin/env python3
"""合并candidate8基线与candidate9教师审核真值，生成可物化的唯一训练索引。"""

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
    spec = importlib.util.spec_from_file_location("candidate9_truth_helper", path)
    if spec is None or spec.loader is None:
        raise ValueError("无法加载训练真值校验器")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-truth-index", required=True, type=Path)
    parser.add_argument("--reinforcement-truth-index", required=True, type=Path)
    parser.add_argument("--standing-commercial-authorization", required=True, type=Path)
    parser.add_argument("--expected-reinforcement-images", type=int, default=11)
    parser.add_argument("--expected-reinforcement-masks", type=int, default=75)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    base_path = args.base_truth_index.resolve()
    reinforcement_path = args.reinforcement_truth_index.resolve()
    authorization_path = args.standing_commercial_authorization.resolve()
    output = args.output.resolve()
    if output.exists() or output in {base_path, reinforcement_path, authorization_path}:
        raise ValueError("输出不得覆盖既有证据")
    helper = load_helper()
    auditor = helper.load_role_auditor()
    helper.validate_standing_authorization(authorization_path)
    base_doc, base_truths = helper.validate_index(base_path, "candidate8-base", 210, 1210, auditor)
    reinforcement_images = args.expected_reinforcement_images
    reinforcement_masks = args.expected_reinforcement_masks
    if reinforcement_images < 11 or reinforcement_masks < 75:
        raise ValueError("candidate9教师增量不得低于首轮11张/75 mask")
    reinforcement_doc, reinforcement_truths = helper.validate_index(
        reinforcement_path,
        "candidate9-reinforcement",
        reinforcement_images,
        reinforcement_masks,
        auditor,
    )

    combined: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    seen_hashes: set[str] = set()
    seen_reports: set[str] = set()
    batch_by_file: dict[str, str] = {}
    for batch, truths in (("candidate8-base", base_truths), ("candidate9-reinforcement", reinforcement_truths)):
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
    masks = sum(int(item["completeMaskCount"]) for item in combined)
    expected_images = 210 + reinforcement_images
    expected_masks = 1210 + reinforcement_masks
    if len(combined) != expected_images or masks != expected_masks:
        raise ValueError(f"candidate9合并结果不再是{expected_images}张/{expected_masks} mask")
    sources = [
        ("candidate8-base", base_path, base_doc, base_truths),
        ("candidate9-reinforcement", reinforcement_path, reinforcement_doc, reinforcement_truths),
    ]
    result = {
        "schemaVersion": 1,
        "ok": True,
        "decision": "approved_unique_training_truth_index",
        "inputs": {
            "truthRole": "train",
            "sourceIndexes": [{
                "batch": batch, "path": str(path), "sha256": sha256_file(path),
                "images": len(truths), "masks": int(document["summary"]["completeMaskCount"]),
            } for batch, path, document, truths in sources],
            "standingCommercialAuthorization": {"path": str(authorization_path), "sha256": sha256_file(authorization_path)},
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
            "approvedReportCount": expected_images, "rejectedReportCount": 0,
            "uniqueImageCount": expected_images, "completeMaskCount": expected_masks,
            "redundantReportCount": 0, "redundantImageCount": 0,
            "conflictingImageCount": 0,
            "sourceGroupCount": len({str(item["sourceGroup"]) for item in combined}),
        },
        "batchCounts": {batch: {"images": len(truths), "masks": int(document["summary"]["completeMaskCount"])} for batch, _, document, truths in sources},
        "batchByFileNameSha256": canonical_sha256(batch_by_file),
        "canonicalTruthsSha256": canonical_sha256(combined),
        "canonicalTruths": combined,
        "rejectedReports": [], "redundantReports": [], "conflicts": [], "errors": [],
    }
    auditor.validate_truth_index("train", result)
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{output.name}.tmp-", dir=output.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()
    print(json.dumps({"ok": True, "images": expected_images, "masks": expected_masks, "canonicalTruthsSha256": result["canonicalTruthsSha256"], "output": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
