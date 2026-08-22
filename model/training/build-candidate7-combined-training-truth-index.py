#!/usr/bin/env python3
"""合并candidate6基线与candidate7两批新增真值，生成可物化的train200唯一索引。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


EXPECTED = {
    "baseline": (120, 636),
    "legacy-real": (33, 237),
    "new-positive": (47, 250),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"{label}不存在：{path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label}不是JSON对象：{path}")
    return value


def load_role_auditor() -> Any:
    path = Path(__file__).with_name("_protected_role_evidence.py")
    spec = importlib.util.spec_from_file_location("candidate7_role_evidence", path)
    if spec is None or spec.loader is None:
        raise ValueError("无法加载角色证据审计器")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_index(
    path: Path, label: str, expected_images: int, expected_masks: int, auditor: Any
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    document = load_json(path, label)
    truths = document.get("canonicalTruths")
    summary = document.get("summary")
    if (
        document.get("schemaVersion") != 1
        or document.get("ok") is not True
        or document.get("decision") != "approved_unique_training_truth_index"
        or not isinstance(truths, list)
        or not isinstance(summary, dict)
        or document.get("errors") not in (None, [])
        or document.get("conflicts") not in (None, [])
    ):
        raise ValueError(f"{label}不符合训练真值索引契约")
    if (
        len(truths) != expected_images
        or summary.get("uniqueImageCount") != expected_images
        or summary.get("completeMaskCount") != expected_masks
        or summary.get("rejectedReportCount") != 0
        or summary.get("conflictingImageCount") != 0
    ):
        raise ValueError(f"{label}不符合固定图片/mask/冲突基线")
    names: set[str] = set()
    hashes: set[str] = set()
    reports: set[str] = set()
    complete_masks = 0
    for number, item in enumerate(truths, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"{label}第{number}条真值不是对象")
        file_name = auditor.require_nonempty(item.get("fileName"), f"{label} fileName")
        image_hash = auditor.require_sha256(
            item.get("imageSha256"), f"{label} {file_name} image SHA-256"
        )
        auditor.require_nonempty(item.get("sourceGroup"), f"{label} {file_name} sourceGroup")
        report = auditor.require_current_file(
            item.get("reportPath"),
            item.get("reportSha256"),
            f"{label} {file_name} report",
        )
        mask_count = item.get("completeMaskCount")
        if isinstance(mask_count, bool) or not isinstance(mask_count, int) or mask_count < 1:
            raise ValueError(f"{label} {file_name}的completeMaskCount无效")
        if (
            file_name.casefold() in names
            or image_hash in hashes
            or str(report).casefold() in reports
        ):
            raise ValueError(f"{label}内部存在重复身份：{file_name}")
        names.add(file_name.casefold())
        hashes.add(image_hash)
        reports.add(str(report).casefold())
        complete_masks += mask_count
    if complete_masks != expected_masks:
        raise ValueError(f"{label}逐条mask总数与摘要不一致")
    return document, truths


def validate_standing_authorization(path: Path) -> dict[str, Any]:
    document = load_json(path, "项目长期商业授权")
    scope = document.get("scope", {})
    if (
        document.get("schemaVersion") != 1
        or document.get("decision")
        != "standing_project_commercial_resource_authorization_granted"
        or document.get("authorizedBy") != "user"
        or scope.get("projectScopedImageResources") != "commercial-use-permitted"
        or scope.get("localComputeResources") != "commercial-model-work-permitted"
        or scope.get("itemizedTrainingAuthorizationRequired") is not False
        or scope.get("trainingStartAuthorizationRequired") is not False
        or scope.get("atomicFreezeAuthorizationRequiredAfterEvidenceGates") is not False
    ):
        raise ValueError("项目长期商业授权记录无效")
    protected = set(document.get("roleRestrictionsNotRelaxed") or [])
    required = {
        "validation-remains-calibration-only",
        "frozen-test-remains-training-prohibited",
        "consumed-holdout-remains-training-prohibited",
        "future-independent-holdout-must-be-unseen-and-source-isolated",
    }
    if not required.issubset(protected):
        raise ValueError("项目长期商业授权缺少角色隔离保留条款")
    return document


def build_report(paths: dict[str, Path]) -> dict[str, Any]:
    auditor = load_role_auditor()
    validate_standing_authorization(paths["standingCommercialAuthorization"])
    batches: list[tuple[str, Path, dict[str, Any], list[dict[str, Any]]]] = []
    for name, key in (
        ("baseline", "baselineTruthIndex"),
        ("legacy-real", "legacyRealTruthIndex"),
        ("new-positive", "newPositiveTruthIndex"),
    ):
        expected_images, expected_masks = EXPECTED[name]
        document, truths = validate_index(
            paths[key], name, expected_images, expected_masks, auditor
        )
        batches.append((name, paths[key], document, truths))

    combined: list[dict[str, Any]] = []
    batch_by_file: dict[str, str] = {}
    seen_names: set[str] = set()
    seen_hashes: set[str] = set()
    seen_reports: set[str] = set()
    for batch_name, _, _, truths in batches:
        for truth in truths:
            file_name = str(truth["fileName"])
            image_hash = str(truth["imageSha256"])
            report_path = str(Path(str(truth["reportPath"])).resolve()).casefold()
            if (
                file_name.casefold() in seen_names
                or image_hash in seen_hashes
                or report_path in seen_reports
            ):
                raise ValueError(f"跨批次训练真值身份重复：{file_name}")
            seen_names.add(file_name.casefold())
            seen_hashes.add(image_hash)
            seen_reports.add(report_path)
            combined.append(truth)
            batch_by_file[file_name] = batch_name
    combined.sort(key=lambda item: (str(item["sourceGroup"]), str(item["fileName"])))
    total_masks = sum(int(item["completeMaskCount"]) for item in combined)
    if len(combined) != 200 or total_masks != 1123:
        raise ValueError("合并结果不再是200张/1123 mask")

    result = {
        "schemaVersion": 1,
        "ok": True,
        "decision": "approved_unique_training_truth_index",
        "inputs": {
            "truthRole": "train",
            "sourceIndexes": [
                {
                    "batch": name,
                    "path": str(path),
                    "sha256": sha256_file(path),
                    "images": len(truths),
                    "masks": int(document["summary"]["completeMaskCount"]),
                }
                for name, path, document, truths in batches
            ],
            "standingCommercialAuthorization": {
                "path": str(paths["standingCommercialAuthorization"]),
                "sha256": sha256_file(paths["standingCommercialAuthorization"]),
            },
        },
        "policy": {
            "uniqueKey": "item.fileName",
            "canonicalSelection": "three-hash-bound-approved-truth-index-union",
            "sourceIndexesAreImmutableAllowLists": True,
            "crossBatchFileNameImageHashAndReportPathMustBeUnique": True,
            "standingCommercialAuthorizationApplied": True,
            "itemizedAuthorizationPauseRequired": False,
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
            name: {
                "images": len(truths),
                "masks": int(document["summary"]["completeMaskCount"]),
            }
            for name, _, document, truths in batches
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


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--baseline-truth-index")
    value.add_argument("--legacy-real-truth-index")
    value.add_argument("--new-positive-truth-index")
    value.add_argument("--standing-commercial-authorization")
    value.add_argument("--output")
    value.add_argument("--verify-report")
    return value


def main() -> int:
    args = parser().parse_args()
    try:
        if args.verify_report:
            report_path = Path(args.verify_report).resolve()
            existing = load_json(report_path, "candidate7合并真值索引")
            inputs = existing.get("inputs", {})
            sources = inputs.get("sourceIndexes") or []
            by_batch = {
                str(item.get("batch")): Path(str(item.get("path", ""))).resolve()
                for item in sources
                if isinstance(item, dict)
            }
            auth = inputs.get("standingCommercialAuthorization", {})
            paths = {
                "baselineTruthIndex": by_batch.get("baseline", Path("missing")),
                "legacyRealTruthIndex": by_batch.get("legacy-real", Path("missing")),
                "newPositiveTruthIndex": by_batch.get("new-positive", Path("missing")),
                "standingCommercialAuthorization": Path(str(auth.get("path", ""))).resolve(),
            }
            rebuilt = build_report(paths)
            if rebuilt != existing:
                raise ValueError("candidate7合并真值索引与当前重放证据不一致")
            print(json.dumps({"ok": True, "decision": "verified", "report": str(report_path)}, ensure_ascii=False))
            return 0

        raw = {
            "baselineTruthIndex": args.baseline_truth_index,
            "legacyRealTruthIndex": args.legacy_real_truth_index,
            "newPositiveTruthIndex": args.new_positive_truth_index,
            "standingCommercialAuthorization": args.standing_commercial_authorization,
        }
        if not args.output or any(not value for value in raw.values()):
            raise ValueError("构建模式必须提供全部输入和--output")
        paths = {key: Path(str(value)).resolve() for key, value in raw.items()}
        result = build_report(paths)
        output = Path(args.output).resolve()
        if output in paths.values():
            raise ValueError("输出不得覆盖输入")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(
            json.dumps(
                {
                    "ok": True,
                    "images": result["summary"]["uniqueImageCount"],
                    "masks": result["summary"]["completeMaskCount"],
                    "canonicalTruthsSha256": result["canonicalTruthsSha256"],
                    "output": str(output),
                },
                ensure_ascii=False,
            )
        )
        return 0
    except (OSError, ValueError, json.JSONDecodeError, KeyError) as error:
        print(json.dumps({"ok": False, "decision": "error", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
