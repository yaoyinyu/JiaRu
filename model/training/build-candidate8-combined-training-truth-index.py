#!/usr/bin/env python3
"""把candidate7已批准训练真值与candidate8新增真值合并为唯一训练索引。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


def load_candidate7_module() -> Any:
    path = Path(__file__).with_name("build-candidate7-combined-training-truth-index.py")
    spec = importlib.util.spec_from_file_location("candidate7_combined_truth", path)
    if spec is None or spec.loader is None:
        raise ValueError("无法加载candidate7真值校验器")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build(base_path: Path, reinforcement_path: Path, authorization_path: Path) -> dict[str, Any]:
    helper = load_candidate7_module()
    auditor = helper.load_role_auditor()
    helper.validate_standing_authorization(authorization_path)
    base_doc, base_truths = helper.validate_index(base_path, "candidate7-base", 200, 1123, auditor)
    reinforcement_doc, reinforcement_truths = helper.validate_index(
        reinforcement_path, "candidate8-reinforcement", 10, 87, auditor
    )

    combined: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    seen_hashes: set[str] = set()
    seen_reports: set[str] = set()
    batch_by_file: dict[str, str] = {}
    for batch, truths in (("candidate7-base", base_truths), ("candidate8-reinforcement", reinforcement_truths)):
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
    if len(combined) != 210 or masks != 1210:
        raise ValueError("candidate8合并结果不再是210张/1210 mask")

    sources = [
        ("candidate7-base", base_path, base_doc, base_truths),
        ("candidate8-reinforcement", reinforcement_path, reinforcement_doc, reinforcement_truths),
    ]
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
                    "sha256": sha256_file(path),
                    "images": len(truths),
                    "masks": int(document["summary"]["completeMaskCount"]),
                }
                for batch, path, document, truths in sources
            ],
            "standingCommercialAuthorization": {
                "path": str(authorization_path),
                "sha256": sha256_file(authorization_path),
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
            "approvedReportCount": 210,
            "rejectedReportCount": 0,
            "uniqueImageCount": 210,
            "completeMaskCount": 1210,
            "redundantReportCount": 0,
            "redundantImageCount": 0,
            "conflictingImageCount": 0,
            "sourceGroupCount": len({str(item["sourceGroup"]) for item in combined}),
        },
        "batchCounts": {
            batch: {"images": len(truths), "masks": int(document["summary"]["completeMaskCount"])}
            for batch, _, document, truths in sources
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
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-truth-index", required=True)
    parser.add_argument("--reinforcement-truth-index", required=True)
    parser.add_argument("--standing-commercial-authorization", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        inputs = [Path(value).resolve() for value in (
            args.base_truth_index,
            args.reinforcement_truth_index,
            args.standing_commercial_authorization,
        )]
        output = Path(args.output).resolve()
        if output in inputs or output.exists():
            raise ValueError("输出不得覆盖输入或既有证据")
        result = build(inputs[0], inputs[1], inputs[2])
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
        print(json.dumps({"ok": True, "images": 210, "masks": 1210, "canonicalTruthsSha256": result["canonicalTruthsSha256"], "output": str(output)}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, json.JSONDecodeError, KeyError) as error:
        print(json.dumps({"ok": False, "decision": "error", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
