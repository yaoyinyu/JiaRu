#!/usr/bin/env python3
"""只读盘点循环014正图容量、受保护角色与可判别样本缺口。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


EXPECTED_CLOSURE = "unreachable_close_development_cycle_013_mask_replacement_branch"
DEVELOPMENT_TARGETS = {
    "absoluteMissingRateResolution": 352,
    "relativeMissingRateResolutionPerGroup": 932,
    "spuriousRateResolution": 148,
}


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


def binding(path: Path) -> dict[str, str]:
    path = path.resolve()
    return {"path": str(path), "sha256": sha256_file(path)}


def identities(records: Any, label: str) -> tuple[set[str], set[str], set[str]]:
    if not isinstance(records, list):
        raise ValueError(f"{label}缺少记录数组")
    names: set[str] = set()
    hashes: set[str] = set()
    groups: set[str] = set()
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            raise ValueError(f"{label}第{index}项不是对象")
        name = str(record.get("fileName") or "").casefold()
        image_hash = str(record.get("imageSha256") or record.get("sha256") or "").lower()
        group = str(record.get("sourceGroup") or record.get("parentSourceGroup") or "")
        if not name or len(image_hash) != 64 or not group:
            raise ValueError(f"{label}第{index}项身份不完整")
        if name in names or image_hash in hashes:
            raise ValueError(f"{label}存在重复文件名或图片哈希")
        names.add(name)
        hashes.add(image_hash)
        groups.add(group)
    return names, hashes, groups


def overlap(left: tuple[set[str], set[str], set[str]], right: tuple[set[str], set[str], set[str]]) -> dict[str, int]:
    return {
        "fileNames": len(left[0] & right[0]),
        "imageSha256": len(left[1] & right[1]),
        "sourceGroups": len(left[2] & right[2]),
    }


def validate_contracts(documents: dict[str, dict[str, Any]]) -> dict[str, Any]:
    closure = documents["cycle013Closure"]
    canonical = documents["canonicalTrainingTruth"]
    cycle012 = documents["cycle012Materialization"]
    clean = documents["cleanDevelopmentEvaluation"]
    validation = documents["historicalValidationTruth"]
    frozen = documents["consumedPositiveTest"]
    candidates = documents["candidateOnlyInventory"]

    if (
        closure.get("decision") != EXPECTED_CLOSURE
        or closure.get("branchClosure", {}).get("closed") is not True
        or any(closure.get("budgetConsumption", {}).values())
    ):
        raise ValueError("循环013关闭证据无效或预算并非零")
    if canonical.get("summary") != {
        "approvedReportCount": 343,
        "rejectedReportCount": 0,
        "uniqueImageCount": 343,
        "completeMaskCount": 2071,
        "redundantReportCount": 0,
        "redundantImageCount": 0,
        "conflictingImageCount": 0,
        "sourceGroupCount": 127,
    }:
        raise ValueError("candidate58b规范训练真值摘要漂移")
    expected_cycle012 = {
        "trainImages": 350,
        "trainPositiveImages": 290,
        "trainPositiveMasks": 1731,
        "trainHardNegativeImages": 60,
        "evaluationImages": 106,
        "evaluationPositiveImages": 66,
        "evaluationPositiveMasks": 405,
        "evaluationHardNegativeImages": 40,
        "testImages": 0,
        "sourceGroupOverlap": 0,
    }
    if cycle012.get("counts") != expected_cycle012:
        raise ValueError("循环012开发物化计数漂移")
    if clean.get("counts") != {
        "trainImages": 0,
        "trainPositiveImages": 0,
        "trainPositiveMasks": 0,
        "trainHardNegativeImages": 0,
        "evaluationImages": 98,
        "evaluationPositiveImages": 58,
        "evaluationPositiveMasks": 354,
        "evaluationHardNegativeImages": 40,
        "testImages": 0,
        "sourceGroupOverlap": 0,
        "imageSha256Overlap": 0,
    }:
        raise ValueError("clean98开发评估计数漂移")
    if validation.get("summary", {}).get("uniqueImageCount") != 30 or validation.get("summary", {}).get("completeMaskCount") != 144:
        raise ValueError("历史val30计数漂移")
    if len(frozen.get("items") or []) != 100 or frozen.get("trainingUse") != "prohibited":
        raise ValueError("已消费正样本test100角色漂移")
    if candidates.get("counts", {}).get("candidateImages") != 10 or candidates.get("counts", {}).get("candidateSourceGroups") != 8:
        raise ValueError("候选清单容量漂移")
    candidate_items = candidates.get("items") or []
    if any(
        item.get("trainingUse") != "prohibited" or item.get("completeMaskReview") != "not-started"
        for item in candidate_items
    ):
        raise ValueError("候选清单被错误晋升或审核状态漂移")

    train_records = [
        row for row in cycle012.get("records") or []
        if row.get("developmentSplit") == "train" and row.get("role") == "train-positive"
    ]
    clean_records = [row for row in clean.get("records") or [] if row.get("role") == "train-positive"]
    if len(train_records) != 290 or len(clean_records) != 58:
        raise ValueError("正图角色过滤计数漂移")
    role_sets = {
        "developmentTrain": identities(train_records, "循环012训练正图"),
        "cleanDevelopment": identities(clean_records, "clean98开发正图"),
        "historicalValidation": identities(validation.get("canonicalTruths"), "历史val30"),
        "consumedPositiveTest": identities(frozen.get("items"), "已消费正样本test100"),
        "candidateOnly": identities(candidate_items, "候选清单"),
    }
    protected_overlap = {
        role: overlap(role_sets["developmentTrain"], role_sets[role])
        for role in ("cleanDevelopment", "historicalValidation", "consumedPositiveTest")
    }
    if any(value for result in protected_overlap.values() for value in result.values()):
        raise ValueError(f"开发训练正图与受保护/评估角色交叠：{protected_overlap}")
    candidate_overlap = {
        role: overlap(role_sets["candidateOnly"], role_sets[role])
        for role in ("developmentTrain", "cleanDevelopment", "historicalValidation", "consumedPositiveTest")
    }
    return {
        "protectedRoleOverlap": protected_overlap,
        "candidateOverlap": candidate_overlap,
        "roleCounts": {
            "developmentTrainPositiveImages": len(role_sets["developmentTrain"][0]),
            "developmentTrainPositiveSourceGroups": len(role_sets["developmentTrain"][2]),
            "cleanDevelopmentPositiveImages": len(role_sets["cleanDevelopment"][0]),
            "cleanDevelopmentPositiveSourceGroups": len(role_sets["cleanDevelopment"][2]),
            "historicalValidationImages": len(role_sets["historicalValidation"][0]),
            "consumedPositiveTestImages": len(role_sets["consumedPositiveTest"][0]),
            "candidateOnlyImages": len(role_sets["candidateOnly"][0]),
            "candidateOnlySourceGroups": len(role_sets["candidateOnly"][2]),
        },
    }


def build(paths: dict[str, Path]) -> dict[str, Any]:
    documents = {key: read_object(path, key) for key, path in paths.items()}
    facts = validate_contracts(documents)
    current = facts["roleCounts"]["cleanDevelopmentPositiveImages"]
    candidate_upper_bound = facts["roleCounts"]["candidateOnlyImages"]
    shortages = {
        key: {
            "targetPositiveImages": target,
            "currentCleanDevelopmentImages": current,
            "additionalImagesToExtendCurrentCohort": max(0, target - current),
            "remainingAfterCandidateOnlyUpperBound": max(0, target - current - candidate_upper_bound),
        }
        for key, target in DEVELOPMENT_TARGETS.items()
    }
    release_reserve = 30 + 100
    return {
        "schemaVersion": 1,
        "ok": True,
        "decision": "cycle014_positive_capacity_insufficient_start_parallel_acquisition_and_review",
        "analysisKind": "metadata_only_positive_capacity_audit",
        "readImagePixels": False,
        "runTraining": False,
        "runInference": False,
        "inputs": {key: binding(path) for key, path in paths.items()},
        "roleLedger": {
            "canonicalHistoricalPositiveTruth": {
                "images": 343,
                "masks": 2071,
                "sourceGroups": 127,
                "status": "machine-approved historical corpus; current quality revalidation required before a new training claim",
            },
            "developmentTrain": {
                "images": facts["roleCounts"]["developmentTrainPositiveImages"],
                "masks": 1731,
                "sourceGroups": facts["roleCounts"]["developmentTrainPositiveSourceGroups"],
                "status": "development training role; not a formal validation, test, or holdout",
            },
            "cleanDevelopment": {
                "images": current,
                "masks": 354,
                "sourceGroups": facts["roleCounts"]["cleanDevelopmentPositiveSourceGroups"],
                "status": "development-only and already used for cycle011/cycle012 diagnosis; prohibited for formal calibration/test/holdout",
            },
            "historicalValidation": {
                "images": 30,
                "masks": 144,
                "status": "historical/consumed val30; prohibited for a new release threshold selection",
            },
            "consumedPositiveTest": {
                "images": 100,
                "status": "candidate57-consumed protected test; permanently prohibited for training or new release claims",
            },
            "candidateOnlyUpperBound": {
                "images": candidate_upper_bound,
                "sourceGroups": facts["roleCounts"]["candidateOnlySourceGroups"],
                "status": "source-screened candidate only; complete mask review not started and trainingUse remains prohibited",
            },
        },
        "identityChecks": {
            "developmentTrainVsProtected": facts["protectedRoleOverlap"],
            "candidateOnlyVsKnownRoles": facts["candidateOverlap"],
        },
        "developmentResolutionShortages": shortages,
        "freshReleasePositiveReserve": {
            "calibration": 30,
            "positiveHoldout": 100,
            "minimumUniquePositiveImages": release_reserve,
            "mayOverlapDevelopmentOrTraining": False,
        },
        "minimumNewPositiveSupply": {
            "extendCleanDevelopmentTo352PlusReleaseReserve": (352 - current) + release_reserve,
            "remainingAfterCandidateOnlyUpperBound": (352 - current) + release_reserve - candidate_upper_bound,
            "note": "Beta100 and additional training positives are outside this minimum and add further demand.",
        },
        "routeDecision": {
            "dataSupplyIsFirstClassRisk": True,
            "startAcquisitionAndOriginalResolutionReviewInParallel": True,
            "candidateOnlyInventoryMayBeCountedAsTrainingReady": False,
            "reuseConsumedValOrTest": False,
            "nextModelVariable": "fullImageCandidateSupply",
            "trainingBudgetGate": "require cycle014 zero-inference reachability and a source-isolated reviewed training manifest before one short run",
        },
        "releaseState": "hold",
        "productState": "hold",
        "errors": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for key in (
        "cycle013-closure",
        "canonical-training-truth",
        "cycle012-materialization",
        "clean-development-evaluation",
        "historical-validation-truth",
        "consumed-positive-test",
        "candidate-only-inventory",
    ):
        parser.add_argument(f"--{key}")
    parser.add_argument("--output")
    parser.add_argument("--verify-report")
    args = parser.parse_args()
    argument_keys = {
        "cycle013Closure": "cycle013_closure",
        "canonicalTrainingTruth": "canonical_training_truth",
        "cycle012Materialization": "cycle012_materialization",
        "cleanDevelopmentEvaluation": "clean_development_evaluation",
        "historicalValidationTruth": "historical_validation_truth",
        "consumedPositiveTest": "consumed_positive_test",
        "candidateOnlyInventory": "candidate_only_inventory",
    }
    if args.verify_report:
        report_path = Path(args.verify_report).resolve()
        existing = read_object(report_path, "待重放容量审计")
        paths = {key: Path(existing["inputs"][key]["path"]) for key in argument_keys}
        replay = build(paths)
        if replay != existing:
            raise ValueError("容量审计与当前元数据深重放不一致")
        print(json.dumps({"ok": True, "decision": existing["decision"], "reportSha256": sha256_file(report_path)}, ensure_ascii=False))
        return 0
    raw = {key: getattr(args, attribute) for key, attribute in argument_keys.items()}
    if any(value is None for value in (*raw.values(), args.output)):
        raise ValueError("构建模式缺少必填参数")
    output = Path(args.output).resolve()
    if output.exists():
        raise ValueError(f"输出已存在，禁止覆盖：{output}")
    payload = build({key: Path(value) for key, value in raw.items()})
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": payload["decision"], "minimumNewPositiveSupply": payload["minimumNewPositiveSupply"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
