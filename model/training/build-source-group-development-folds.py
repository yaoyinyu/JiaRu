#!/usr/bin/env python3
"""构建并重放仅限 train 角色的 sourceGroup 互斥开发折。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any


SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
TRAIN_ROLES = ("train-positive", "hard-negative")


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


def read_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"{label}不存在：{path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"{label}不是可读JSON：{path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label}必须是JSON对象：{path}")
    return value


def require_sha(value: Any, label: str) -> str:
    normalized = str(value or "").lower()
    if not SHA256_PATTERN.fullmatch(normalized):
        raise ValueError(f"{label}不是有效SHA-256")
    return normalized


def require_file_hash(path: Path, expected: Any, label: str) -> str:
    expected_sha = require_sha(expected, f"{label}预期哈希")
    if not path.is_file():
        raise ValueError(f"{label}不存在：{path}")
    actual = sha256_file(path)
    if actual != expected_sha:
        raise ValueError(
            f"{label}发生漂移：expected={expected_sha} actual={actual}: {path}"
        )
    return actual


def require_int(value: Any, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{label}必须是不小于{minimum}的整数")
    return value


def validate_dataset_yaml(path: Path) -> None:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key in {"path", "train", "val", "test", "task"}:
            values[key] = value.strip().strip("'\"")
    expected = {
        "path": ".",
        "train": "images/train",
        "val": "images/val",
        "test": "images/test",
        "task": "segment",
    }
    if values != expected:
        raise ValueError(f"数据集YAML路径或任务合同不规范：{values}")


def validate_inputs(
    index_path: Path,
    materialization_path: Path,
    audit_path: Path,
    dataset_yaml_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    index = read_json(index_path, "规范训练真值索引")
    materialization = read_json(materialization_path, "训练物化报告")
    audit = read_json(audit_path, "训练输入审计")
    validate_dataset_yaml(dataset_yaml_path)

    truths = index.get("canonicalTruths")
    index_summary = index.get("summary")
    if (
        index.get("ok") is not True
        or index.get("decision") != "approved_unique_training_truth_index"
        or index.get("errors") not in (None, [])
        or index.get("conflicts") not in (None, [])
        or not isinstance(truths, list)
        or not isinstance(index_summary, dict)
    ):
        raise ValueError("规范训练真值索引合同无效")
    if canonical_sha256(truths) != require_sha(
        index.get("canonicalTruthsSha256"), "canonicalTruthsSha256"
    ):
        raise ValueError("规范训练真值索引的canonicalTruthsSha256不匹配")

    records = materialization.get("records")
    counts = materialization.get("counts")
    roles = materialization.get("roles")
    inputs = materialization.get("inputs")
    if (
        materialization.get("ok") is not True
        or materialization.get("status") != "PASS"
        or materialization.get("decision")
        != "approved_canonical_candidate_dataset_materialization"
        or materialization.get("candidateTrainingEligible") is not True
        or materialization.get("trainingUse")
        != "permitted-for-candidate-training-only"
        or materialization.get("errors") not in (None, [])
        or not isinstance(records, list)
        or not isinstance(counts, dict)
        or not isinstance(roles, dict)
        or not isinstance(inputs, dict)
    ):
        raise ValueError("训练物化报告合同无效")
    if canonical_sha256(records) != require_sha(
        materialization.get("recordsSha256"), "recordsSha256"
    ):
        raise ValueError("训练物化报告的recordsSha256不匹配")
    bound_index = inputs.get("trainingTruthIndex")
    if not isinstance(bound_index, dict):
        raise ValueError("训练物化报告未绑定规范训练真值索引")
    if Path(str(bound_index.get("path", ""))).resolve() != index_path:
        raise ValueError("训练物化报告绑定了不同的规范训练真值索引")
    require_file_hash(index_path, bound_index.get("sha256"), "规范训练真值索引")

    audit_inputs = audit.get("inputs")
    if (
        audit.get("ok") is not True
        or audit.get("status") != "PASS"
        or audit.get("decision") != "approved_candidate_training_input"
        or audit.get("candidateTrainingEligible") is not True
        or audit.get("trainingUse") != "approved-for-candidate-training-only"
        or audit.get("errors") not in (None, [])
        or not isinstance(audit_inputs, dict)
    ):
        raise ValueError("训练输入审计合同无效")
    bound_materialization = audit_inputs.get("materializationReport")
    if not isinstance(bound_materialization, dict):
        raise ValueError("训练输入审计未绑定物化报告")
    if Path(str(bound_materialization.get("path", ""))).resolve() != materialization_path:
        raise ValueError("训练输入审计绑定了不同的物化报告")
    require_file_hash(
        materialization_path,
        bound_materialization.get("sha256"),
        "训练物化报告",
    )

    dataset_root = Path(str(materialization.get("outputDir", ""))).resolve()
    if dataset_yaml_path != dataset_root / "dataset.yaml":
        raise ValueError("数据集YAML不属于物化报告绑定的数据集根目录")
    for key in ("datasetFilesSha256", "allRolesSha256"):
        materialized_sha = require_sha(materialization.get(key), f"物化报告{key}")
        audited_sha = require_sha(audit.get(key), f"输入审计{key}")
        if materialized_sha != audited_sha:
            raise ValueError(f"物化报告与输入审计的{key}不一致")
    if Path(str(audit.get("outputDir", ""))).resolve() != dataset_root:
        raise ValueError("训练输入审计绑定了不同的数据集根目录")

    expected_counts = {
        "trainPositiveImages": 328,
        "positiveMasks": 1981,
        "hardNegativeImages": 160,
        "validationImages": 30,
        "validationMasks": 144,
        "testImages": 0,
        "orphanFiles": 0,
    }
    for key, expected in expected_counts.items():
        if require_int(counts.get(key), f"物化报告counts.{key}") != expected:
            raise ValueError(f"物化报告counts.{key}不等于冻结基线{expected}")
        if require_int(audit.get("counts", {}).get(key), f"输入审计counts.{key}") != expected:
            raise ValueError(f"输入审计counts.{key}不等于冻结基线{expected}")
    if (
        roles.get("train-positive", {}).get("sourceGroups") != 112
        or roles.get("hard-negative", {}).get("sourceGroups") != 16
        or roles.get("val", {}).get("sourceGroups") != 14
    ):
        raise ValueError("物化报告来源组计数不等于冻结基线")
    return index, materialization, audit


def normalize_records(
    index: dict[str, Any], materialization: dict[str, Any]
) -> tuple[list[dict[str, Any]], set[str]]:
    truths = index["canonicalTruths"]
    truth_by_name: dict[str, dict[str, Any]] = {}
    for number, truth in enumerate(truths, start=1):
        if not isinstance(truth, dict):
            raise ValueError(f"规范训练真值第{number}项不是对象")
        file_name = str(truth.get("fileName", ""))
        if not file_name or file_name in truth_by_name:
            raise ValueError("规范训练真值文件名为空或重复")
        truth_by_name[file_name] = truth

    normalized: list[dict[str, Any]] = []
    val_groups: set[str] = set()
    seen_names: set[str] = set()
    seen_hashes: set[str] = set()
    positive_names: set[str] = set()
    for number, record in enumerate(materialization["records"], start=1):
        if not isinstance(record, dict):
            raise ValueError(f"物化记录第{number}项不是对象")
        role = str(record.get("role", ""))
        source_group = str(record.get("sourceGroup", ""))
        file_name = str(record.get("fileName", ""))
        image_sha = require_sha(record.get("imageSha256"), f"记录{number}图片哈希")
        source_groups = record.get("sourceGroups")
        if (
            not source_group
            or not file_name
            or Path(file_name).name != file_name
            or not isinstance(source_groups, list)
            or source_group not in source_groups
        ):
            raise ValueError(f"物化记录第{number}项身份字段无效")
        if file_name.casefold() in seen_names or image_sha in seen_hashes:
            raise ValueError("物化记录存在重复文件名或图片哈希")
        seen_names.add(file_name.casefold())
        seen_hashes.add(image_sha)
        if role == "val":
            val_groups.update(str(value) for value in source_groups)
            continue
        if role not in TRAIN_ROLES:
            raise ValueError(f"开发折发现禁止角色：{role}")
        mask_count = require_int(record.get("maskCount"), f"记录{number} maskCount")
        if role == "train-positive":
            truth = truth_by_name.get(file_name)
            if truth is None:
                raise ValueError(f"正样本不在规范训练真值索引中：{file_name}")
            if (
                truth.get("imageSha256") != image_sha
                or truth.get("sourceGroup") != source_group
                or truth.get("completeMaskCount") != mask_count
            ):
                raise ValueError(f"正样本与规范训练真值索引不一致：{file_name}")
            positive_names.add(file_name)
        elif mask_count != 0:
            raise ValueError(f"困难负样本标签非空：{file_name}")
        normalized.append(
            {
                "fileName": file_name,
                "role": role,
                "sourceGroup": source_group,
                "sourceGroups": sorted({str(value) for value in source_groups}),
                "imageSha256": image_sha,
                "maskCount": mask_count,
            }
        )
    if positive_names != set(truth_by_name):
        raise ValueError("物化正样本与规范训练真值索引不是精确同一清单")
    train_groups = {
        group for record in normalized for group in record["sourceGroups"]
    }
    overlap = sorted(train_groups & val_groups)
    if overlap:
        raise ValueError(f"train与旧val来源组交叠：{overlap[:5]}")
    return sorted(normalized, key=lambda item: (item["role"], item["fileName"])), val_groups


def assign_groups(
    records: list[dict[str, Any]], fold_count: int, seed: str
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    by_group: dict[str, list[dict[str, Any]]] = {}
    group_role: dict[str, str] = {}
    for record in records:
        group = record["sourceGroup"]
        role = record["role"]
        if group in group_role and group_role[group] != role:
            raise ValueError(f"同一sourceGroup跨越正负训练角色：{group}")
        group_role[group] = role
        by_group.setdefault(group, []).append(record)

    assignments: dict[str, int] = {}
    assignment_rows: list[dict[str, Any]] = []
    for role in TRAIN_ROLES:
        groups = []
        for group, items in by_group.items():
            if group_role[group] != role:
                continue
            images = len(items)
            masks = sum(int(item["maskCount"]) for item in items)
            tie = hashlib.sha256(f"{seed}\0{role}\0{group}".encode("utf-8")).hexdigest()
            groups.append((group, items, images, masks, tie))
        groups.sort(key=lambda value: (-value[2], -value[3], value[4], value[0]))
        total_images = sum(value[2] for value in groups)
        total_masks = sum(value[3] for value in groups)
        target_images = total_images / fold_count
        target_masks = total_masks / fold_count if total_masks else 1.0
        loads = [
            {"images": 0, "masks": 0, "groups": 0} for _ in range(fold_count)
        ]
        for group, items, images, masks, _ in groups:
            def score(fold: int) -> tuple[float, float, int, int]:
                image_ratio = (loads[fold]["images"] + images) / target_images
                mask_ratio = (
                    (loads[fold]["masks"] + masks) / target_masks
                    if total_masks
                    else 0.0
                )
                return (
                    max(image_ratio, mask_ratio),
                    image_ratio + mask_ratio,
                    loads[fold]["groups"],
                    fold,
                )

            fold = min(range(fold_count), key=score)
            assignments[group] = fold
            loads[fold]["images"] += images
            loads[fold]["masks"] += masks
            loads[fold]["groups"] += 1
            assignment_rows.append(
                {
                    "sourceGroup": group,
                    "role": role,
                    "fold": fold,
                    "imageCount": images,
                    "maskCount": masks,
                    "recordIdentitiesSha256": canonical_sha256(
                        [
                            {
                                "fileName": item["fileName"],
                                "imageSha256": item["imageSha256"],
                            }
                            for item in sorted(items, key=lambda value: value["fileName"])
                        ]
                    ),
                }
            )
    return sorted(assignment_rows, key=lambda item: (item["role"], item["sourceGroup"])), assignments


def build_document(
    index_path: Path,
    materialization_path: Path,
    audit_path: Path,
    dataset_yaml_path: Path,
    fold_count: int,
    evaluation_fold: int,
    seed: str,
) -> dict[str, Any]:
    if fold_count < 3:
        raise ValueError("开发折至少需要3折")
    if evaluation_fold < 0 or evaluation_fold >= fold_count:
        raise ValueError("evaluationFold超出范围")
    if not seed.strip():
        raise ValueError("seed不能为空")
    index, materialization, audit = validate_inputs(
        index_path, materialization_path, audit_path, dataset_yaml_path
    )
    records, excluded_val_groups = normalize_records(index, materialization)
    group_rows, assignments = assign_groups(records, fold_count, seed)
    record_rows = [
        {
            **record,
            "fold": assignments[record["sourceGroup"]],
            "developmentRole": (
                "evaluation" if assignments[record["sourceGroup"]] == evaluation_fold else "training"
            ),
        }
        for record in records
    ]
    record_rows.sort(key=lambda item: (item["fold"], item["role"], item["fileName"]))
    folds: list[dict[str, Any]] = []
    for fold in range(fold_count):
        items = [item for item in record_rows if item["fold"] == fold]
        role_counts = {
            role: {
                "images": sum(1 for item in items if item["role"] == role),
                "masks": sum(item["maskCount"] for item in items if item["role"] == role),
                "sourceGroups": len(
                    {item["sourceGroup"] for item in items if item["role"] == role}
                ),
            }
            for role in TRAIN_ROLES
        }
        folds.append(
            {
                "fold": fold,
                "developmentRole": "evaluation" if fold == evaluation_fold else "training",
                "roles": role_counts,
                "recordsSha256": canonical_sha256(items),
            }
        )
    summary = {
        "foldCount": fold_count,
        "evaluationFold": evaluation_fold,
        "trainPositiveImages": sum(item["role"] == "train-positive" for item in records),
        "positiveMasks": sum(item["maskCount"] for item in records),
        "hardNegativeImages": sum(item["role"] == "hard-negative" for item in records),
        "sourceGroups": len(assignments),
        "positiveSourceGroups": sum(item["role"] == "train-positive" for item in group_rows),
        "hardNegativeSourceGroups": sum(item["role"] == "hard-negative" for item in group_rows),
        "excludedValidationSourceGroups": len(excluded_val_groups),
        "groupOverlapAcrossFolds": 0,
        "trainValidationSourceGroupOverlap": 0,
        "testOrHoldoutRecords": 0,
    }
    if summary != {
        "foldCount": fold_count,
        "evaluationFold": evaluation_fold,
        "trainPositiveImages": 328,
        "positiveMasks": 1981,
        "hardNegativeImages": 160,
        "sourceGroups": 128,
        "positiveSourceGroups": 112,
        "hardNegativeSourceGroups": 16,
        "excludedValidationSourceGroups": 14,
        "groupOverlapAcrossFolds": 0,
        "trainValidationSourceGroupOverlap": 0,
        "testOrHoldoutRecords": 0,
    }:
        raise ValueError(f"开发折汇总不等于冻结基线：{summary}")
    document: dict[str, Any] = {
        "schemaVersion": 1,
        "ok": True,
        "decision": "approved_train_internal_source_group_development_folds",
        "inputs": {
            "combinedTrainingTruthIndex": {
                "path": str(index_path),
                "sha256": sha256_file(index_path),
                "canonicalTruthsSha256": index["canonicalTruthsSha256"],
            },
            "materializationReport": {
                "path": str(materialization_path),
                "sha256": sha256_file(materialization_path),
                "recordsSha256": materialization["recordsSha256"],
            },
            "candidateInputAudit": {
                "path": str(audit_path),
                "sha256": sha256_file(audit_path),
                "datasetFilesSha256": audit["datasetFilesSha256"],
                "allRolesSha256": audit["allRolesSha256"],
            },
            "datasetYaml": {
                "path": str(dataset_yaml_path),
                "sha256": sha256_file(dataset_yaml_path),
            },
        },
        "policy": {
            "purpose": "train-internal-development-only",
            "formalCalibrationTestOrHoldout": False,
            "selectionUnit": "sourceGroup",
            "sourceGroupAtomic": True,
            "allSourceGroupsMutuallyExclusiveAcrossFolds": True,
            "positiveAndHardNegativeLoadsBalancedSeparately": True,
            "assignmentAlgorithm": "role-stratified-largest-group-first-normalized-greedy/v1",
            "seed": seed,
            "fixedEvaluationFold": evaluation_fold,
            "oldValidationRecordsExcluded": True,
            "testAndHoldoutRecordsExcluded": True,
            "winnerMayUseAllTrainRecordsForFullTraining": True,
        },
        "summary": summary,
        "folds": folds,
        "sourceGroupAssignmentsSha256": canonical_sha256(group_rows),
        "sourceGroupAssignments": group_rows,
        "recordsSha256": canonical_sha256(record_rows),
        "records": record_rows,
        "errors": [],
    }
    document["contentSha256"] = canonical_sha256(document)
    return document


def verify_plan(path: Path) -> dict[str, Any]:
    document = read_json(path, "开发折计划")
    if (
        document.get("schemaVersion") != 1
        or document.get("ok") is not True
        or document.get("decision")
        != "approved_train_internal_source_group_development_folds"
        or document.get("errors") not in (None, [])
    ):
        raise ValueError("开发折计划顶层合同无效")
    expected_content_sha = require_sha(document.get("contentSha256"), "contentSha256")
    without_content_sha = dict(document)
    without_content_sha.pop("contentSha256", None)
    if canonical_sha256(without_content_sha) != expected_content_sha:
        raise ValueError("开发折计划contentSha256不匹配")
    inputs = document.get("inputs")
    policy = document.get("policy")
    summary = document.get("summary")
    if not isinstance(inputs, dict) or not isinstance(policy, dict) or not isinstance(summary, dict):
        raise ValueError("开发折计划缺少inputs/policy/summary")
    bindings = {}
    for key in (
        "combinedTrainingTruthIndex",
        "materializationReport",
        "candidateInputAudit",
        "datasetYaml",
    ):
        binding = inputs.get(key)
        if not isinstance(binding, dict):
            raise ValueError(f"开发折计划缺少输入绑定：{key}")
        bound_path = Path(str(binding.get("path", ""))).resolve()
        require_file_hash(bound_path, binding.get("sha256"), key)
        bindings[key] = bound_path
    rebuilt = build_document(
        bindings["combinedTrainingTruthIndex"],
        bindings["materializationReport"],
        bindings["candidateInputAudit"],
        bindings["datasetYaml"],
        require_int(summary.get("foldCount"), "foldCount", 3),
        require_int(summary.get("evaluationFold"), "evaluationFold"),
        str(policy.get("seed", "")),
    )
    if canonical_sha256(rebuilt) != canonical_sha256(document):
        raise ValueError("开发折计划不能从冻结输入确定性重建")
    return document


def atomic_write_new(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise ValueError(f"输出已存在，禁止覆盖：{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.tmp-", dir=path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--combined-training-truth-index", type=Path)
    parser.add_argument("--materialization-report", type=Path)
    parser.add_argument("--candidate-input-audit", type=Path)
    parser.add_argument("--dataset-yaml", type=Path)
    parser.add_argument("--fold-count", type=int, default=5)
    parser.add_argument("--evaluation-fold", type=int, default=0)
    parser.add_argument("--seed", default="jiaru-train-source-group-development-v1")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-plan", type=Path)
    args = parser.parse_args()
    if args.verify_plan is not None:
        if any(
            value is not None
            for value in (
                args.combined_training_truth_index,
                args.materialization_report,
                args.candidate_input_audit,
                args.dataset_yaml,
                args.output,
            )
        ):
            raise ValueError("--verify-plan不能与构建参数并用")
        document = verify_plan(args.verify_plan.resolve())
        print(
            json.dumps(
                {
                    "ok": True,
                    "decision": document["decision"],
                    "contentSha256": document["contentSha256"],
                },
                ensure_ascii=False,
            )
        )
        return 0
    required = {
        "--combined-training-truth-index": args.combined_training_truth_index,
        "--materialization-report": args.materialization_report,
        "--candidate-input-audit": args.candidate_input_audit,
        "--dataset-yaml": args.dataset_yaml,
        "--output": args.output,
    }
    missing = [key for key, value in required.items() if value is None]
    if missing:
        raise ValueError(f"缺少构建参数：{', '.join(missing)}")
    index_path = args.combined_training_truth_index.resolve()
    materialization_path = args.materialization_report.resolve()
    audit_path = args.candidate_input_audit.resolve()
    dataset_yaml_path = args.dataset_yaml.resolve()
    output_path = args.output.resolve()
    document = build_document(
        index_path,
        materialization_path,
        audit_path,
        dataset_yaml_path,
        args.fold_count,
        args.evaluation_fold,
        args.seed,
    )
    input_snapshot = {
        path: sha256_file(path)
        for path in (index_path, materialization_path, audit_path, dataset_yaml_path)
    }
    atomic_write_new(output_path, document)
    for path, expected in input_snapshot.items():
        if sha256_file(path) != expected:
            raise ValueError(f"构建期间输入发生漂移：{path}")
    verify_plan(output_path)
    print(
        json.dumps(
            {
                "ok": True,
                "decision": document["decision"],
                "summary": document["summary"],
                "contentSha256": document["contentSha256"],
                "output": str(output_path),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
