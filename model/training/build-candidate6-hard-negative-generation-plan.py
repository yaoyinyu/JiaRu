#!/usr/bin/env python3
"""Build the candidate6 training-negative plan from candidate5 rejection evidence.

The candidate5 independent holdout is immutable evaluation evidence. This tool
derives only a failure taxonomy and a new 160-item generation plan. It never
copies holdout images, generates images, grants authorization, or permits
training. The resulting pool remains prohibited until exact user authorization
and original-resolution review are complete.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


EXPECTED_COUNT = 160
FAMILY_SIZE = 10
EXPECTED_CANDIDATE5_WEIGHTS_SHA256 = (
    "26daf742ce83a9d740a786114cfec481051e6f86574ba1c43428f75e5db4ca56"
)
EXPECTED_FAILURE_FAMILIES = {
    "botanical_seed_pods_samaras",
    "laboratory_pipette_tips_microtubes",
    "pharma_softgel_blisters",
}
FAMILIES: tuple[tuple[str, str], ...] = (
    ("softgel_blister_single", "单粒软胶囊泡罩、完整铝塑包装与真实药品陈列"),
    ("softgel_blister_cluster", "多粒软胶囊泡罩、不同排布、颜色与视角"),
    ("softgel_loose_capsules", "散装完整软胶囊、玻璃皿或药盒内自然堆放"),
    ("softgel_translucent_backlit", "半透明软胶囊、逆光高光与材质厚度变化"),
    ("samara_dry_clusters", "干燥翅果、槭树种子和完整枝梗簇"),
    ("seed_pod_glossy_macro", "清晰种荚、果荚与高光种子近景"),
    ("seed_capsule_translucent", "半透明植物蒴果、薄壳种荚与自然纹理"),
    ("winged_seed_mixed_scale", "不同尺度翅果、单体与群落自然场景"),
    ("pipette_tip_racks", "移液枪吸头盒、完整吸头阵列与实验台场景"),
    ("pipette_tip_loose", "散置移液吸头、完整锥形结构与多角度陈列"),
    ("microtube_racks", "微量离心管架、完整管盖和实验室容器阵列"),
    ("microtube_loose", "散置微量离心管、透明塑料与完整管体"),
    ("lab_disposable_translucent", "透明实验耗材、滴管头、样品管与包装件"),
    ("mixed_softgel_seedpod", "软胶囊与植物种荚的全新独立场景组合"),
    ("mixed_lab_botanical", "实验耗材与植物标本的全新独立场景组合"),
    ("mixed_scale_reflective_confuser", "上述类别跨尺度、反光和半透明全新场景"),
)


def load_candidate5_module() -> Any:
    path = Path(__file__).with_name("build-candidate5-hard-negative-generation-plan.py")
    spec = importlib.util.spec_from_file_location("jiaru_candidate5_plan_base", path)
    if spec is None or spec.loader is None:
        raise ValueError("cannot load candidate5 plan contract")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


BASE = load_candidate5_module()


def record_family(record: dict[str, Any]) -> str:
    source_group = record.get("sourceGroup")
    if not isinstance(source_group, str) or ":" not in source_group:
        raise ValueError("candidate5 audit record sourceGroup is invalid")
    return source_group.rsplit(":", 1)[1]


def derive_failure_taxonomy(audit: dict[str, Any]) -> dict[str, Any]:
    records = audit.get("records")
    deployment = audit.get("deploymentThreshold")
    if not isinstance(records, list) or len(records) != 100:
        raise ValueError("candidate5 audit must contain exactly 100 records")
    if not isinstance(deployment, dict):
        raise ValueError("candidate5 audit deployment summary is missing")

    variants = ("original", "crop12", "blur_corner")
    counts_by_variant: dict[str, list[int]] = {}
    failing_indices: set[int] = set()
    for variant in variants:
        summary = deployment.get(variant)
        counts = summary.get("counts") if isinstance(summary, dict) else None
        if (
            not isinstance(counts, list)
            or len(counts) != len(records)
            or any(type(value) is not int or value < 0 for value in counts)
        ):
            raise ValueError(f"candidate5 {variant} deployment counts are invalid")
        counts_by_variant[variant] = counts
        failing_indices.update(index for index, value in enumerate(counts) if value > 0)

    failures: list[dict[str, Any]] = []
    for index in sorted(failing_indices):
        record = records[index]
        if not isinstance(record, dict):
            raise ValueError("candidate5 audit record must be an object")
        failures.append(
            {
                "recordIndex": index + 1,
                "fileName": record.get("fileName"),
                "sourceSha256": record.get("sourceSha256"),
                "sourceGroup": record.get("sourceGroup"),
                "promptFamily": record_family(record),
                "deploymentDetections": {
                    variant: counts_by_variant[variant][index] for variant in variants
                },
            }
        )

    families = {failure["promptFamily"] for failure in failures}
    if families != EXPECTED_FAILURE_FAMILIES:
        raise ValueError(
            "candidate5 failure-family evidence drift: "
            f"expected={sorted(EXPECTED_FAILURE_FAMILIES)}, actual={sorted(families)}"
        )
    if len(failures) != 5:
        raise ValueError(f"candidate5 failure-image count drift: {len(failures)}")
    return {
        "failedImageCount": len(failures),
        "failedFamilies": sorted(families),
        "failures": failures,
    }


def require_holdout_in_registry(
    audit: dict[str, Any], registry_path: Path
) -> dict[str, Any]:
    registry = BASE.read_json(registry_path, "protected hard-negative registry")
    entries = registry.get("entries")
    manifest = audit.get("inputs", {}).get("hardNegativeManifest", {})
    expected = {
        "path": manifest.get("path"),
        "sha256": manifest.get("sha256"),
        "role": "holdout",
    }
    if not isinstance(entries, list) or expected not in entries:
        raise ValueError("candidate5 rejected holdout is not protected by the registry")
    return expected


def build_plan(
    source_root: Path, batch_date: str, registry_binding: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if len(FAMILIES) * FAMILY_SIZE != EXPECTED_COUNT:
        raise RuntimeError("candidate6 family allocation no longer sums to 160")
    items: list[dict[str, Any]] = []
    for family, _ in FAMILIES:
        for variant in range(1, FAMILY_SIZE + 1):
            sequence = len(items) + 1
            items.append(
                {
                    "sequence": sequence,
                    "expectedFileName": (
                        f"hard_negative_training_{batch_date}_{sequence:03d}_"
                        f"{family}_{variant:02d}.png"
                    ),
                    "promptId": f"candidate6.{family}.{variant:02d}",
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
            "minimumSide": BASE.MINIMUM_SIDE,
            "nearDuplicateThreshold": BASE.NEAR_DUPLICATE_DISTANCE,
            "protectedHardNegativeRegistry": {
                "path": registry_binding["path"],
                "sha256": registry_binding["sha256"],
            },
            "itemsSha256": BASE.canonical_sha256(items),
            "items": items,
        },
        items,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate5-audit", required=True)
    parser.add_argument("--protected-hard-negative-registry", required=True)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--batch-date", required=True)
    parser.add_argument("--output-plan", required=True)
    parser.add_argument("--output-brief", required=True)
    args = parser.parse_args()

    if len(args.batch_date) != 8 or not args.batch_date.isdigit():
        raise ValueError("--batch-date must use YYYYMMDD")
    audit_path = BASE.require_plain_file(args.candidate5_audit, "candidate5 audit")
    registry_path = BASE.require_plain_file(
        args.protected_hard_negative_registry, "protected hard-negative registry"
    )
    output_plan = Path(args.output_plan).absolute()
    output_brief = Path(args.output_brief).absolute()
    if output_plan == output_brief:
        raise ValueError("plan and brief outputs must differ")

    audit, audit_verification = BASE.verify_rejected_holdout(audit_path)
    weights_sha256 = audit.get("inputs", {}).get("weights", {}).get("sha256")
    if weights_sha256 != EXPECTED_CANDIDATE5_WEIGHTS_SHA256:
        raise ValueError("rejected holdout is not bound to the approved candidate5 weights")
    taxonomy = derive_failure_taxonomy(audit)
    registry_binding = BASE.verify_registry(registry_path)
    protected_holdout = require_holdout_in_registry(audit, registry_path)
    source_root = BASE.require_empty_directory(args.source_root)
    plan, items = build_plan(source_root, args.batch_date, registry_binding)
    brief = {
        "schemaVersion": 1,
        "ok": True,
        "decision": "candidate6_hard_negative_failure_taxonomy_generation_brief",
        "role": "training-candidate",
        "trainingUse": "prohibited",
        "authorizationStatus": "missing",
        "candidate5Rejection": {
            "audit": {"path": str(audit_path), "sha256": BASE.sha256_file(audit_path)},
            "auditVerification": audit_verification,
            "weightsSha256": weights_sha256,
            "decision": audit["decision"],
            "releaseGeneralizationEligible": False,
            "protectedHoldout": protected_holdout,
            "failureTaxonomy": taxonomy,
        },
        "generationPlan": {
            "path": str(output_plan.resolve()),
            "itemsSha256": plan["itemsSha256"],
            "count": EXPECTED_COUNT,
        },
        "constraints": {
            "minimumSide": BASE.MINIMUM_SIDE,
            "nearDuplicateThreshold": BASE.NEAR_DUPLICATE_DISTANCE,
            "mustNotCopyProtectedTrainingOrHoldout": True,
            "mustNotContainRealHandOrNailSurface": True,
            "mustNotContainIndependentNailTipsOrTemplates": True,
            "mustNotContainNailArtToolsOrScenes": True,
            "mustNotContainTextWatermarkLogoUiBorderOrCollage": True,
            "mustBeSingleCoherentRealisticScene": True,
            "mustKeepPrimarySubjectCompleteAndSharp": True,
            "newSourceRequiredForFutureIndependentHoldout": True,
            "commercialTrainingRequiresNewExactUserAuthorization": True,
            "originalResolutionReviewRequiredBeforeAuthorization": True,
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
    BASE.atomic_write_json(output_plan, plan)
    try:
        BASE.atomic_write_json(output_brief, brief)
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
                "failedCandidate5Images": taxonomy["failedImageCount"],
                "failedFamilies": taxonomy["failedFamilies"],
                "trainingUse": "prohibited",
                "authorizationStatus": "missing",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
