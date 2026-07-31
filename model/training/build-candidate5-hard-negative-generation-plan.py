#!/usr/bin/env python3
"""Build a candidate5 training-negative plan from a rejected independent holdout.

Candidate4's independent holdout is immutable evaluation evidence. This tool
only converts its verified rejection into a new 160-item training-candidate
generation plan. It never copies holdout images, generates images, or grants
training eligibility. The emitted plan is compatible with the existing
generation-progress auditor.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any


EXPECTED_COUNT = 160
MINIMUM_SIDE = 768
NEAR_DUPLICATE_DISTANCE = 12
FAMILY_SIZE = 10
FAMILIES: tuple[tuple[str, str], ...] = (
    ("fish_lure_reflective", "反光鱼饵主体、匙形亮片与拟饵配件"),
    ("fish_lure_elongated", "细长拟饵、软虫饵与分段反光结构"),
    ("fish_lure_hooked", "带钩或金属环的鱼饵配件，禁止出现手或甲片"),
    ("furniture_hardware_oval", "椭圆家具拉手、旋钮与嵌入式五金"),
    ("furniture_hardware_plate", "金属底座、铭牌与亮面固定件"),
    ("furniture_hardware_knob", "圆角家具旋钮、抽屉把手与装饰五金"),
    ("hair_clip_oval", "椭圆发夹、鸭嘴夹与亮面发饰"),
    ("hair_clip_elongated", "细长发夹、发卡与层叠金属发饰"),
    ("hair_clip_reflective", "镜面或珠光发夹，不出现人手或头部"),
    ("jewelry_cabochon", "椭圆宝石、凸面饰品与戒面，禁止独立甲片"),
    ("jewelry_setting", "金属镶嵌、链坠与反光小饰件"),
    ("craft_hardware", "亮面手工五金、纽扣与紧固件"),
    ("cosmetic_tool", "非美甲用途的反光化妆工具和收纳配件"),
    ("plastic_glossy", "高光塑料小件、圆角夹具与包装配件"),
    ("stone_elongated", "细长抛光石、树脂件与椭圆装饰物"),
    ("mixed_visual_confuser", "上述类别的全新场景组合，禁止复刻留出图"),
)


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is unreadable JSON: {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain an object: {path}")
    return value


def is_link_or_reparse_point(path: Path) -> bool:
    attributes = int(getattr(path.lstat(), "st_file_attributes", 0))
    return path.is_symlink() or bool(
        getattr(path, "is_junction", lambda: False)()
    ) or bool(attributes & 0x0400)


def reject_linked_ancestors(path: Path, label: str) -> None:
    current = path
    while True:
        if is_link_or_reparse_point(current):
            raise ValueError(
                f"{label} cannot traverse a symbolic link, junction, or reparse point: {current}"
            )
        if current.parent == current:
            return
        current = current.parent


def require_plain_file(path_value: str, label: str) -> Path:
    candidate = Path(path_value).absolute()
    if not candidate.is_file():
        raise ValueError(f"{label} is missing: {candidate}")
    reject_linked_ancestors(candidate, label)
    return candidate.resolve(strict=True)


def load_module(name: str, filename: str) -> Any:
    script = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(name, script)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def require_empty_directory(path_value: str) -> Path:
    selected = Path(path_value).absolute()
    if selected.exists():
        reject_linked_ancestors(selected, "source root")
        source_root = selected.resolve(strict=True)
        if not source_root.is_dir():
            raise ValueError("source root must be a directory")
        if any(source_root.iterdir()):
            raise ValueError("source root must be empty before training-candidate generation")
        return source_root
    parent = selected.parent
    if not parent.is_dir():
        raise ValueError(f"source root parent is missing: {parent}")
    reject_linked_ancestors(parent, "source root parent")
    selected.mkdir()
    return selected.resolve(strict=True)


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise ValueError(f"output already exists and is immutable: {path}")
    if not path.parent.is_dir():
        raise ValueError(f"output parent is missing: {path.parent}")
    reject_linked_ancestors(path.parent, "output parent")
    staging = path.with_name(f".{path.name}.staging-{os.getpid()}-{uuid.uuid4().hex}")
    try:
        staging.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        staging.replace(path)
    finally:
        staging.unlink(missing_ok=True)


def verify_rejected_holdout(audit_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    audit_module = load_module(
        "jiaru_candidate5_holdout_audit", "audit-hard-negative-watermark-shortcut.py"
    )
    verification = audit_module.verify_report(audit_path)
    audit = read_json(audit_path, "candidate4 independent holdout audit")
    valid = (
        verification.get("ok") is True
        and audit.get("datasetRole") == "independent-holdout"
        and audit.get("ok") is False
        and audit.get("status") == "HOLD"
        and audit.get("decision") == "hold_hard_negative_watermark_shortcut_instability"
        and audit.get("releaseGeneralizationEligible") is False
        and audit.get("counts") == {"images": 100, "variants": 3, "inferenceViews": 300}
        and audit.get("configuration", {}).get("imgsz") == 512
        and audit.get("configuration", {}).get("maxFalsePositiveImages") == 0
        and audit.get("configuration", {}).get("maxVariantDetectionDelta") == 0
    )
    deployment = audit.get("deploymentThreshold")
    has_false_positive = isinstance(deployment, dict) and any(
        int(deployment.get(variant, {}).get("falsePositiveImages", 0)) > 0
        for variant in ("original", "crop12", "blur_corner")
    )
    if not valid or not has_false_positive:
        raise ValueError("candidate4 audit is not the expected rejected independent holdout")
    return audit, verification


def verify_registry(registry_path: Path) -> dict[str, Any]:
    contract = load_module(
        "jiaru_candidate5_training_authorization",
        "record-training-hard-negative-authorization.py",
    )
    binding, manifests, _ = contract.load_protected_registry(str(registry_path))
    if not manifests or binding.get("path") != str(registry_path):
        raise ValueError("protected hard-negative registry did not verify")
    return binding


def build_plan(
    source_root: Path, batch_date: str, registry_binding: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if len(FAMILIES) * FAMILY_SIZE != EXPECTED_COUNT:
        raise RuntimeError("candidate5 family allocation no longer sums to 160")
    items: list[dict[str, Any]] = []
    for family, _ in FAMILIES:
        for variant in range(1, FAMILY_SIZE + 1):
            sequence = len(items) + 1
            items.append(
                {
                    "sequence": sequence,
                    "expectedFileName": (
                        f"hard_negative_training_{batch_date}_{sequence:03d}_{family}_{variant:02d}.png"
                    ),
                    "promptId": f"candidate5.{family}.{variant:02d}",
                    "promptFamily": family,
                    "promptVariant": variant,
                    "role": "training-candidate",
                    "trainingUse": "prohibited",
                }
            )
    return (
        {
            "schemaVersion": 1,
            "ok": True,
            "decision": "training_hard_negative_generation_plan",
            "role": "training-candidate",
            "trainingUse": "prohibited",
            "authorizationStatus": "missing",
            "sourceRoot": str(source_root),
            "batchDate": batch_date,
            "expectedCount": EXPECTED_COUNT,
            "minimumSide": MINIMUM_SIDE,
            "nearDuplicateThreshold": NEAR_DUPLICATE_DISTANCE,
            "protectedHardNegativeRegistry": {
                "path": registry_binding["path"],
                "sha256": registry_binding["sha256"],
            },
            "itemsSha256": canonical_sha256(items),
            "items": items,
        },
        items,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a candidate5 negative generation plan from a rejected candidate4 holdout."
    )
    parser.add_argument("--candidate4-audit", required=True)
    parser.add_argument("--protected-hard-negative-registry", required=True)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--batch-date", required=True)
    parser.add_argument("--output-plan", required=True)
    parser.add_argument("--output-brief", required=True)
    args = parser.parse_args()

    if len(args.batch_date) != 8 or not args.batch_date.isdigit():
        raise ValueError("--batch-date must use YYYYMMDD")
    audit_path = require_plain_file(args.candidate4_audit, "candidate4 audit")
    registry_path = require_plain_file(
        args.protected_hard_negative_registry, "protected hard-negative registry"
    )
    output_plan = Path(args.output_plan).absolute()
    output_brief = Path(args.output_brief).absolute()
    if output_plan == output_brief:
        raise ValueError("plan and brief outputs must differ")

    audit, audit_verification = verify_rejected_holdout(audit_path)
    registry_binding = verify_registry(registry_path)
    source_root = require_empty_directory(args.source_root)
    plan, items = build_plan(source_root, args.batch_date, registry_binding)
    brief = {
        "schemaVersion": 1,
        "ok": True,
        "decision": "candidate5_hard_negative_failure_taxonomy_generation_brief",
        "role": "training-candidate",
        "trainingUse": "prohibited",
        "authorizationStatus": "missing",
        "candidate4Rejection": {
            "audit": {"path": str(audit_path), "sha256": sha256_file(audit_path)},
            "auditVerification": audit_verification,
            "decision": audit["decision"],
            "releaseGeneralizationEligible": False,
        },
        "generationPlan": {
            "path": str(output_plan.resolve()),
            "itemsSha256": plan["itemsSha256"],
            "count": EXPECTED_COUNT,
        },
        "constraints": {
            "minimumSide": MINIMUM_SIDE,
            "nearDuplicateThreshold": NEAR_DUPLICATE_DISTANCE,
            "mustNotCopyCandidate4Holdout": True,
            "mustNotContainRealHandOrNailSurface": True,
            "mustNotContainIndependentNailTipsOrTemplates": True,
            "mustNotContainWatermarkOrGeneratorMarker": True,
            "newSourceRequiredForFutureIndependentHoldout": True,
            "candidate5InferenceForbiddenBeforeGenerationRoleFreeze": True,
            "commercialTrainingRequiresNewExactUserAuthorization": True,
        },
        "families": [
            {
                "promptFamily": family,
                "target": target,
                "variants": FAMILY_SIZE,
                "sequenceStart": index * FAMILY_SIZE + 1,
                "sequenceEnd": (index + 1) * FAMILY_SIZE,
            }
            for index, (family, target) in enumerate(FAMILIES)
        ],
    }
    atomic_write_json(output_plan, plan)
    try:
        atomic_write_json(output_brief, brief)
    except Exception:
        output_plan.unlink(missing_ok=True)
        raise
    print(
        json.dumps(
            {
                "ok": True,
                "status": "PASS",
                "plan": str(output_plan),
                "brief": str(output_brief),
                "items": len(items),
                "trainingUse": "prohibited",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
