#!/usr/bin/env python3
"""冻结循环015内置生成正图并复验当前角色隔离与原分辨率源图门。"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path
from typing import Any


TARGET_SOURCE_QUALIFIED = 133


def decision_for_count(count: int) -> str:
    if count == 3:
        return "freeze_3_new_source_qualified_candidates_continue_to_133"
    return f"freeze_{count}_cumulative_source_qualified_candidates_continue_to_133"


def next_action_for_count(count: int) -> str:
    if count == 3:
        return "generate_review_and_freeze_next_10_source_qualified_candidates_to_reach_13_of_133"
    next_checkpoint = 13 if count < 13 else min(TARGET_SOURCE_QUALIFIED, count + 10)
    return (
        f"generate_review_and_freeze_next_{next_checkpoint - count}_"
        f"source_qualified_candidates_to_reach_{next_checkpoint}_of_133"
    )


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


def png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as source:
        header = source.read(24)
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ValueError(f"不是有效PNG头：{path}")
    width, height = struct.unpack(">II", header[16:24])
    if width < 512 or height < 512:
        raise ValueError(f"候选分辨率低于512：{path}")
    return width, height


def identity(record: dict[str, Any], label: str) -> tuple[str, str, str]:
    name = str(record.get("fileName") or "").casefold()
    image_hash = str(record.get("imageSha256") or record.get("sha256") or "").lower()
    group = str(record.get("sourceGroup") or record.get("parentSourceGroup") or "")
    if not name or len(image_hash) != 64 or not group:
        raise ValueError(f"{label}身份不完整")
    return name, image_hash, group


def validate_prior_corrections(
    prior_items: list[dict[str, Any]], items: list[dict[str, Any]], corrections: Any, exclusions: Any = None
) -> None:
    corrections = [] if corrections is None else corrections
    exclusions = [] if exclusions is None else exclusions
    if not isinstance(corrections, list) or not isinstance(exclusions, list):
        raise ValueError("前序冻结纠正或排除账本不是数组")
    correction_by_file: dict[str, dict[str, Any]] = {}
    for correction in corrections:
        if not isinstance(correction, dict):
            raise ValueError("前序冻结纠正项不是JSON对象")
        name = str(correction.get("fileName") or "")
        if not name or name in correction_by_file:
            raise ValueError("前序冻结纠正项文件名为空或重复")
        if correction.get("field") != "fullyVisibleNails":
            raise ValueError("当前只允许显式纠正完整可见甲面计数")
        if not isinstance(correction.get("reason"), str) or not correction["reason"].strip():
            raise ValueError("前序冻结纠正项缺少原因")
        correction_by_file[name] = correction
    exclusion_by_file: dict[str, dict[str, Any]] = {}
    for exclusion in exclusions:
        if not isinstance(exclusion, dict):
            raise ValueError("前序冻结排除项不是JSON对象")
        name = str(exclusion.get("fileName") or "")
        if not name or name in exclusion_by_file:
            raise ValueError("前序冻结排除项文件名为空或重复")
        if exclusion.get("oldSourceGateDecision") != "pass" or exclusion.get("newSourceGateDecision") != "exclude":
            raise ValueError("前序冻结排除项状态转换无效")
        if not isinstance(exclusion.get("reason"), str) or not exclusion["reason"].strip():
            raise ValueError("前序冻结排除项缺少原因")
        exclusion_by_file[name] = exclusion
    if len(items) < len(prior_items):
        raise ValueError("纠正后的累计声明少于前序冻结条目")
    used: set[str] = set()
    for prior, current in zip(prior_items, items, strict=False):
        name = str(prior.get("fileName") or "")
        expected = dict(prior)
        correction = correction_by_file.get(name)
        if correction is not None:
            if correction.get("oldValue") != prior.get("fullyVisibleNails"):
                raise ValueError(f"纠正旧值与前序冻结不一致：{name}")
            expected["fullyVisibleNails"] = correction.get("newValue")
            used.add(name)
        exclusion = exclusion_by_file.get(name)
        if exclusion is not None:
            expected["sourceGateDecision"] = "exclude"
            checks = dict(expected.get("originalResolutionChecks") or {})
            checks["anatomyPlausible"] = False
            expected["originalResolutionChecks"] = checks
            expected["exclusionReason"] = exclusion["reason"]
            used.add(name)
        if current != expected:
            raise ValueError(f"未登记或越权改写前序冻结条目：{name}")
    if used != set(correction_by_file) | set(exclusion_by_file):
        raise ValueError("纠正或排除账本含不属于前序冻结的图片")


def role_identity_sets(source_supply: dict[str, Any]) -> tuple[dict[str, set[str]], dict[str, dict[str, int]]]:
    inputs = source_supply.get("inputs") or {}
    required = ["cycle012Materialization", "cleanDevelopmentEvaluation", "historicalValidationTruth", "consumedPositiveTest"]
    documents: dict[str, dict[str, Any]] = {}
    for key in required:
        binding = inputs.get(key) or {}
        path = Path(str(binding.get("path") or "")).resolve()
        if sha256_file(path) != binding.get("sha256"):
            raise ValueError(f"{key}字节哈希漂移")
        documents[key] = read_object(path, key)

    cycle = documents["cycle012Materialization"]
    clean = documents["cleanDevelopmentEvaluation"]
    validation = documents["historicalValidationTruth"]
    frozen = documents["consumedPositiveTest"]
    if frozen.get("trainingUse") != "prohibited":
        raise ValueError("已消费test训练角色漂移")
    role_records = {
        "developmentTrain": [row for row in cycle.get("records") or [] if row.get("developmentSplit") == "train" and row.get("role") == "train-positive"],
        "historicalDevelopmentEvaluation": [row for row in cycle.get("records") or [] if row.get("developmentSplit") == "val" and row.get("role") == "train-positive"],
        "cleanDevelopment": [row for row in clean.get("records") or [] if row.get("developmentSplit") == "val" and row.get("role") == "train-positive"],
        "historicalValidation": validation.get("canonicalTruths") or [],
        "consumedPositiveTest": frozen.get("items") or [],
    }
    expected = {"developmentTrain": 290, "historicalDevelopmentEvaluation": 66, "cleanDevelopment": 58, "historicalValidation": 30, "consumedPositiveTest": 100}
    if {key: len(value) for key, value in role_records.items()} != expected:
        raise ValueError("当前角色记录计数漂移")
    used = {"fileName": set(), "imageSha256": set(), "sourceGroup": set()}
    counts: dict[str, dict[str, int]] = {}
    for role, records in role_records.items():
        local = {"fileName": set(), "imageSha256": set(), "sourceGroup": set()}
        for index, record in enumerate(records, start=1):
            name, image_hash, group = identity(record, f"{role}第{index}项")
            local["fileName"].add(name)
            local["imageSha256"].add(image_hash)
            local["sourceGroup"].add(group)
        counts[role] = {"images": len(local["fileName"]), "sourceGroups": len(local["sourceGroup"])}
        for field in used:
            used[field].update(local[field])
    return used, counts


def audit(declaration_path: Path, source_supply_path: Path, route_path: Path) -> dict[str, Any]:
    declaration_path = declaration_path.resolve()
    source_supply_path = source_supply_path.resolve()
    route_path = route_path.resolve()
    declaration = read_object(declaration_path, "生成批次声明")
    source_supply = read_object(source_supply_path, "当前角色供给审计")
    route = read_object(route_path, "提速路线审计")
    if declaration.get("decision") != "generated_sources_reviewed_at_original_resolution":
        raise ValueError("生成批次声明未完成原分辨率源图门")
    if declaration.get("reviewScale") != "original-resolution" or declaration.get("trainingUse") != "prohibited":
        raise ValueError("生成批次声明审核尺度或训练角色无效")
    generator = declaration.get("generator") or {}
    if generator.get("name") != "OpenAI built-in image generation" or generator.get("exactModelIdKnown") is not False:
        raise ValueError("生成器事实边界无效")
    if declaration.get("authorization") != "standing-project-commercial-development-authorization":
        raise ValueError("生成批次未绑定standing商业开发授权")
    prior_freeze = declaration.get("priorFreeze")
    if prior_freeze is not None:
        if not isinstance(prior_freeze, dict):
            raise ValueError("前序冻结绑定不是JSON对象")
        prior_path = Path(str(prior_freeze.get("path") or "")).resolve()
        if sha256_file(prior_path) != prior_freeze.get("sha256"):
            raise ValueError("前序冻结声明字节哈希漂移")
        prior_declaration = read_object(prior_path, "前序冻结声明")
        prior_items = prior_declaration.get("items")
        if not isinstance(prior_items, list) or len(prior_items) != prior_freeze.get("itemCount"):
            raise ValueError("前序冻结声明条目计数漂移")
    else:
        prior_items = []
    if source_supply.get("decision") != "recover_7_candidates_and_acquire_at_least_43_for_first_50_batch":
        raise ValueError("当前角色供给审计合同漂移")
    if route.get("decision") != "replace_50_candidate_intake_with_133_source_qualified_development_cohort":
        raise ValueError("提速路线审计合同漂移")
    if (route.get("routeSizing") or {}).get("sourceQualifiedCandidatesConservativeFloor") != TARGET_SOURCE_QUALIFIED:
        raise ValueError("133张候选下限漂移")
    used, role_counts = role_identity_sets(source_supply)

    items = declaration.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= TARGET_SOURCE_QUALIFIED:
        raise ValueError("累计生成冻结清单必须包含1至133张")
    if prior_items:
        validate_prior_corrections(
            prior_items, items, declaration.get("corrections"), declaration.get("exclusions")
        )
    frozen: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    batch_sets = {"fileName": set(), "imageSha256": set(), "sourceGroup": set()}
    for index, item in enumerate(items, start=1):
        source_gate = item.get("sourceGateDecision")
        if source_gate not in {"pass", "exclude"} or item.get("trainingUse") != "prohibited":
            raise ValueError(f"第{index}项源图门或训练角色无效")
        checks = item.get("originalResolutionChecks") or {}
        required_checks = ["allRequiredNailsFullyVisible", "noNailTouchesImageEdge", "sharpEnoughForCompleteBoundary", "noOcclusion", "noTextLogoOrWatermark", "anatomyPlausible"]
        required_values = {key: True for key in required_checks}
        if source_gate == "exclude":
            required_values["anatomyPlausible"] = False
        if any(checks.get(key) is not value for key, value in required_values.items()):
            raise ValueError(f"第{index}项原分辨率检查不完整")
        path = Path(str(item.get("path") or "")).resolve()
        if not path.is_file() or path.suffix.lower() != ".png":
            raise ValueError(f"第{index}项图片不存在或不是PNG")
        image_hash = sha256_file(path)
        width, height = png_dimensions(path)
        if image_hash != item.get("imageSha256") or [width, height] != item.get("dimensions"):
            raise ValueError(f"第{index}项图片身份漂移")
        generator_output = Path(str(item.get("generatorOutputPath") or "")).resolve()
        if not generator_output.is_file() or sha256_file(generator_output) != image_hash:
            raise ValueError(f"第{index}项生成器原始输出缺失或与项目副本不一致")
        name, declared_hash, group = identity(item, f"第{index}项")
        values = {"fileName": name, "imageSha256": declared_hash, "sourceGroup": group}
        for field, value in values.items():
            if value in batch_sets[field]:
                raise ValueError(f"生成批次存在重复{field}")
            if value in used[field]:
                raise ValueError(f"生成批次与受保护或已使用角色发生{field}交叠")
            batch_sets[field].add(value)
        nail_count = int(item.get("fullyVisibleNails") or 0)
        if not 1 <= nail_count <= 10:
            raise ValueError(f"第{index}项完整甲面数无效")
        if source_gate == "exclude":
            if not str(item.get("exclusionReason") or "").strip():
                raise ValueError(f"第{index}项排除但缺少原因")
            excluded.append({
                "fileName": item["fileName"],
                "path": str(path),
                "imageSha256": image_hash,
                "sourceGroup": group,
                "sourceGateDecision": "exclude",
                "exclusionReason": item["exclusionReason"],
                "trainingUse": "prohibited",
            })
            continue
        frozen.append({
            "fileName": item["fileName"],
            "path": str(path),
            "imageSha256": image_hash,
            "dimensions": [width, height],
            "sourceGroup": group,
            "fullyVisibleNails": nail_count,
            "visualProfile": item["visualProfile"],
            "sourceGateDecision": "pass",
            "trainingUse": "prohibited",
            "requiredNextGate": "complete-mask annotation and original-resolution per-nail review",
        })
    if canonical_sha256(items) != declaration.get("itemsSha256"):
        raise ValueError("生成批次条目摘要漂移")

    return {
        "schemaVersion": 1,
        "ok": True,
        "decision": decision_for_count(len(frozen)),
        "analysisKind": "generated_source_identity_role_and_original_resolution_gate_audit",
        "readImagePixels": True,
        "runTraining": False,
        "runInference": False,
        "inputs": {
            "declaration": {"path": str(declaration_path), "sha256": sha256_file(declaration_path)},
            "sourceSupply": {"path": str(source_supply_path), "sha256": sha256_file(source_supply_path)},
            "accelerationRoute": {"path": str(route_path), "sha256": sha256_file(route_path)},
        },
        "currentRoleLedger": role_counts,
        "counts": {
            "generatedImages": len(items),
            "sourceQualifiedImages": len(frozen),
            "sourceGroups": len({item["sourceGroup"] for item in frozen}),
            "fullyVisibleNails": sum(item["fullyVisibleNails"] for item in frozen),
            "identityOrRoleOverlaps": 0,
            "targetSourceQualifiedImages": TARGET_SOURCE_QUALIFIED,
            "remainingSourceQualifiedImages": TARGET_SOURCE_QUALIFIED - len(frozen),
        },
        "items": frozen,
        "excludedItems": excluded,
        "policy": {
            "frozenBeforeAnnotationOrModelAssistance": True,
            "exactModelIdClaimed": False,
            "sourceGateDoesNotApproveMasks": True,
            "sourceGateDoesNotPermitTraining": True,
            "protectedOrConsumedDataReused": False,
            "supersededSourceGatePassesPreservedAsExcludedEvidence": True,
        },
        "trainingUse": "prohibited",
        "formalPromotionAllowed": False,
        "nextAction": next_action_for_count(len(frozen)),
        "releaseState": "hold",
        "productState": "hold",
        "errors": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--declaration")
    parser.add_argument("--source-supply")
    parser.add_argument("--acceleration-route")
    parser.add_argument("--output")
    parser.add_argument("--verify-report")
    args = parser.parse_args()
    if args.verify_report:
        report_path = Path(args.verify_report).resolve()
        existing = read_object(report_path, "待重放生成批次报告")
        inputs = existing.get("inputs") or {}
        replay = audit(Path(inputs["declaration"]["path"]), Path(inputs["sourceSupply"]["path"]), Path(inputs["accelerationRoute"]["path"]))
        if replay != existing:
            raise ValueError("生成批次报告与绑定输入重放不一致")
        print(json.dumps({"ok": True, "decision": existing["decision"], "reportSha256": sha256_file(report_path)}, ensure_ascii=False))
        return 0
    if not args.declaration or not args.source_supply or not args.acceleration_route or not args.output:
        raise ValueError("构建模式缺少必填参数")
    output = Path(args.output).resolve()
    if output.exists():
        raise ValueError(f"输出已存在，禁止覆盖：{output}")
    report = audit(Path(args.declaration), Path(args.source_supply), Path(args.acceleration_route))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"], "counts": report["counts"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
