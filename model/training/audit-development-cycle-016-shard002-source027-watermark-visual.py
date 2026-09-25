#!/usr/bin/env python3
"""Replay visual usability of source27 watermark variants without training promotion."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


NAMES = ("original", "remove", "occlude", "blur", "move_position")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bind(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha(path)}


def checked(binding: dict) -> None:
    path = Path(binding["path"])
    if not path.is_file() or sha(path) != binding["sha256"]:
        raise ValueError(f"bound file drift: {path}")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build(variant_path: Path, decision_path: Path, mask_visual_path: Path) -> dict:
    variants, decisions, mask_visual = map(load, (variant_path,
                                                  decision_path, mask_visual_path))
    if (variants["decision"] !=
            "source027_four_logo_variants_built_visual_and_model_ablation_pending" or
            variants["sourceOrdinal"] != 27 or
            variants["nailPixelsChanged"] != 0 or
            variants["logoMaskPixels"] != 960 or
            variants["maskVisualApproval"] is not True or
            variants["variantVisualApproval"] or
            variants["modelAblationComplete"] or
            variants["shortcutAbsenceProven"] or
            variants["trainingUse"] != "prohibited" or
            tuple(variants["variants"]) != NAMES or
            tuple(variants["logoCrops"]) != NAMES or
            tuple(variants["movedCrops"]) != NAMES or
            mask_visual["source27"]["decision"] !=
            "repaired_mask_visual_pass_pending_watermark_and_full_split" or
            mask_visual["source27"]["sourceFileName"] != variants["sourceFileName"] or
            mask_visual["source27"]["sourceGroup"] != variants["sourceGroup"] or
            variants["inputs"]["source025027VisualAudit"]["sha256"] != sha(mask_visual_path)):
        raise ValueError("source27 variant/visual contract mismatch")
    for binding in variants["inputs"].values():
        checked(binding)
    checked(variants["logoMask"])
    for key in ("variants", "logoCrops", "movedCrops"):
        for binding in variants[key].values():
            checked(binding)
    if (decisions["schemaVersion"] != 1 or
            decisions["reviewer"] != "Codex" or
            decisions["reviewDate"] != "2026-09-24" or
            decisions["sourceOrdinal"] != 27 or
            decisions["decision"] !=
            "source027_logo_four_variants_visual_usable_model_ablation_pending" or
            any(decisions[key] is not True for key in
                ("originalLogoVisible", "removeLogoUnreadable",
                 "occludeLogoUnreadable", "blurLogoUnreadable",
                 "moveOriginalPositionUnreadable", "moveTargetLogoVisible")) or
            decisions["moveRectangularArtifact"] or
            not decisions["reason"] or
            decisions["modelAblationComplete"] or
            decisions["shortcutAbsenceProven"] or
            decisions["trainingUse"] != "prohibited"):
        raise ValueError("source27 variant human review incomplete")
    return {"schemaVersion": 1, "ok": True,
            "decision": "source027_logo_variants_visual_usable_model_ablation_and_split_hold",
            "inputs": {"sourceScript": bind(Path(__file__)),
                       "variantReport": bind(variant_path),
                       "visualDecisions": bind(decision_path),
                       "maskVisualAudit": bind(mask_visual_path)},
            "sourceOrdinal": 27,
            "sourceFileName": variants["sourceFileName"],
            "sourceGroup": variants["sourceGroup"],
            "logoMarkType": "xiaohongshu_corner_logo",
            "variantNames": list(NAMES),
            "visualVariantCount": 4,
            "nailPixelsChanged": 0,
            "modelAblationComplete": False,
            "shortcutAbsenceProven": False,
            "newTrainingApprovedSources": 0,
            "trainingUse": "prohibited"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variants", type=Path)
    parser.add_argument("--decisions", type=Path)
    parser.add_argument("--mask-visual", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        previous = load(args.verify_report)
        for binding in previous["inputs"].values():
            checked(binding)
        inputs = previous["inputs"]
        current = build(Path(inputs["variantReport"]["path"]),
                        Path(inputs["visualDecisions"]["path"]),
                        Path(inputs["maskVisualAudit"]["path"]))
        if current != previous:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"]}))
        return
    if not all((args.variants, args.decisions, args.mask_visual, args.output)):
        parser.error("all inputs and --output required")
    if args.output.exists():
        raise FileExistsError(args.output)
    report = build(args.variants.resolve(), args.decisions.resolve(),
                   args.mask_visual.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"]}))


if __name__ == "__main__":
    main()
