#!/usr/bin/env python3
"""建立循环015生成正图的隔离、哈希绑定标注工作区。"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any


WORKSPACE_DECISION = "development_cycle_015_generated_annotation_workspace_ready_candidate_only"
TARGET_SOURCE_QUALIFIED = 133
CANONICAL_INDEX_DECISION = "approved_unique_training_truth_index"
CYCLE012_TRUTH_DECISION = "development_cycle_012_positive_truth_ready_for_materialization"
DEVELOPMENT_TRUTH_DECISION = "approved_unique_development_evaluation_truth_index"


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


def truth_identities(documents: list[dict[str, Any]]) -> dict[str, set[str]]:
    identities = {"fileName": set(), "imageSha256": set(), "sourceGroup": set()}
    for document in documents:
        rows = document.get("canonicalTruths")
        if not isinstance(rows, list):
            raise ValueError("训练真值索引缺少canonicalTruths数组")
        for row in rows:
            name = str(row.get("fileName") or "").casefold()
            image_hash = str(row.get("imageSha256") or row.get("sha256") or "").lower()
            group = str(row.get("sourceGroup") or row.get("parentSourceGroup") or "")
            if name:
                identities["fileName"].add(name)
            if len(image_hash) == 64:
                identities["imageSha256"].add(image_hash)
            if group:
                identities["sourceGroup"].add(group)
    return identities


def assert_no_truth_duplicates(items: list[dict[str, Any]], identities: dict[str, set[str]]) -> None:
    for index, item in enumerate(items, start=1):
        values = {
            "fileName": str(item.get("fileName") or "").casefold(),
            "imageSha256": str(item.get("imageSha256") or "").lower(),
            "sourceGroup": str(item.get("sourceGroup") or ""),
        }
        for field, value in values.items():
            if not value:
                raise ValueError(f"第{index}项缺少{field}")
            if value in identities[field]:
                raise ValueError(f"第{index}项与既有训练真值重复{field}：{value}")


def select_pending_items(
    intake_items: list[dict[str, Any]], existing_development_truth: dict[str, Any] | None
) -> tuple[list[dict[str, Any]], int]:
    if existing_development_truth is None:
        return intake_items, 0
    if (
        existing_development_truth.get("ok") is not True
        or existing_development_truth.get("decision") != DEVELOPMENT_TRUTH_DECISION
        or (existing_development_truth.get("inputs") or {}).get("truthRole") != "development-evaluation"
        or (existing_development_truth.get("policy") or {}).get("trainingUse") != "prohibited"
    ):
        raise ValueError("既有开发评估真值索引无效")
    canonical = existing_development_truth.get("canonicalTruths")
    summary = existing_development_truth.get("summary") or {}
    if (
        not isinstance(canonical, list)
        or summary.get("uniqueImageCount") != len(canonical)
        or summary.get("conflictingImageCount") != 0
    ):
        raise ValueError("既有开发评估真值计数或冲突状态漂移")
    intake_by_name = {str(item.get("fileName") or "").casefold(): item for item in intake_items}
    consumed_names: set[str] = set()
    for index, truth in enumerate(canonical, start=1):
        name, image_hash, group = (
            str(truth.get("fileName") or "").casefold(),
            str(truth.get("imageSha256") or "").lower(),
            str(truth.get("sourceGroup") or ""),
        )
        intake = intake_by_name.get(name)
        if intake is None:
            raise ValueError(f"既有开发评估真值不属于当前累计来源清单：第{index}项 {name}")
        if image_hash != str(intake.get("imageSha256") or "").lower() or group != intake.get("sourceGroup"):
            raise ValueError(f"既有开发评估真值与当前累计来源身份冲突：{name}")
        consumed_names.add(name)
    pending = [item for item in intake_items if str(item.get("fileName") or "").casefold() not in consumed_names]
    if not pending:
        raise ValueError("当前累计来源没有待标注增量")
    return pending, len(canonical)


def validate_inputs(
    intake_path: Path, canonical_index_path: Path, cycle012_truth_path: Path,
    existing_development_truth_path: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, Any]], int]:
    intake = read_object(intake_path, "循环015生成来源审计")
    canonical_index = read_object(canonical_index_path, "权威规范训练真值索引")
    cycle012_truth = read_object(cycle012_truth_path, "循环012新增训练真值")
    items = intake.get("items")
    item_count = len(items) if isinstance(items, list) else -1
    expected_decision = (
        "freeze_3_new_source_qualified_candidates_continue_to_133"
        if item_count == 3
        else f"freeze_{item_count}_cumulative_source_qualified_candidates_continue_to_133"
    )
    if (
        intake.get("ok") is not True
        or intake.get("decision") != expected_decision
        or intake.get("trainingUse") != "prohibited"
        or intake.get("formalPromotionAllowed") is not False
    ):
        raise ValueError("循环015生成来源审计未通过动态累计候选冻结合同")
    counts = intake.get("counts") or {}
    expected_nails = (
        sum(int(item.get("fullyVisibleNails") or 0) for item in items)
        if isinstance(items, list)
        else -1
    )
    if (
        not isinstance(items, list)
        or not 1 <= len(items) <= TARGET_SOURCE_QUALIFIED
        or counts.get("sourceQualifiedImages") != len(items)
        or counts.get("sourceGroups") != len(items)
        or counts.get("fullyVisibleNails") != expected_nails
        or any(not 1 <= int(item.get("fullyVisibleNails") or 0) <= 10 for item in items)
        or counts.get("identityOrRoleOverlaps") != 0
    ):
        raise ValueError("循环015冻结计数或隔离结论漂移")
    if canonical_index.get("ok") is not True or canonical_index.get("decision") != CANONICAL_INDEX_DECISION:
        raise ValueError("权威规范训练真值索引无效")
    if cycle012_truth.get("ok") is not True or cycle012_truth.get("decision") != CYCLE012_TRUTH_DECISION:
        raise ValueError("循环012新增训练真值无效")
    if len(canonical_index.get("canonicalTruths") or []) != 343:
        raise ValueError("权威规范训练真值索引不再是343张")
    if len(cycle012_truth.get("canonicalTruths") or []) != 13:
        raise ValueError("循环012新增训练真值不再是13张")
    assert_no_truth_duplicates(items, truth_identities([canonical_index, cycle012_truth]))
    existing_development_truth = (
        read_object(existing_development_truth_path, "既有开发评估真值")
        if existing_development_truth_path is not None
        else None
    )
    pending_items, existing_count = select_pending_items(items, existing_development_truth)
    return intake, canonical_index, cycle012_truth, pending_items, existing_count


def verify_workspace(report_path: Path) -> dict[str, Any]:
    report_path = report_path.resolve()
    report = read_object(report_path, "待重放循环015标注工作区")
    if report.get("ok") is not True or report.get("decision") != WORKSPACE_DECISION:
        raise ValueError("标注工作区报告合同无效")
    inputs = report.get("inputs") or {}
    bindings: dict[str, Path] = {}
    required_bindings = ["generatedIntake", "canonicalTruthIndex", "cycle012PositiveTruth"]
    if "existingDevelopmentEvaluationTruth" in inputs:
        required_bindings.append("existingDevelopmentEvaluationTruth")
    for key in required_bindings:
        binding = inputs.get(key) or {}
        path = Path(str(binding.get("path") or "")).resolve()
        if not path.is_file() or sha256_file(path) != binding.get("sha256"):
            raise ValueError(f"{key}绑定漂移")
        bindings[key] = path
    intake, _, _, pending_items, existing_count = validate_inputs(
        bindings["generatedIntake"], bindings["canonicalTruthIndex"], bindings["cycle012PositiveTruth"],
        bindings.get("existingDevelopmentEvaluationTruth"),
    )
    expected_by_name = {str(item["fileName"]): item for item in pending_items}
    rows = report.get("items") or []
    if len(rows) != len(expected_by_name) or {str(row.get("fileName") or "") for row in rows} != set(expected_by_name):
        raise ValueError("标注工作区未精确覆盖冻结合格图片")
    for row in rows:
        name = str(row["fileName"])
        expected = expected_by_name[name]
        source_path = Path(str(row.get("sourcePath") or "")).resolve()
        workspace_path = Path(str(row.get("workspacePath") or "")).resolve()
        expected_hash = str(expected["imageSha256"])
        if (
            row.get("materializationMethod") != "copy"
            or row.get("trainingUse") != "prohibited"
            or row.get("annotationTruthStatus") != "not-started"
            or row.get("sourceGroup") != expected.get("sourceGroup")
            or row.get("sha256") != expected_hash
            or not source_path.is_file()
            or not workspace_path.is_file()
            or sha256_file(source_path) != expected_hash
            or sha256_file(workspace_path) != expected_hash
        ):
            raise ValueError(f"标注工作区图片身份或隔离复制漂移：{name}")
        try:
            if os.path.samefile(source_path, workspace_path):
                raise ValueError(f"标注工作区错误复用了源文件：{name}")
        except OSError as error:
            raise ValueError(f"无法验证标注工作区文件独立性：{name}") from error
    expected_counts = {
        "images": len(expected_by_name),
        "sourceGroups": len(expected_by_name),
        "shards": len(expected_by_name),
        "expectedFullyVisibleNails": sum(int(item["fullyVisibleNails"]) for item in expected_by_name.values()),
        "truthFileNameOverlaps": 0,
        "truthImageSha256Overlaps": 0,
        "truthSourceGroupOverlaps": 0,
        "copiedImages": len(expected_by_name),
    }
    if existing_count:
        expected_counts.update({
            "cumulativeSourceQualifiedImages": len(intake["items"]),
            "existingDevelopmentEvaluationTruthImages": existing_count,
            "pendingIncrementImages": len(expected_by_name),
        })
    if (report.get("counts") or {}) != expected_counts:
        raise ValueError("标注工作区汇总漂移")
    return report


def build_workspace(
    intake_path: Path, canonical_index_path: Path, cycle012_truth_path: Path, output_dir: Path,
    existing_development_truth_path: Path | None = None,
) -> Path:
    intake_path = intake_path.resolve()
    canonical_index_path = canonical_index_path.resolve()
    cycle012_truth_path = cycle012_truth_path.resolve()
    output_dir = output_dir.resolve()
    if existing_development_truth_path is not None:
        existing_development_truth_path = existing_development_truth_path.resolve()
    intake, _, _, pending_items, existing_count = validate_inputs(
        intake_path, canonical_index_path, cycle012_truth_path, existing_development_truth_path
    )
    if output_dir.exists():
        raise ValueError(f"输出目录已存在，禁止覆盖：{output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.tmp-", dir=output_dir.parent))
    try:
        images_dir = temporary / "images"
        shards_dir = temporary / "shards"
        images_dir.mkdir()
        shards_dir.mkdir()
        rows: list[dict[str, Any]] = []
        for shard_index, item in enumerate(pending_items, start=1):
            source_path = Path(str(item["path"])).resolve()
            expected_hash = str(item["imageSha256"])
            if not source_path.is_file() or sha256_file(source_path) != expected_hash:
                raise ValueError(f"冻结源图缺失或漂移：{source_path}")
            target_path = images_dir / str(item["fileName"])
            shutil.copy2(source_path, target_path)
            if sha256_file(target_path) != expected_hash or os.path.samefile(source_path, target_path):
                raise ValueError(f"隔离复制失败：{item['fileName']}")
            final_target = output_dir / "images" / target_path.name
            record = {
                "fileName": item["fileName"],
                "sourcePath": str(source_path),
                "workspacePath": str(final_target),
                "sha256": expected_hash,
                "sourceGroup": item["sourceGroup"],
                "assignedRole": "development-evaluation-extension",
                "expectedFullyVisibleNails": item["fullyVisibleNails"],
                "shardIndex": shard_index,
                "materializationMethod": "copy",
                "trainingUse": "prohibited",
                "annotationTruthStatus": "not-started",
            }
            rows.append(record)
            shard_path = shards_dir / f"annotation-shard-{shard_index:03d}.csv"
            with shard_path.open("w", encoding="utf-8", newline="") as target:
                writer = csv.DictWriter(target, fieldnames=[
                    "fileName", "sha256", "sourceGroup", "expectedFullyVisibleNails",
                    "candidateCount", "reviewStatus", "issueCodes", "note",
                ])
                writer.writeheader()
                writer.writerow({
                    "fileName": record["fileName"],
                    "sha256": record["sha256"],
                    "sourceGroup": record["sourceGroup"],
                    "expectedFullyVisibleNails": record["expectedFullyVisibleNails"],
                    "candidateCount": "",
                    "reviewStatus": "",
                    "issueCodes": "",
                    "note": "",
                })
        report_inputs = {
            "generatedIntake": {"path": str(intake_path), "sha256": sha256_file(intake_path)},
            "canonicalTruthIndex": {"path": str(canonical_index_path), "sha256": sha256_file(canonical_index_path)},
            "cycle012PositiveTruth": {"path": str(cycle012_truth_path), "sha256": sha256_file(cycle012_truth_path)},
        }
        if existing_development_truth_path is not None:
            report_inputs["existingDevelopmentEvaluationTruth"] = {
                "path": str(existing_development_truth_path),
                "sha256": sha256_file(existing_development_truth_path),
            }
        counts = {
            "images": len(rows),
            "sourceGroups": len(rows),
            "shards": len(rows),
            "expectedFullyVisibleNails": sum(int(row["expectedFullyVisibleNails"]) for row in rows),
            "truthFileNameOverlaps": 0,
            "truthImageSha256Overlaps": 0,
            "truthSourceGroupOverlaps": 0,
            "copiedImages": len(rows),
        }
        if existing_count:
            counts.update({
                "cumulativeSourceQualifiedImages": len(intake["items"]),
                "existingDevelopmentEvaluationTruthImages": existing_count,
                "pendingIncrementImages": len(rows),
            })
        report = {
            "schemaVersion": 1,
            "ok": True,
            "decision": WORKSPACE_DECISION,
            "inputs": report_inputs,
            "imageDir": str(output_dir / "images"),
            "counts": counts,
            "policy": {
                "sourceGroupsRemainAtomicAcrossShards": True,
                "oneSourceGroupPerShard": True,
                "copyOnlyNoHardlinks": True,
                "sourcePixelsRemainImmutable": True,
                "workspaceDoesNotApproveMasks": True,
                "workspaceDoesNotGrantTrainingUse": True,
                "originalResolutionPerNailReviewRequired": True,
            },
            "items": rows,
            "shards": [
                {
                    "index": index,
                    "path": str(output_dir / "shards" / f"annotation-shard-{index:03d}.csv"),
                    "sha256": sha256_file(shards_dir / f"annotation-shard-{index:03d}.csv"),
                    "images": 1,
                    "sourceGroups": [row["sourceGroup"]],
                }
                for index, row in enumerate(rows, start=1)
            ],
            "trainingUse": "prohibited",
            "formalPromotionAllowed": False,
            "nextAction": "generate_candidate_masks_then_complete_original_resolution_per_nail_review",
            "releaseState": "hold",
            "productState": "hold",
            "errors": [],
        }
        (temporary / "annotation-workspace-manifest.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(temporary, output_dir)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    report_path = output_dir / "annotation-workspace-manifest.json"
    verify_workspace(report_path)
    return report_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generated-intake")
    parser.add_argument("--canonical-truth-index")
    parser.add_argument("--cycle012-positive-truth")
    parser.add_argument("--existing-development-evaluation-truth")
    parser.add_argument("--output-dir")
    parser.add_argument("--verify-report")
    args = parser.parse_args()
    if args.verify_report:
        report_path = Path(args.verify_report).resolve()
        report = verify_workspace(report_path)
        print(json.dumps({"ok": True, "decision": report["decision"], "reportSha256": sha256_file(report_path)}, ensure_ascii=False))
        return 0
    if not all((args.generated_intake, args.canonical_truth_index, args.cycle012_positive_truth, args.output_dir)):
        raise ValueError("构建模式缺少必填参数")
    report_path = build_workspace(
        Path(args.generated_intake), Path(args.canonical_truth_index),
        Path(args.cycle012_positive_truth), Path(args.output_dir),
        Path(args.existing_development_evaluation_truth) if args.existing_development_evaluation_truth else None,
    )
    report = read_object(report_path, "新建标注工作区")
    print(json.dumps({"ok": True, "decision": report["decision"], "counts": report["counts"], "report": str(report_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
