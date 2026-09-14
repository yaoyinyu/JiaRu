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
    next_checkpoint = min(TARGET_SOURCE_QUALIFIED, count + (6 if count == 7 else 10))
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
    if prior_items and items[: len(prior_items)] != prior_items:
        raise ValueError("累计声明改写了前序冻结条目")
    frozen: list[dict[str, Any]] = []
    batch_sets = {"fileName": set(), "imageSha256": set(), "sourceGroup": set()}
    for index, item in enumerate(items, start=1):
        if item.get("sourceGateDecision") != "pass" or item.get("trainingUse") != "prohibited":
            raise ValueError(f"第{index}项未通过源图门或被错误晋升")
        checks = item.get("originalResolutionChecks") or {}
        required_checks = ["allRequiredNailsFullyVisible", "noNailTouchesImageEdge", "sharpEnoughForCompleteBoundary", "noOcclusion", "noTextLogoOrWatermark", "anatomyPlausible"]
        if any(checks.get(key) is not True for key in required_checks):
            raise ValueError(f"第{index}项原分辨率检查不完整")
        path = Path(str(item.get("path") or "")).resolve()
        if not path.is_file() or path.suffix.lower() != ".png":
            raise ValueError(f"第{index}项图片不存在或不是PNG")
        image_hash = sha256_file(path)
        width, height = png_dimensions(path)
        if image_hash != item.get("imageSha256") or [width, height] != item.get("dimensions"):
            raise ValueError(f"第{index}项图片身份漂移")
        name, declared_hash, group = identity(item, f"第{index}项")
        values = {"fileName": name, "imageSha256": declared_hash, "sourceGroup": group}
        for field, value in values.items():
            if value in batch_sets[field]:
                raise ValueError(f"生成批次存在重复{field}")
            if value in used[field]:
                raise ValueError(f"生成批次与受保护或已使用角色发生{field}交叠")
            batch_sets[field].add(value)
        nail_count = int(item.get("fullyVisibleNails") or 0)
        if nail_count not in {5, 10}:
            raise ValueError(f"第{index}项完整甲面数无效")
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
            "generatedImages": len(frozen),
            "sourceQualifiedImages": len(frozen),
            "sourceGroups": len(batch_sets["sourceGroup"]),
            "fullyVisibleNails": sum(item["fullyVisibleNails"] for item in frozen),
            "identityOrRoleOverlaps": 0,
            "targetSourceQualifiedImages": TARGET_SOURCE_QUALIFIED,
            "remainingSourceQualifiedImages": TARGET_SOURCE_QUALIFIED - len(frozen),
        },
        "items": frozen,
        "policy": {
            "frozenBeforeAnnotationOrModelAssistance": True,
            "exactModelIdClaimed": False,
            "sourceGateDoesNotApproveMasks": True,
            "sourceGateDoesNotPermitTraining": True,
            "protectedOrConsumedDataReused": False,
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
