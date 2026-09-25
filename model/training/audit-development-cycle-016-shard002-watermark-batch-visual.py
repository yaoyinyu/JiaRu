#!/usr/bin/env python3
"""Bind five logo reviews and source32 variant stop-loss decisions."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ORDINALS = [25, 27, 30, 32, 40]
NAMES = ("original", "remove", "occlude", "blur", "move_position")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bind(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha(path)}


def checked(item: dict) -> None:
    path = Path(item["path"])
    if not path.is_file() or sha(path) != item["sha256"]:
        raise ValueError(f"bound file drift: {path}")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def check_report_bindings(document: dict) -> None:
    for binding in document["inputs"].values():
        checked(binding)
    for key in ("variants", "cornerCrops"):
        for binding in document.get(key, {}).values():
            checked(binding)
    for key in ("logoMask", "movedTargetCrop"):
        if key in document:
            checked(document[key])


def build(preflight_path: Path, decision_path: Path,
          variant_paths: list[Path], crop_paths: list[Path]) -> dict:
    preflight, decisions = load(preflight_path), load(decision_path)
    if (preflight.get("decision") !=
            "five_rework_sources_logo_windows_bound_visual_review_pending" or
            preflight["counts"]["sourceImages"] != 5 or
            preflight["counts"]["oldLabelNails"] != 25 or
            preflight["counts"]["distinctSourceGroups"] != 4 or
            preflight["counts"]["historicalCanonicalRecords"] != 1 or
            preflight["counts"]["newTrainingApprovedSources"] != 0 or
            decisions["decision"] != "five_logos_confirmed_source032_v3_variants_visual_only" or
            decisions["visibleLogoOrdinals"] != ORDINALS or
            decisions["source32OldMaskVisualApproval"] or
            decisions["source32WatermarkShortcutAbsenceProven"] or
            decisions["trainingUse"] != "prohibited"):
        raise ValueError("five-source visual/role contract mismatch")
    check_report_bindings(preflight)
    for row in preflight["sources"]:
        for key in ("sourceImage", "sourceLabel", "isolatedSourceImage", "logoCrop"):
            checked(row[key])
    source32 = next(row for row in preflight["sources"] if row["ordinal"] == 32)
    source40 = next(row for row in preflight["sources"] if row["ordinal"] == 40)
    if (source32["sameGroupVisualPassOrdinals"] or source40["sameGroupVisualPassOrdinals"] or
            source32["historicalCanonicalCount"] != 1 or
            source32["minimumOldMaskDistancePixels"] < 400 or
            source40["minimumOldMaskDistancePixels"] >= 100 or
            source32["overlappingOldMaskIndices"] or
            any(row["trainingUse"] != "prohibited" for row in preflight["sources"])):
        raise ValueError("source32 priority/old-mask diagnostic drift")
    if len(variant_paths) != 3 or len(crop_paths) != 3:
        raise ValueError("three variant/crop versions required")
    variants, crops = [], []
    for version, (variant_path, crop_path) in enumerate(zip(variant_paths, crop_paths), 1):
        variant, crop = load(variant_path), load(crop_path)
        if (variant_path.parent.name != f"cycle016-shard002-source032-watermark-v{version}" or
                crop_path.parent != variant_path.parent or
                variant.get("decision") !=
                "source032_four_logo_variants_built_visual_and_model_ablation_pending" or
                variant["sourceOrdinal"] != 32 or variant["nailPixelsChanged"] != 0 or
                variant["modelAblationComplete"] or variant["shortcutAbsenceProven"] or
                variant["trainingUse"] != "prohibited" or
                variant["inputs"]["batchPreflight"]["sha256"] != sha(preflight_path) or
                crop.get("decision") !=
                "source032_variant_review_crops_bound_visual_decision_pending" or
                crop["sourceOrdinal"] != 32 or crop["shortcutAbsenceProven"] or
                crop["trainingUse"] != "prohibited" or
                crop["inputs"]["variantReport"]["sha256"] != sha(variant_path) or
                set(variant["variants"]) != set(NAMES) or
                set(crop["cornerCrops"]) != set(NAMES)):
            raise ValueError(f"source32 v{version} variant/crop mismatch")
        check_report_bindings(variant)
        check_report_bindings(crop)
        variants.append(variant)
        crops.append(crop)
    if any(variants[version]["variants"][name]["sha256"] !=
           variants[0]["variants"][name]["sha256"]
           for version in (1, 2) for name in NAMES[:-1]):
        raise ValueError("unchanged four source32 variants drifted between revisions")
    review = decisions["source32VariantVersions"]
    if ([item["version"] for item in review] != [1, 2, 3] or
            [item["decision"] for item in review] !=
            ["reject_move_position", "reject_move_position",
             "visual_variant_quality_pass_model_ablation_pending"] or
            any(not item["reason"] for item in review)):
        raise ValueError("missing variant visual stop-loss decisions")
    return {
        "schemaVersion": 1, "ok": True,
        "decision": "five_logos_verified_source032_v3_visual_variants_only_model_and_masks_pending",
        "inputs": {"sourceScript": bind(Path(__file__)), "batchPreflight": bind(preflight_path),
                   "visualDecisions": bind(decision_path),
                   "variantReports": [bind(path) for path in variant_paths],
                   "reviewCropReports": [bind(path) for path in crop_paths]},
        "visibleLogoOrdinals": ORDINALS,
        "source32VariantVisualDecisions": review,
        "source32Priority": {"historicalCanonicalCount": 1,
                             "sameGroupVisualPassSources": 0,
                             "minimumOldMaskDistancePixels":
                             source32["minimumOldMaskDistancePixels"],
                             "oldMaskVisualApproval": False},
        "counts": {"sourceImages": 5, "oldLabelNails": 25,
                   "logoVisualConfirmations": 5,
                   "source32RejectedMoveVersions": 2,
                   "source32VisualVariantSetsPassing": 1,
                   "newTrainingApprovedSources": 0},
        "source32ModelAblationComplete": False,
        "source32ShortcutAbsenceProven": False,
        "fullShardCleanTruthComplete": False,
        "trainingUse": "prohibited",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", type=Path)
    parser.add_argument("--decisions", type=Path)
    parser.add_argument("--variants", nargs=3, type=Path)
    parser.add_argument("--crops", nargs=3, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        prior = load(args.verify_report)
        for binding in prior["inputs"].values():
            if isinstance(binding, list):
                for item in binding:
                    checked(item)
            else:
                checked(binding)
        current = build(Path(prior["inputs"]["batchPreflight"]["path"]),
                        Path(prior["inputs"]["visualDecisions"]["path"]),
                        [Path(item["path"]) for item in prior["inputs"]["variantReports"]],
                        [Path(item["path"]) for item in prior["inputs"]["reviewCropReports"]])
        if current != prior:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"],
                          "counts": current["counts"]}))
        return
    if not all((args.preflight, args.decisions, args.variants, args.crops, args.output)):
        parser.error("all inputs and --output required")
    if args.output.exists():
        raise FileExistsError(args.output)
    report = build(args.preflight.resolve(), args.decisions.resolve(),
                   [path.resolve() for path in args.variants],
                   [path.resolve() for path in args.crops])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"],
                      "counts": report["counts"]}))


if __name__ == "__main__":
    main()
