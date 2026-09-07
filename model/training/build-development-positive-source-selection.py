#!/usr/bin/env python3
"""构建并重放开发正样本源图选择，阻止与既有受保护角色身份交叠。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_object(path: Path, label: str) -> dict[str, Any]:
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
        group = item.get("parentSourceGroup") or item.get("sourceGroup")
        if name:
            names.add(name)
        if image_hash:
            hashes.add(require_sha(image_hash, f"{label}第{index}项图片"))
        if group:
            groups.add(str(group))
    return names, hashes, groups


def protected_identities(registry_path: Path) -> tuple[set[str], set[str], set[str]]:
    registry = load_object(registry_path, "困难负样本保护登记表")
    if registry.get("ok") is not True or registry.get("decision") != "protected_hard_negative_registry":
        raise ValueError("困难负样本保护登记表状态无效")
    result = (set(), set(), set())
    for index, entry in enumerate(registry.get("entries") or [], start=1):
        manifest_path = Path(str(entry.get("path") or "")).resolve()
        expected = require_sha(entry.get("sha256"), f"保护登记第{index}项")
        if not manifest_path.is_file() or sha256_file(manifest_path) != expected:
            raise ValueError(f"困难负样本manifest漂移：{manifest_path}")
        manifest = load_object(manifest_path, "困难负样本manifest")
        current = identities(manifest.get("items"), f"困难负样本manifest {manifest_path.name}")
        for target, values in zip(result, current, strict=True):
            target.update(values)
    return result


def build(args: argparse.Namespace) -> dict[str, Any]:
    paths = {
        "spec": Path(args.spec).resolve(),
        "trainingTruthIndex": Path(args.training_truth_index).resolve(),
        "validationTruthIndex": Path(args.validation_truth_index).resolve(),
        "frozenTestManifest": Path(args.frozen_test_manifest).resolve(),
        "protectedRegistry": Path(args.protected_registry).resolve(),
        "standingAuthorization": Path(args.standing_authorization).resolve(),
    }
    spec = load_object(paths["spec"], "源图选择规格")
    train = load_object(paths["trainingTruthIndex"], "训练真值索引")
    validation = load_object(paths["validationTruthIndex"], "验证真值索引")
    frozen = load_object(paths["frozenTestManifest"], "冻结test manifest")
    authorization = load_object(paths["standingAuthorization"], "standing商业授权")
    if spec.get("decision") != "development_positive_source_candidates_pending_audit":
        raise ValueError("源图选择规格decision无效")
    if train.get("ok") is not True or train.get("decision") != "approved_unique_training_truth_index":
        raise ValueError("训练真值索引状态无效")
    if validation.get("ok") is not True or validation.get("decision") != "approved_unique_validation_truth_index":
        raise ValueError("验证真值索引状态无效")
    if frozen.get("trainingUse") != "prohibited" or not isinstance(frozen.get("items"), list):
        raise ValueError("冻结test manifest状态无效")
    if (
        authorization.get("decision") != "standing_project_commercial_resource_authorization_granted"
        or authorization.get("scope", {}).get("itemizedTrainingAuthorizationRequired") is not False
    ):
        raise ValueError("standing商业授权无效")

    role_sets = {
        "train": identities(train.get("canonicalTruths"), "训练真值"),
        "validation": identities(validation.get("canonicalTruths"), "验证真值"),
        "frozenTest": identities(frozen.get("items"), "冻结test"),
        "protectedHardNegative": protected_identities(paths["protectedRegistry"]),
    }
    source_root = Path(str(spec.get("sourceRoot") or "")).resolve()
    if not source_root.is_dir():
        raise ValueError(f"源图目录不存在：{source_root}")
    raw_items = spec.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("源图选择规格没有items")
    records: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    seen_hashes: set[str] = set()
    seen_groups: set[str] = set()
    for index, item in enumerate(raw_items, start=1):
        file_name = str(item.get("fileName") or "")
        source_group = str(item.get("sourceGroup") or "")
        expected_nails = item.get("expectedFullyVisibleNails")
        if not file_name or not source_group or not isinstance(expected_nails, int) or expected_nails < 1:
            raise ValueError(f"规格第{index}项身份或完整甲数无效")
        image_path = (source_root / file_name).resolve()
        if image_path.parent != source_root or not image_path.is_file():
            raise ValueError(f"源图路径缺失或逃逸：{file_name}")
        image_hash = sha256_file(image_path)
        if item.get("sha256") and image_hash != require_sha(item.get("sha256"), file_name):
            raise ValueError(f"源图SHA漂移：{file_name}")
        if file_name.casefold() in seen_names or image_hash in seen_hashes or source_group in seen_groups:
            raise ValueError(f"批内文件、哈希或来源组重复：{file_name}")
        for role, (names, hashes, groups) in role_sets.items():
            if file_name.casefold() in names or image_hash in hashes or source_group in groups:
                raise ValueError(f"源图与{role}角色冲突：{file_name}")
        with Image.open(image_path) as image:
            image.verify()
        with Image.open(image_path) as image:
            width, height = image.size
            image.load()
            image_format = image.format
        if (item.get("width"), item.get("height")) != (width, height):
            raise ValueError(f"源图尺寸与规格不一致：{file_name}")
        seen_names.add(file_name.casefold())
        seen_hashes.add(image_hash)
        seen_groups.add(source_group)
        records.append({
            "fileName": file_name,
            "sha256": image_hash,
            "bytes": image_path.stat().st_size,
            "width": width,
            "height": height,
            "format": image_format,
            "sourceGroup": source_group,
            "expectedFullyVisibleNails": expected_nails,
            "coverageIntent": str(item.get("coverageIntent") or ""),
            "sourceReviewStatus": "pass_pending_complete_mask_review",
            "annotationTruthStatus": "not-started",
            "trainingUse": "prohibited",
        })
    return {
        "schemaVersion": 1,
        "ok": True,
        "decision": "development_positive_annotation_workspace_ready_candidate_only",
        "inputs": {key: {"path": str(path), "sha256": sha256_file(path)} for key, path in paths.items()},
        "sourceRoot": str(source_root),
        "imageDir": str(source_root),
        "policy": {
            "standingCommercialAuthorizationRecorded": True,
            "trainValidationFrozenTestAndProtectedNegativeOverlap": 0,
            "originalResolutionSourceReviewRequired": True,
            "completeNailMaskReviewRequired": True,
            "modelOutputMayOnlyGenerateReviewCandidates": True,
            "trainingUse": "prohibited-until-truth-finalization-and-materialization-audit",
        },
        "counts": {
            "images": len(records),
            "sourceGroups": len(seen_groups),
            "expectedFullyVisibleNails": sum(item["expectedFullyVisibleNails"] for item in records),
        },
        "itemsSha256": canonical_sha256(records),
        "items": records,
        "trainingUse": "prohibited",
        "errors": [],
    }


def write_atomic(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise ValueError(f"输出不得覆盖既有证据：{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.tmp-", dir=path.parent)
    os.close(descriptor)
    temporary = Path(name)
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec")
    parser.add_argument("--training-truth-index")
    parser.add_argument("--validation-truth-index")
    parser.add_argument("--frozen-test-manifest")
    parser.add_argument("--protected-registry")
    parser.add_argument("--standing-authorization")
    parser.add_argument("--output")
    parser.add_argument("--verify-report")
    args = parser.parse_args()
    if args.verify_report:
        report_path = Path(args.verify_report).resolve()
        existing = load_object(report_path, "待重放报告")
        inputs = existing.get("inputs") or {}
        replay = argparse.Namespace(**{
            "spec": inputs["spec"]["path"],
            "training_truth_index": inputs["trainingTruthIndex"]["path"],
            "validation_truth_index": inputs["validationTruthIndex"]["path"],
            "frozen_test_manifest": inputs["frozenTestManifest"]["path"],
            "protected_registry": inputs["protectedRegistry"]["path"],
            "standing_authorization": inputs["standingAuthorization"]["path"],
        })
        if build(replay) != existing:
            raise ValueError("报告与当前磁盘重放结果不一致")
        print(json.dumps({"ok": True, "decision": "verified", "report": str(report_path)}, ensure_ascii=False))
        return 0
    required = [args.spec, args.training_truth_index, args.validation_truth_index, args.frozen_test_manifest,
                args.protected_registry, args.standing_authorization, args.output]
    if any(value is None for value in required):
        raise ValueError("构建模式缺少必填参数")
    output = Path(args.output).resolve()
    report = build(args)
    write_atomic(output, report)
    print(json.dumps({"ok": True, "counts": report["counts"], "output": str(output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
