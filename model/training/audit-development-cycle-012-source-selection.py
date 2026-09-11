#!/usr/bin/env python3
"""审计循环012的13张定向真实正图，锁定来源隔离并保持训练禁用。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image


REQUIRED_COVERAGE = {
    "small-or-distant-complete-nails",
    "edge-adjacent-but-fully-visible-nails",
    "low-contrast-or-transparent-complete-nails",
    "side-view-or-elongated-complete-nails",
    "multi-hand-scenes-with-background-distractors",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"{label}不存在：{path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label}不是JSON对象")
    return value


def require_sha(value: Any, label: str) -> str:
    text = str(value or "").lower()
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ValueError(f"{label}不是SHA-256")
    return text


def binding(path: Path) -> dict[str, str]:
    return {"path": str(path), "sha256": sha256_file(path)}


def identities(items: Any, label: str) -> tuple[set[str], set[str], set[str]]:
    if not isinstance(items, list):
        raise ValueError(f"{label}缺少条目数组")
    names: set[str] = set()
    hashes: set[str] = set()
    groups: set[str] = set()
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"{label}第{index}项不是对象")
        name = str(item.get("fileName") or "").casefold()
        image_hash = item.get("imageSha256") or item.get("sha256")
        source_group = item.get("parentSourceGroup") or item.get("sourceGroup")
        if name:
            names.add(name)
        if image_hash:
            hashes.add(require_sha(image_hash, f"{label}第{index}项图片"))
        if source_group:
            groups.add(str(source_group))
    return names, hashes, groups


def protected_negative_identities(registry: dict[str, Any]) -> tuple[set[str], set[str], set[str]]:
    if registry.get("ok") is not True or registry.get("decision") != "protected_hard_negative_registry":
        raise ValueError("困难负样本保护登记表状态无效")
    result = (set(), set(), set())
    for index, entry in enumerate(registry.get("entries") or [], start=1):
        manifest_path = Path(str(entry.get("path") or "")).resolve()
        expected = require_sha(entry.get("sha256"), f"保护登记第{index}项")
        if not manifest_path.is_file() or sha256_file(manifest_path) != expected:
            raise ValueError(f"困难负样本manifest漂移：{manifest_path}")
        manifest = read_object(manifest_path, "困难负样本manifest")
        current = identities(manifest.get("items"), f"困难负样本manifest {manifest_path.name}")
        for target, values in zip(result, current, strict=True):
            target.update(values)
    return result


def build(args: argparse.Namespace) -> dict[str, Any]:
    paths = {
        "plan": Path(args.plan).resolve(),
        "spec": Path(args.spec).resolve(),
        "sourceReviewEvidence": Path(args.source_review_evidence).resolve(),
        "sourceInventory": Path(args.source_inventory).resolve(),
        "trainingMaterialization": Path(args.training_materialization).resolve(),
        "developmentEvaluation": Path(args.development_evaluation).resolve(),
        "validationTruthIndex": Path(args.validation_truth_index).resolve(),
        "frozenTestManifest": Path(args.frozen_test_manifest).resolve(),
        "protectedRegistry": Path(args.protected_registry).resolve(),
        "standingAuthorization": Path(args.standing_authorization).resolve(),
        "corpusAudit": Path(args.corpus_audit).resolve(),
    }
    documents = {key: read_object(path, key) for key, path in paths.items()}
    plan = documents["plan"]
    spec = documents["spec"]
    review = documents["sourceReviewEvidence"]
    inventory = documents["sourceInventory"]
    training = documents["trainingMaterialization"]
    evaluation = documents["developmentEvaluation"]
    validation = documents["validationTruthIndex"]
    frozen = documents["frozenTestManifest"]
    authorization = documents["standingAuthorization"]
    corpus = documents["corpusAudit"]

    if (
        plan.get("cycleId") != "nail-texture-development-cycle-012"
        or plan.get("decision") != "pre_registered_pending_targeted_positive_truth_materialization"
        or plan.get("releaseState") != "hold"
    ):
        raise ValueError("循环012计划状态无效")
    contract = plan.get("targetedPositiveSelectionContract") or {}
    if (
        contract.get("images") != 13
        or contract.get("masks") != 65
        or contract.get("sourceGroups") != 13
        or contract.get("exactlyFiveFullyVisibleNailsPerImage") is not True
        or set(contract.get("requiredMorphologyCoverage") or []) != REQUIRED_COVERAGE
    ):
        raise ValueError("循环012源图合同漂移")
    if (
        spec.get("decision") != "development_cycle_012_positive_source_candidates_pending_audit"
        or spec.get("cyclePlan") != binding(paths["plan"])
        or spec.get("sourceInventory") != binding(paths["sourceInventory"])
    ):
        raise ValueError("源图规格状态或输入绑定无效")
    if (
        review.get("decision") != "development_cycle_012_original_resolution_source_review_pass_candidate_only"
        or review.get("sourceSelectionSpec") != binding(paths["spec"])
        or review.get("policy", {}).get("trainingUse") != "prohibited"
        or review.get("policy", {}).get("completeMaskReviewStillRequired") is not True
    ):
        raise ValueError("原分辨率源图审核状态无效")
    if (
        inventory.get("decision") != "development_cycle_012_unused_real_positive_inventory"
        or inventory.get("trainingUse") != "prohibited"
        or training.get("ok") is not True
        or training.get("decision") != "approved_train_internal_development_dataset_materialization"
        or evaluation.get("ok") is not True
        or evaluation.get("decision") != "approved_read_only_clean_development_evaluation"
        or evaluation.get("trainingUse") != "prohibited"
        or validation.get("ok") is not True
        or validation.get("decision") != "approved_unique_validation_truth_index"
        or frozen.get("trainingUse") != "prohibited"
    ):
        raise ValueError("受保护角色或上游筛选状态无效")
    if (
        authorization.get("decision") != "standing_project_commercial_resource_authorization_granted"
        or authorization.get("scope", {}).get("itemizedTrainingAuthorizationRequired") is not False
    ):
        raise ValueError("standing商业授权无效")

    source_root = Path(str(spec.get("sourceRoot") or "")).resolve()
    if not source_root.is_dir():
        raise ValueError(f"源图目录不存在：{source_root}")
    raw_items = spec.get("items")
    review_items = review.get("items")
    if not isinstance(raw_items, list) or len(raw_items) != 13:
        raise ValueError("源图规格必须恰有13项")
    if not isinstance(review_items, list) or len(review_items) != 13:
        raise ValueError("源图审核必须恰有13项")
    inventory_by_name = {
        str(item.get("fileName")): item for item in inventory.get("items") or []
        if isinstance(item, dict)
    }
    review_by_name = {
        str(item.get("fileName")): item for item in review_items if isinstance(item, dict)
    }
    role_sets = {
        "currentDevelopmentDataset": identities(training.get("records"), "当前开发数据集"),
        "clean98Evaluation": identities(evaluation.get("records"), "98图干净评估"),
        "validation": identities(validation.get("canonicalTruths"), "验证真值"),
        "frozenTest": identities(frozen.get("items"), "冻结test"),
        "protectedHardNegative": protected_negative_identities(documents["protectedRegistry"]),
    }

    seen_names: set[str] = set()
    seen_hashes: set[str] = set()
    seen_groups: set[str] = set()
    covered: set[str] = set()
    records: list[dict[str, Any]] = []
    overlaps = {role: {"fileName": [], "imageSha256": [], "sourceGroup": []} for role in role_sets}
    for index, item in enumerate(raw_items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"源图规格第{index}项不是对象")
        name = str(item.get("fileName") or "")
        group = str(item.get("sourceGroup") or "")
        expected_hash = require_sha(item.get("sha256"), f"源图规格第{index}项")
        intents = item.get("coverageIntents")
        if not name or not group or item.get("expectedFullyVisibleNails") != 5:
            raise ValueError(f"源图规格第{index}项身份或完整甲数无效")
        if not isinstance(intents, list) or not intents or not set(intents) <= REQUIRED_COVERAGE:
            raise ValueError(f"源图规格第{index}项形态覆盖无效")
        image_path = (source_root / name).resolve()
        if image_path.parent != source_root or not image_path.is_file():
            raise ValueError(f"源图缺失或路径逃逸：{name}")
        actual_hash = sha256_file(image_path)
        if actual_hash != expected_hash:
            raise ValueError(f"源图哈希漂移：{name}")
        with Image.open(image_path) as image:
            image.load()
            width, height = image.size
            image_format = image.format
        if (item.get("width"), item.get("height")) != (width, height):
            raise ValueError(f"源图尺寸漂移：{name}")
        if name.casefold() in seen_names or actual_hash in seen_hashes or group in seen_groups:
            raise ValueError(f"批内文件、哈希或来源组重复：{name}")
        inventoried = inventory_by_name.get(name)
        if not inventoried or (
            inventoried.get("candidateStatus") != "unused_source_candidate"
            or inventoried.get("trainingUse") != "prohibited"
            or inventoried.get("sha256") != actual_hash
            or inventoried.get("sourceGroup") != group
        ):
            raise ValueError(f"源图未绑定到未使用真实素材清单：{name}")
        source_path = Path(str(inventoried.get("sourcePath") or "")).resolve()
        if not source_path.is_file():
            raise ValueError(f"源素材路径不存在：{name}")
        derivation = str(inventoried.get("derivation") or "original")
        if derivation == "original":
            source_hash = require_sha(
                inventoried.get("sourceSha256") or actual_hash,
                f"源图清单第{index}项源素材",
            )
            if sha256_file(source_path) != source_hash or source_hash != actual_hash:
                raise ValueError(f"原始源素材与候选图不一致：{name}")
        elif derivation == "parent-crop":
            parent_hash = require_sha(inventoried.get("parentSha256"), f"源图清单第{index}项父图")
            crop_box = inventoried.get("cropBox")
            if (
                sha256_file(source_path) != parent_hash
                or not isinstance(crop_box, list)
                or len(crop_box) != 4
                or any(not isinstance(value, int) for value in crop_box)
            ):
                raise ValueError(f"派生区域父图绑定无效：{name}")
            with Image.open(source_path) as parent, Image.open(image_path) as candidate:
                expected_crop = parent.convert("RGB").crop(tuple(crop_box))
                actual_crop = candidate.convert("RGB")
                if expected_crop.size != actual_crop.size or expected_crop.tobytes() != actual_crop.tobytes():
                    raise ValueError(f"派生区域不能从绑定父图精确重放：{name}")
        else:
            raise ValueError(f"未知源图派生方式：{name}")
        reviewed = review_by_name.get(name)
        if not reviewed or (
            reviewed.get("sha256") != actual_hash
            or reviewed.get("sourceGroup") != group
            or reviewed.get("reviewScale") != "original-resolution"
            or reviewed.get("reviewDecision") != "pass_source_only_pending_complete_mask_review"
            or reviewed.get("fullyVisibleNails") != 5
            or reviewed.get("allVisibleNailsComplete") is not True
            or reviewed.get("croppedOrPartialNails") != 0
            or reviewed.get("blurredOrUnreviewableNails") != 0
            or reviewed.get("watermarkOutsideNailSurfaces") is not True
            or reviewed.get("coverageIntents") != intents
        ):
            raise ValueError(f"原分辨率源图审核记录无效：{name}")
        for role, (names, hashes, groups) in role_sets.items():
            if name.casefold() in names:
                overlaps[role]["fileName"].append(name)
            if actual_hash in hashes:
                overlaps[role]["imageSha256"].append(name)
            if group in groups:
                overlaps[role]["sourceGroup"].append(group)
        seen_names.add(name.casefold())
        seen_hashes.add(actual_hash)
        seen_groups.add(group)
        covered.update(intents)
        records.append({
            "fileName": name,
            "sha256": actual_hash,
            "bytes": image_path.stat().st_size,
            "width": width,
            "height": height,
            "format": image_format,
            "sourceGroup": group,
            "expectedFullyVisibleNails": 5,
            "coverageIntents": intents,
            "sourceReviewStatus": "pass_pending_complete_mask_review",
            "annotationTruthStatus": "not-started",
            "trainingUse": "prohibited",
        })
    if covered != REQUIRED_COVERAGE:
        raise ValueError("13张源图未覆盖全部预注册困难形态")
    if any(values for role in overlaps.values() for values in role.values()):
        raise ValueError(f"源图与受保护角色身份交叠：{overlaps}")

    expected_train_root = str((Path(str(training.get("outputDir"))) / "images" / "train").resolve())
    expected_eval_root = str((Path(str(evaluation.get("outputDir"))) / "images" / "val").resolve())
    comparison = corpus.get("comparisons") or {}
    if (
        corpus.get("ok") is not True
        or Path(str(corpus.get("root"))).resolve() != source_root
        or corpus.get("totals") != {
            "files": 13,
            "validImages": 13,
            "invalidImages": 0,
            "exactDuplicateGroups": 0,
            "exactDuplicateFiles": 0,
            "nearDuplicatePairs": 0,
        }
        or set(comparison.get("roots") or []) != {expected_train_root, expected_eval_root}
        or comparison.get("invalidReferences") != []
        or comparison.get("exactMatches") != []
        or comparison.get("nearMatches") != []
    ):
        raise ValueError("语料精确/感知近重复审计无效")

    return {
        "schemaVersion": 1,
        "ok": True,
        "decision": "development_cycle_012_source_selection_pass_candidate_only",
        "inputs": {key: binding(path) for key, path in paths.items()},
        "sourceRoot": str(source_root),
        "counts": {"images": 13, "sourceGroups": 13, "expectedFullyVisibleNails": 65},
        "coverage": {"required": sorted(REQUIRED_COVERAGE), "covered": sorted(covered)},
        "overlaps": overlaps,
        "corpusAudit": {
            "candidateExactDuplicateGroups": 0,
            "candidateNearDuplicatePairs": 0,
            "protectedReferenceImages": comparison.get("referenceImages"),
            "exactMatches": 0,
            "nearMatches": 0,
        },
        "itemsSha256": canonical_sha256(records),
        "items": records,
        "trainingUse": "prohibited",
        "nextGate": "65 complete masks require original-resolution per-nail review, polygon validity, and zero pairwise overlap",
        "errors": [],
    }


def write_atomic(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise ValueError(f"输出不得覆盖既有证据：{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.tmp-", dir=path.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan")
    parser.add_argument("--spec")
    parser.add_argument("--source-review-evidence")
    parser.add_argument("--source-inventory")
    parser.add_argument("--training-materialization")
    parser.add_argument("--development-evaluation")
    parser.add_argument("--validation-truth-index")
    parser.add_argument("--frozen-test-manifest")
    parser.add_argument("--protected-registry")
    parser.add_argument("--standing-authorization")
    parser.add_argument("--corpus-audit")
    parser.add_argument("--output")
    parser.add_argument("--verify-report")
    args = parser.parse_args()
    if args.verify_report:
        report_path = Path(args.verify_report).resolve()
        existing = read_object(report_path, "待重放报告")
        input_bindings = existing.get("inputs") or {}
        replay = argparse.Namespace(**{
            "plan": input_bindings["plan"]["path"],
            "spec": input_bindings["spec"]["path"],
            "source_review_evidence": input_bindings["sourceReviewEvidence"]["path"],
            "source_inventory": input_bindings["sourceInventory"]["path"],
            "training_materialization": input_bindings["trainingMaterialization"]["path"],
            "development_evaluation": input_bindings["developmentEvaluation"]["path"],
            "validation_truth_index": input_bindings["validationTruthIndex"]["path"],
            "frozen_test_manifest": input_bindings["frozenTestManifest"]["path"],
            "protected_registry": input_bindings["protectedRegistry"]["path"],
            "standing_authorization": input_bindings["standingAuthorization"]["path"],
            "corpus_audit": input_bindings["corpusAudit"]["path"],
        })
        if build(replay) != existing:
            raise ValueError("报告与当前磁盘重放结果不一致")
        print(json.dumps({"ok": True, "decision": "verified", "report": str(report_path)}, ensure_ascii=False))
        return 0
    required = [
        args.plan, args.spec, args.source_review_evidence, args.source_inventory,
        args.training_materialization, args.development_evaluation,
        args.validation_truth_index, args.frozen_test_manifest, args.protected_registry,
        args.standing_authorization, args.corpus_audit, args.output,
    ]
    if any(value is None for value in required):
        raise ValueError("构建模式缺少必填参数")
    report = build(args)
    output = Path(args.output).resolve()
    write_atomic(output, report)
    print(json.dumps({"ok": True, "counts": report["counts"], "output": str(output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
