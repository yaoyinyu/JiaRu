#!/usr/bin/env python3
"""循环015真实素材正图入库：只读盘点、身份角色隔离与原分辨率源图门审计。

背景（用户2026-09-19指令与裁决）：
1. 停用AI生成图片供给——对今后批次生效，循环015供给改由用户提供的真实素材承担；
2. 已冻结的43张内置生成源图经用户裁决保留计入133供给账，历史证据原样保留。

本审计器提供两个模式：
- --inventory：对真实素材目录做只读盘点（字节SHA-256、图片头尺寸、精确重复分组、
  低分辨率标记），不解码、不改写任何图片文件；
- 审计模式：绑定累计真实素材声明、当前角色供给审计、提速路线审计与前序生成入库
  审计报告，对前序条目做逐字核验，对新增真实素材条目做完整原分辨率源图门验证
  （含新增的 notSuspectedAiGenerated 检查），并执行三重身份/角色交叠拒绝。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path
from typing import Any


TARGET_SOURCE_QUALIFIED = 133
MIN_DIMENSION = 512
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
REQUIRED_CHECKS = [
    "allRequiredNailsFullyVisible",
    "noNailTouchesImageEdge",
    "sharpEnoughForCompleteBoundary",
    "noOcclusion",
    "noTextLogoOrWatermark",
    "anatomyPlausible",
    "notSuspectedAiGenerated",
]
PRIOR_CUMULATIVE_SOURCE_QUALIFIED = 43


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
    return width, height


def jpeg_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if data[:2] != b"\xff\xd8":
        raise ValueError(f"不是有效JPEG头：{path}")
    offset = 2
    size = len(data)
    while offset + 4 <= size:
        if data[offset] != 0xFF:
            raise ValueError(f"JPEG标记流损坏：{path}")
        marker = data[offset + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            offset += 2
            continue
        if marker == 0xDA:
            break
        if offset + 4 > size:
            break
        seg_len = struct.unpack(">H", data[offset + 2 : offset + 4])[0]
        if seg_len < 2:
            raise ValueError(f"JPEG段长度无效：{path}")
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            if seg_len < 7 or offset + 2 + seg_len > size:
                raise ValueError(f"JPEG SOF段损坏：{path}")
            height, width = struct.unpack(">HH", data[offset + 5 : offset + 9])
            return width, height
        offset += 2 + seg_len
    raise ValueError(f"JPEG缺少SOF尺寸段：{path}")


def image_dimensions(path: Path) -> tuple[int, int, str]:
    suffix = path.suffix.lower()
    if suffix == ".png":
        width, height = png_dimensions(path)
        return width, height, "png"
    if suffix in {".jpg", ".jpeg"}:
        width, height = jpeg_dimensions(path)
        return width, height, "jpeg"
    raise ValueError(f"不支持的图片格式：{path}")


def check_min_dimension(width: int, height: int, path: Path) -> None:
    if width < MIN_DIMENSION or height < MIN_DIMENSION:
        raise ValueError(f"候选分辨率低于{MIN_DIMENSION}：{path}（{width}x{height}）")


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


def run_inventory(scan_root: Path, output: Path) -> dict[str, Any]:
    files = sorted(p for p in scan_root.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES)
    records: list[dict[str, Any]] = []
    by_hash: dict[str, list[str]] = {}
    for path in files:
        digest = sha256_file(path)
        rel = path.relative_to(scan_root).as_posix()
        width = height = 0
        fmt = path.suffix.lower().lstrip(".")
        dim_error = None
        try:
            width, height, fmt = image_dimensions(path)
        except ValueError as error:
            dim_error = str(error)
        record: dict[str, Any] = {
            "fileName": rel,
            "path": str(path),
            "bytes": path.stat().st_size,
            "sha256": digest,
            "format": fmt,
            "width": width,
            "height": height,
            "lowResolution": bool(dim_error is None and (width < MIN_DIMENSION or height < MIN_DIMENSION)),
        }
        if dim_error is not None:
            record["dimensionError"] = dim_error
        records.append(record)
        by_hash.setdefault(digest, []).append(rel)
    duplicates = [
        {"sha256": sha, "members": members}
        for sha, members in sorted(by_hash.items())
        if len(members) > 1
    ]
    report = {
        "schemaVersion": 1,
        "analysisKind": "cycle015_real_material_inventory",
        "scanRoot": str(scan_root),
        "fileCount": len(records),
        "uniqueBySha256": len(by_hash),
        "duplicateGroups": duplicates,
        "lowResolutionCount": sum(1 for record in records if record["lowResolution"]),
        "files": records,
        "readImagePixels": False,
        "runTraining": False,
        "runInference": False,
        "note": "只读盘点：仅计算字节哈希与图片头尺寸，未解码像素、未改写任何图片文件",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise ValueError(f"输出已存在，禁止覆盖：{output}")
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "fileCount": len(records),
                "uniqueBySha256": len(by_hash),
                "duplicateGroups": len(duplicates),
                "lowResolutionCount": report["lowResolutionCount"],
            },
            ensure_ascii=False,
        )
    )
    return report


def validate_prior_items(
    prior_items: list[dict[str, Any]],
    items: list[dict[str, Any]],
    prior_report: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    prior_frozen = {str(item.get("fileName") or ""): item for item in prior_report.get("items") or []}
    prior_excluded = {str(item.get("fileName") or ""): item for item in prior_report.get("excludedItems") or []}
    if len(prior_frozen) + len(prior_excluded) != len(prior_items):
        raise ValueError("前序冻结条目数与前序审计报告的通过/排除计数不一致")
    for index, (prior, current) in enumerate(zip(prior_items, items, strict=False), start=1):
        if current != prior:
            raise ValueError(f"前序冻结条目被改写：第{index}项 {prior.get('fileName')}")
        name = str(prior.get("fileName") or "")
        report_item = prior_frozen.get(name) or prior_excluded.get(name)
        if report_item is None:
            raise ValueError(f"前序冻结条目在前序审计报告中不存在：{name}")
        if report_item.get("imageSha256") != prior.get("imageSha256"):
            raise ValueError(f"前序冻结条目哈希与前序审计报告不一致：{name}")
        if report_item.get("sourceGroup") != prior.get("sourceGroup"):
            raise ValueError(f"前序冻结条目来源组与前序审计报告不一致：{name}")
        if report_item.get("sourceGateDecision") != prior.get("sourceGateDecision"):
            raise ValueError(f"前序冻结条目源图门决定与前序审计报告不一致：{name}")
    return prior_frozen


def audit(
    declaration_path: Path,
    source_supply_path: Path,
    route_path: Path,
    prior_audit_path: Path,
) -> dict[str, Any]:
    declaration_path = declaration_path.resolve()
    source_supply_path = source_supply_path.resolve()
    route_path = route_path.resolve()
    prior_audit_path = prior_audit_path.resolve()
    declaration = read_object(declaration_path, "真实素材批次声明")
    source_supply = read_object(source_supply_path, "当前角色供给审计")
    route = read_object(route_path, "提速路线审计")
    prior_report = read_object(prior_audit_path, "前序生成入库审计报告")

    if declaration.get("decision") != "real_material_sources_reviewed_at_original_resolution":
        raise ValueError("真实素材批次声明未完成原分辨率源图门")
    if declaration.get("reviewScale") != "original-resolution" or declaration.get("trainingUse") != "prohibited":
        raise ValueError("真实素材批次声明审核尺度或训练角色无效")
    if declaration.get("sourceType") != "user-provided-real-material":
        raise ValueError("真实素材批次声明来源类型无效")
    if declaration.get("authorization") != "standing-project-commercial-development-authorization":
        raise ValueError("真实素材批次未绑定standing商业开发授权")
    if declaration.get("reviewedBy") != "WorkBuddy":
        raise ValueError("真实素材批次审核者登记无效")
    if declaration.get("role") != "development-evaluation-extension":
        raise ValueError("真实素材批次角色漂移")
    channel = declaration.get("supplyChannelChange") or {}
    if channel.get("directive") != "user-directive-2026-09-19-disable-ai-generated-supply-use-real-material":
        raise ValueError("供给渠道变更指令登记无效")
    if channel.get("aiGeneratedSupplyDisabledGoingForward") is not True:
        raise ValueError("停用AI生成供给未登记为今后生效")
    if channel.get("priorGeneratedItemsRetained") != PRIOR_CUMULATIVE_SOURCE_QUALIFIED:
        raise ValueError("前序43张保留计入裁决未登记")

    prior_freeze = declaration.get("priorFreeze")
    if not isinstance(prior_freeze, dict):
        raise ValueError("前序冻结绑定不是JSON对象")
    prior_path = Path(str(prior_freeze.get("path") or "")).resolve()
    if sha256_file(prior_path) != prior_freeze.get("sha256"):
        raise ValueError("前序冻结声明字节哈希漂移")
    prior_declaration = read_object(prior_path, "前序冻结声明")
    prior_items = prior_declaration.get("items")
    if not isinstance(prior_items, list) or not prior_items:
        raise ValueError("前序冻结声明条目缺失")
    if len(prior_items) != prior_freeze.get("itemCount"):
        raise ValueError("前序冻结声明条目计数漂移")
    if prior_declaration.get("decision") != "generated_sources_reviewed_at_original_resolution":
        raise ValueError("前序冻结声明不是生成素材入库声明")
    prior_count = len(prior_items)

    prior_report_counts = prior_report.get("counts") or {}
    if not isinstance(prior_report_counts.get("sourceQualifiedImages"), int):
        raise ValueError("前序入库审计报告缺少通过计数")
    prior_report_declaration = (prior_report.get("inputs") or {}).get("declaration") or {}
    if Path(str(prior_report_declaration.get("path") or "")).resolve() != prior_path:
        raise ValueError("前序审计报告绑定的声明与priorFreeze不一致")
    if prior_report_declaration.get("sha256") != prior_freeze.get("sha256"):
        raise ValueError("前序审计报告绑定的声明哈希与priorFreeze不一致")
    if (prior_report.get("counts") or {}).get("sourceQualifiedImages") != PRIOR_CUMULATIVE_SOURCE_QUALIFIED:
        raise ValueError("前序审计报告通过计数漂移")

    if source_supply.get("decision") != "recover_7_candidates_and_acquire_at_least_43_for_first_50_batch":
        raise ValueError("当前角色供给审计合同漂移")
    if route.get("decision") != "replace_50_candidate_intake_with_133_source_qualified_development_cohort":
        raise ValueError("提速路线审计合同漂移")
    if (route.get("routeSizing") or {}).get("sourceQualifiedCandidatesConservativeFloor") != TARGET_SOURCE_QUALIFIED:
        raise ValueError("133张候选下限漂移")
    used, role_counts = role_identity_sets(source_supply)

    items = declaration.get("items")
    if not isinstance(items, list) or not prior_count < len(items):
        raise ValueError("累计声明条目数无效：必须至少包含一条新增真实素材条目")
    validate_prior_items(prior_items, items[:prior_count], prior_report)

    prior_identity = {"fileName": set(), "imageSha256": set(), "sourceGroup": set()}
    for prior in prior_items:
        name, image_hash, group = identity(prior, "前序冻结条目")
        prior_identity["fileName"].add(name)
        prior_identity["imageSha256"].add(image_hash)
        prior_identity["sourceGroup"].add(group)

    batch_sets = {"fileName": set(), "imageSha256": set(), "sourceGroup": set()}
    frozen: list[dict[str, Any]] = list(prior_report.get("items") or [])
    excluded: list[dict[str, Any]] = list(prior_report.get("excludedItems") or [])
    new_frozen: list[dict[str, Any]] = []
    for offset, item in enumerate(items[prior_count:], start=1):
        index = prior_count + offset
        source_gate = item.get("sourceGateDecision")
        if source_gate not in {"pass", "exclude"} or item.get("trainingUse") != "prohibited":
            raise ValueError(f"第{index}项源图门或训练角色无效")
        checks = item.get("originalResolutionChecks") or {}
        if any(key not in checks for key in REQUIRED_CHECKS):
            raise ValueError(f"第{index}项原分辨率检查键不完整")
        watermark_registration = item.get("watermarkRegistration")
        if source_gate == "exclude" and watermark_registration is not None:
            raise ValueError(f"第{index}项为排除项，不应携带水印登记")
        if source_gate == "pass":
            required_values = {key: True for key in REQUIRED_CHECKS}
            if watermark_registration is not None:
                if not isinstance(watermark_registration, dict):
                    raise ValueError(f"第{index}项水印登记不是JSON对象")
                if checks.get("noTextLogoOrWatermark") is not False:
                    raise ValueError(f"第{index}项已登记水印但检查值不是false")
                for field in ("type", "position", "description"):
                    if not str(watermark_registration.get(field) or "").strip():
                        raise ValueError(f"第{index}项水印登记缺少{field}")
                if watermark_registration.get("ablationRequiredBeforeTrainingUse") is not True:
                    raise ValueError(f"第{index}项水印登记缺少训练前消融义务")
                required_values.pop("noTextLogoOrWatermark")
            if any(checks.get(key) is not value for key, value in required_values.items()):
                raise ValueError(f"第{index}项原分辨率检查不完整")
        # 排除项：检查值如实登记、不强制具体失败组合，排除依据由 exclusionReason 承载
        path = Path(str(item.get("path") or "")).resolve()
        if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
            raise ValueError(f"第{index}项图片不存在或格式不受支持")
        image_hash = sha256_file(path)
        width, height, fmt = image_dimensions(path)
        if image_hash != item.get("imageSha256") or [width, height] != item.get("dimensions"):
            raise ValueError(f"第{index}项图片身份漂移")
        if source_gate == "pass":
            check_min_dimension(width, height, path)
        origin = Path(str(item.get("originPath") or "")).resolve()
        if not origin.is_file() or origin.suffix.lower() not in IMAGE_SUFFIXES:
            raise ValueError(f"第{index}项原始素材文件缺失或格式不受支持")
        if sha256_file(origin) != image_hash:
            raise ValueError(f"第{index}项原始素材与登记副本哈希不一致")
        if item.get("format") != fmt:
            raise ValueError(f"第{index}项图片格式登记漂移")
        name, declared_hash, group = identity(item, f"第{index}项")
        values = {"fileName": name, "imageSha256": declared_hash, "sourceGroup": group}
        for field, value in values.items():
            if value in batch_sets[field]:
                raise ValueError(f"真实素材批次存在重复{field}")
            if value in prior_identity[field]:
                raise ValueError(f"真实素材批次与前序冻结条目发生{field}交叠")
            if value in used[field]:
                raise ValueError(f"真实素材批次与受保护或已使用角色发生{field}交叠")
            batch_sets[field].add(value)
        nail_count = int(item.get("fullyVisibleNails") or 0)
        if source_gate == "pass" and not 1 <= nail_count <= 10:
            raise ValueError(f"第{index}项完整甲面数无效")
        if not str(item.get("visualProfile") or "").strip():
            raise ValueError(f"第{index}项视觉画像缺失")
        if source_gate == "exclude":
            if not str(item.get("exclusionReason") or "").strip():
                raise ValueError(f"第{index}项排除但缺少原因")
            excluded.append(
                {
                    "fileName": item["fileName"],
                    "path": str(path),
                    "imageSha256": image_hash,
                    "sourceGroup": group,
                    "sourceGateDecision": "exclude",
                    "exclusionReason": item["exclusionReason"],
                    "trainingUse": "prohibited",
                }
            )
            continue
        new_frozen.append(
            {
                "fileName": item["fileName"],
                "path": str(path),
                "originPath": str(origin),
                "imageSha256": image_hash,
                "dimensions": [width, height],
                "format": fmt,
                "sourceGroup": group,
                "fullyVisibleNails": nail_count,
                "visualProfile": item["visualProfile"],
                "sourceGateDecision": "pass",
                "trainingUse": "prohibited",
                "requiredNextGate": "complete-mask annotation and original-resolution per-nail review",
                **(
                    {"watermarkRegistration": watermark_registration}
                    if watermark_registration is not None
                    else {}
                ),
            }
        )
    frozen.extend(new_frozen)
    if canonical_sha256(items) != declaration.get("itemsSha256"):
        raise ValueError("真实素材批次条目摘要漂移")

    total_qualified = len(frozen)
    if total_qualified > TARGET_SOURCE_QUALIFIED:
        raise ValueError(f"累计通过数超过133张上限：{total_qualified}")
    return {
        "schemaVersion": 1,
        "ok": True,
        "decision": f"freeze_{total_qualified}_cumulative_source_qualified_candidates_continue_to_133",
        "analysisKind": "real_material_source_identity_role_and_original_resolution_gate_audit",
        "readImagePixels": True,
        "runTraining": False,
        "runInference": False,
        "inputs": {
            "declaration": {"path": str(declaration_path), "sha256": sha256_file(declaration_path)},
            "sourceSupply": {"path": str(source_supply_path), "sha256": sha256_file(source_supply_path)},
            "accelerationRoute": {"path": str(route_path), "sha256": sha256_file(route_path)},
            "priorIntakeAudit": {"path": str(prior_audit_path), "sha256": sha256_file(prior_audit_path)},
        },
        "currentRoleLedger": role_counts,
        "counts": {
            "sourceImages": len(items),
            "priorRetainedImages": PRIOR_CUMULATIVE_SOURCE_QUALIFIED,
            "newRealMaterialImages": len(new_frozen),
            "sourceQualifiedImages": total_qualified,
            "sourceGroups": len({item["sourceGroup"] for item in frozen}),
            "fullyVisibleNails": sum(int(item["fullyVisibleNails"]) for item in frozen),
            "identityOrRoleOverlaps": 0,
            "targetSourceQualifiedImages": TARGET_SOURCE_QUALIFIED,
            "remainingSourceQualifiedImages": TARGET_SOURCE_QUALIFIED - total_qualified,
        },
        "items": frozen,
        "newItems": new_frozen,
        "excludedItems": excluded,
        "policy": {
            "frozenBeforeAnnotationOrModelAssistance": True,
            "sourceGateDoesNotApproveMasks": True,
            "sourceGateDoesNotPermitTraining": True,
            "protectedOrConsumedDataReused": False,
            "supersededSourceGatePassesPreservedAsExcludedEvidence": True,
            "aiGeneratedSupplyDisabledGoingForward": True,
            "priorGeneratedItemsRetainedPerUserRuling": True,
            "suspectedAiGeneratedImagesExcluded": True,
            "watermarkBearingItemsRegisteredWithAblationDebt": True,
            "edgeCroppedOccludedOrUnconfirmableNailImagesStillExcludedPerGoalCoreRequirements": True,
        },
        "trainingUse": "prohibited",
        "formalPromotionAllowed": False,
        "nextAction": (
            f"review_and_freeze_next_{TARGET_SOURCE_QUALIFIED - total_qualified}_"
            f"source_qualified_real_material_candidates_to_reach_133_of_133"
            if total_qualified < TARGET_SOURCE_QUALIFIED
            else "source_supply_target_reached_proceed_to_annotation_pipeline"
        ),
        "releaseState": "hold",
        "productState": "hold",
        "errors": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", action="store_true", help="只读盘点模式")
    parser.add_argument("--scan-root")
    parser.add_argument("--declaration")
    parser.add_argument("--source-supply")
    parser.add_argument("--acceleration-route")
    parser.add_argument("--prior-intake-audit")
    parser.add_argument("--output")
    parser.add_argument("--verify-report")
    args = parser.parse_args()
    if args.inventory:
        if not args.scan_root or not args.output:
            raise ValueError("盘点模式缺少必填参数")
        run_inventory(Path(args.scan_root).resolve(), Path(args.output).resolve())
        return 0
    if args.verify_report:
        report_path = Path(args.verify_report).resolve()
        existing = read_object(report_path, "待重放真实素材批次报告")
        inputs = existing.get("inputs") or {}
        replay = audit(
            Path(inputs["declaration"]["path"]),
            Path(inputs["sourceSupply"]["path"]),
            Path(inputs["accelerationRoute"]["path"]),
            Path(inputs["priorIntakeAudit"]["path"]),
        )
        if replay != existing:
            raise ValueError("真实素材批次报告与绑定输入重放不一致")
        print(json.dumps({"ok": True, "decision": existing["decision"], "reportSha256": sha256_file(report_path)}, ensure_ascii=False))
        return 0
    if not args.declaration or not args.source_supply or not args.acceleration_route or not args.prior_intake_audit or not args.output:
        raise ValueError("构建模式缺少必填参数")
    output = Path(args.output).resolve()
    if output.exists():
        raise ValueError(f"输出已存在，禁止覆盖：{output}")
    report = audit(
        Path(args.declaration),
        Path(args.source_supply),
        Path(args.acceleration_route),
        Path(args.prior_intake_audit),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"], "counts": report["counts"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
