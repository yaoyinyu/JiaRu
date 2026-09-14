#!/usr/bin/env python3
"""只读重算循环015现有正图库存的当前角色隔离与首批供给缺口。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


TARGET_FIRST_BATCH = 50
TARGET_CLEAN_DEVELOPMENT = 352
FRESH_CALIBRATION_RESERVE = 30
FRESH_POSITIVE_HOLDOUT_RESERVE = 100


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def read_object(path: Path, label: str) -> dict[str, Any]:
    path = path.resolve()
    if not path.is_file():
        raise ValueError(f"{label}不存在：{path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label}不是JSON对象")
    return value


def binding(path: Path) -> dict[str, str]:
    path = path.resolve()
    return {"path": str(path), "sha256": sha256_file(path)}


def identity(record: dict[str, Any], label: str) -> tuple[str, str, str]:
    name = str(record.get("fileName") or "").casefold()
    image_hash = str(record.get("imageSha256") or record.get("sha256") or "").lower()
    group = str(record.get("sourceGroup") or record.get("parentSourceGroup") or "")
    if not name or len(image_hash) != 64 or not group:
        raise ValueError(f"{label}身份不完整")
    return name, image_hash, group


def identity_sets(records: list[dict[str, Any]], label: str) -> dict[str, set[str]]:
    result = {"fileName": set(), "imageSha256": set(), "sourceGroup": set()}
    for index, record in enumerate(records, start=1):
        name, image_hash, group = identity(record, f"{label}第{index}项")
        if name in result["fileName"] or image_hash in result["imageSha256"]:
            raise ValueError(f"{label}存在重复文件名或图片哈希")
        result["fileName"].add(name)
        result["imageSha256"].add(image_hash)
        result["sourceGroup"].add(group)
    return result


def overlap_reasons(record: dict[str, Any], used: dict[str, set[str]]) -> list[str]:
    name, image_hash, group = identity(record, "候选")
    values = {"fileName": name, "imageSha256": image_hash, "sourceGroup": group}
    return [field for field, value in values.items() if value in used[field]]


def selected_plan(inventory_path: Path, inventory: dict[str, Any], selected: list[dict[str, Any]]) -> dict[str, Any]:
    names = [str(item["fileName"]) for item in selected]
    return {
        "schemaVersion": 1,
        "ok": True,
        "decision": "source_selection_frozen_before_model_assistance",
        "inputs": {
            "inventory": str(inventory_path.resolve()),
            "inventorySha256": sha256_file(inventory_path.resolve()),
            "inventoryItemsSha256": inventory["itemsSha256"],
        },
        "selectionBasis": "metadata-only current-role isolation; no model inference or output selection",
        "selectedFileNames": names,
        "selectedFileNamesSha256": canonical_sha256(names),
        "counts": {
            "selectedImages": len(names),
            "selectedSourceGroups": len({str(item["sourceGroup"]) for item in selected}),
        },
        "trainingUse": "prohibited",
    }


def validate_and_build(paths: dict[str, Path], selection_plan_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    documents = {key: read_object(path, key) for key, path in paths.items()}
    cycle = documents["cycle012Materialization"]
    clean = documents["cleanDevelopmentEvaluation"]
    validation = documents["historicalValidationTruth"]
    frozen = documents["consumedPositiveTest"]
    legacy = documents["legacyCandidateInventory"]
    current = documents["currentCandidateInventory"]

    train_records = [
        row for row in cycle.get("records") or []
        if row.get("developmentSplit") == "train" and row.get("role") == "train-positive"
    ]
    historical_development_records = [
        row for row in cycle.get("records") or []
        if row.get("developmentSplit") == "val" and row.get("role") == "train-positive"
    ]
    clean_records = [
        row for row in clean.get("records") or []
        if row.get("developmentSplit") == "val" and row.get("role") == "train-positive"
    ]
    role_records = {
        "developmentTrain": train_records,
        "historicalDevelopmentEvaluation": historical_development_records,
        "cleanDevelopment": clean_records,
        "historicalValidation": validation.get("canonicalTruths") or [],
        "consumedPositiveTest": frozen.get("items") or [],
    }
    expected_counts = {
        "developmentTrain": 290,
        "historicalDevelopmentEvaluation": 66,
        "cleanDevelopment": 58,
        "historicalValidation": 30,
        "consumedPositiveTest": 100,
    }
    if {key: len(value) for key, value in role_records.items()} != expected_counts:
        raise ValueError("当前角色记录计数漂移")
    if frozen.get("trainingUse") != "prohibited":
        raise ValueError("已消费test100训练角色漂移")

    used = {"fileName": set(), "imageSha256": set(), "sourceGroup": set()}
    role_counts: dict[str, Any] = {}
    for role, records in role_records.items():
        values = identity_sets(records, role)
        role_counts[role] = {"images": len(values["fileName"]), "sourceGroups": len(values["sourceGroup"])}
        for field in used:
            used[field].update(values[field])

    def classify(inventory: dict[str, Any], label: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        items = inventory.get("items")
        if (
            inventory.get("schemaVersion") != 1
            or inventory.get("ok") is not True
            or inventory.get("decision") != "candidate_inventory_ready_for_original_resolution_review"
            or not isinstance(items, list)
        ):
            raise ValueError(f"{label}合同无效")
        if canonical_sha256(items) != inventory.get("itemsSha256"):
            raise ValueError(f"{label}条目摘要漂移")
        eligible: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        for item in items:
            if item.get("trainingUse") != "prohibited":
                raise ValueError(f"{label}存在错误晋升项")
            reasons = overlap_reasons(item, used)
            if reasons:
                rejected.append({
                    "fileName": item["fileName"],
                    "sourceGroup": item["sourceGroup"],
                    "overlapReasons": reasons,
                })
            else:
                eligible.append(item)
        return eligible, rejected

    legacy_eligible, legacy_rejected = classify(legacy, "旧333候选库存")
    current_eligible, current_rejected = classify(current, "当前10候选库存")
    if len(legacy_eligible) != 7 or len({item["sourceGroup"] for item in legacy_eligible}) != 7:
        raise ValueError("旧库存当前可恢复容量漂移")
    if len(current_eligible) != 7 or len(current_rejected) != 3:
        raise ValueError("当前10候选库存隔离结论漂移")
    current_eligible_hashes = {str(item["imageSha256"]).lower() for item in current_eligible}
    legacy_eligible_hashes = {str(item["imageSha256"]).lower() for item in legacy_eligible}
    if not current_eligible_hashes <= legacy_eligible_hashes:
        raise ValueError("当前可用7项并非旧库存可恢复子集")

    plan = selected_plan(paths["legacyCandidateInventory"], legacy, legacy_eligible)
    total_required = (
        TARGET_CLEAN_DEVELOPMENT
        - len(clean_records)
        + FRESH_CALIBRATION_RESERVE
        + FRESH_POSITIVE_HOLDOUT_RESERVE
    )
    report = {
        "schemaVersion": 1,
        "ok": True,
        "decision": "recover_7_candidates_and_acquire_at_least_43_for_first_50_batch",
        "analysisKind": "metadata_only_current_role_isolation_audit",
        "readImagePixels": False,
        "runTraining": False,
        "runInference": False,
        "inputs": {key: binding(path) for key, path in paths.items()},
        "outputs": {
            "selectionPlan": (
                binding(selection_plan_path)
                if selection_plan_path.is_file()
                else {"path": str(selection_plan_path.resolve()), "sha256": "pending-until-plan-is-written"}
            )
        },
        "currentRoleLedger": role_counts,
        "legacyInventory": {
            "inputImages": len(legacy.get("items") or []),
            "inputSourceGroups": len({item["sourceGroup"] for item in legacy.get("items") or []}),
            "eligibleImages": len(legacy_eligible),
            "eligibleSourceGroups": len({item["sourceGroup"] for item in legacy_eligible}),
            "rejectedImages": len(legacy_rejected),
            "rejectedByAnySourceGroupOverlap": sum("sourceGroup" in row["overlapReasons"] for row in legacy_rejected),
        },
        "currentTenInventory": {
            "eligibleImages": len(current_eligible),
            "eligibleSourceGroups": len({item["sourceGroup"] for item in current_eligible}),
            "rejectedImages": len(current_rejected),
            "rejected": current_rejected,
            "eligibleAreExactlyRecovered7": current_eligible_hashes == legacy_eligible_hashes,
        },
        "recoveredCandidates": [
            {
                "fileName": item["fileName"],
                "imageSha256": item["imageSha256"],
                "sourceGroup": item["sourceGroup"],
                "fullyVisibleNails": item["fullyVisibleNails"],
                "trainingUse": "prohibited",
                "requiredNextGate": "original-resolution source and complete-mask review",
            }
            for item in legacy_eligible
        ],
        "supplyMath": {
            "firstBatchTargetImages": TARGET_FIRST_BATCH,
            "recoveredCandidateImages": len(legacy_eligible),
            "minimumNewCandidateImagesForFirstBatch": TARGET_FIRST_BATCH - len(legacy_eligible),
            "cleanDevelopmentCurrentImages": len(clean_records),
            "cleanDevelopmentTargetImages": TARGET_CLEAN_DEVELOPMENT,
            "freshCalibrationReserveImages": FRESH_CALIBRATION_RESERVE,
            "freshPositiveHoldoutReserveImages": FRESH_POSITIVE_HOLDOUT_RESERVE,
            "totalAdditionalApprovedPositiveImagesBeforeRecoveredCandidates": total_required,
            "minimumNewApprovedPositiveImagesIfAllRecoveredCandidatesPass": total_required - len(legacy_eligible),
        },
        "accelerationDecision": {
            "reviewRecoveredCandidatesImmediately": True,
            "acquireNewSourcesInParallel": True,
            "firstBatchNewCandidateMinimum": TARGET_FIRST_BATCH - len(legacy_eligible),
            "freezeRolesBeforeAnnotationOrModelAssistance": True,
            "countCandidateAsApprovedBeforeOriginalResolutionReview": False,
            "reuseConsumedOrProtectedEvidence": False,
            "earliestStatisticallyUsefulDevelopmentMilestone": {
                "targetPositiveImages": 148,
                "currentPositiveImages": len(clean_records),
                "additionalApprovedImages": 148 - len(clean_records),
                "purpose": "spurious-rate discrimination before the 352-image missing-rate milestone",
            },
        },
        "trainingUse": "prohibited",
        "formalPromotionAllowed": False,
        "releaseState": "hold",
        "productState": "hold",
        "errors": [],
    }
    return plan, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for key in (
        "legacy-candidate-inventory",
        "current-candidate-inventory",
        "cycle012-materialization",
        "clean-development-evaluation",
        "historical-validation-truth",
        "consumed-positive-test",
    ):
        parser.add_argument(f"--{key}")
    parser.add_argument("--selection-plan")
    parser.add_argument("--output")
    parser.add_argument("--verify-report")
    args = parser.parse_args()
    argument_keys = {
        "legacyCandidateInventory": "legacy_candidate_inventory",
        "currentCandidateInventory": "current_candidate_inventory",
        "cycle012Materialization": "cycle012_materialization",
        "cleanDevelopmentEvaluation": "clean_development_evaluation",
        "historicalValidationTruth": "historical_validation_truth",
        "consumedPositiveTest": "consumed_positive_test",
    }
    if args.verify_report:
        report_path = Path(args.verify_report).resolve()
        existing = read_object(report_path, "待重放供给审计")
        paths = {key: Path(existing["inputs"][key]["path"]) for key in argument_keys}
        plan_path = Path(existing["outputs"]["selectionPlan"]["path"]).resolve()
        existing_plan = read_object(plan_path, "冻结候选选择计划")
        replay_plan, replay_report = validate_and_build(paths, plan_path)
        if replay_plan != existing_plan or replay_report != existing:
            raise ValueError("供给审计或选择计划与当前元数据深重放不一致")
        print(json.dumps({"ok": True, "decision": existing["decision"], "reportSha256": sha256_file(report_path)}, ensure_ascii=False))
        return 0

    raw = {key: getattr(args, attribute) for key, attribute in argument_keys.items()}
    if any(value is None for value in (*raw.values(), args.selection_plan, args.output)):
        raise ValueError("构建模式缺少必填参数")
    output = Path(args.output).resolve()
    plan_path = Path(args.selection_plan).resolve()
    if output.exists() or plan_path.exists():
        raise ValueError("输出已存在，禁止覆盖")
    paths = {key: Path(value).resolve() for key, value in raw.items()}
    # 先生成计划，再将其字节哈希绑定进审计报告。
    placeholder_plan, _ = validate_and_build(paths, plan_path)
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps(placeholder_plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _, report = validate_and_build(paths, plan_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"], "supplyMath": report["supplyMath"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
