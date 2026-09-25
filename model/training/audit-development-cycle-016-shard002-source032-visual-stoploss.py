#!/usr/bin/env python3
"""Bind source32 original-pixel rejection and frozen-weight diagnostic limits."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


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


def build(canonical_path: Path, old_outline_path: Path,
          sam_path: Path, model_path: Path, decisions_path: Path) -> dict:
    canonical, old, sam, model, decisions = map(
        load, (canonical_path, old_outline_path, sam_path, model_path, decisions_path))
    if (canonical["decision"] != "historical_approved_truth_is_same_defective_cycle012_polygon" or
            canonical["sourceOrdinal"] != 32 or canonical["trainingUse"] != "prohibited" or
            old["decision"] != "source032_frozen_old_polygon_original_resolution_reassessment_pending" or
            old["counts"] != {"polygons": 5, "legalPolygons": 5,
                              "overlapPairs": 0, "visualApproved": 0,
                              "newTrainingApprovedSources": 0} or
            sam["decision"] != "source032_sam_geometry_pass_original_resolution_visual_pending" or
            sam["counts"]["legalPolygons"] != 5 or
            sam["counts"]["overlapPairs"] != 0 or
            sam["counts"]["visualApproved"] != 0 or
            model["decision"] != "source032_frozen_development_weight_watermark_probe_diagnostic_only" or
            model["contract"] != {"imgsz": 512, "conf": 0.25, "iou": 0.7,
                                  "device": "cpu", "retinaMasks": True,
                                  "oneInferencePerVariant": True} or
            model["independentWatermarkShortcutExclusionProven"] or
            decisions["decision"] != "source032_one_sam_pass_visual_rejected_manual_repair_required" or
            decisions["sourceOrdinal"] != 32 or
            decisions["oldPolygonVisualApproval"] or
            decisions["samCandidateVisualApproval"] or
            decisions["source32WatermarkShortcutAbsenceProven"] or
            decisions["newTrainingApprovedSources"] != 0 or
            decisions["trainingUse"] != "prohibited"):
        raise ValueError("source32 stop-loss contract mismatch")
    if (len(old["crops"]) != 5 or len(sam["crops"]) != 5 or
            [item["nailIndex"] for item in decisions["nails"]] != [1, 2, 3, 4, 5] or
            any(item["decision"] != "manual_rework" or not item["reason"]
                for item in decisions["nails"])):
        raise ValueError("five-nail visual decision mismatch")
    if (model["variantPredictions"]["original"]["instanceCount"] != 6 or
            any(item["instanceCount"] != 6
                for item in model["variantPredictions"].values()) or
            any(item["instanceCountDelta"] != 0 or
                item["originalUnionIoU"] < 0.9999
                for item in model["comparisonsToOriginal"].values())):
        raise ValueError("frozen model diagnostic differs from visual decision")
    for report in (canonical, old, sam, model):
        for item in report["inputs"].values():
            checked(item)
    for report in (old, sam):
        for crop in report["crops"]:
            for key in ("source", "old-outline" if report is old else "overlay"):
                checked(crop[key])
    return {"schemaVersion": 1, "ok": True,
            "decision": "source032_old_and_sam_masks_rejected_frozen_probe_diagnostic_only",
            "inputs": {"sourceScript": bind(Path(__file__)),
                       "canonicalIdentity": bind(canonical_path),
                       "oldOutline": bind(old_outline_path),
                       "samCandidateAudit": bind(sam_path),
                       "modelProbe": bind(model_path),
                       "visualDecisions": bind(decisions_path)},
            "counts": {"sourceImages": 1, "oldPolygons": 5,
                       "samPolygons": 5, "samGeometryPass": 5,
                       "oldMaskVisualPass": 0, "samMaskVisualPass": 0,
                       "manualReworkRequired": 5,
                       "modelOriginalCandidates": 6,
                       "modelVariantCandidatesEach": 6,
                       "newTrainingApprovedSources": 0},
            "source32ShortcutAbsenceProven": False,
            "oldHistoricalSnapshotChanged": False,
            "trainingUse": "prohibited"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical", type=Path)
    parser.add_argument("--old-outline", type=Path)
    parser.add_argument("--sam", type=Path)
    parser.add_argument("--model-probe", type=Path)
    parser.add_argument("--decisions", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        prior = load(args.verify_report)
        for item in prior["inputs"].values():
            checked(item)
        inputs = prior["inputs"]
        current = build(Path(inputs["canonicalIdentity"]["path"]),
                        Path(inputs["oldOutline"]["path"]),
                        Path(inputs["samCandidateAudit"]["path"]),
                        Path(inputs["modelProbe"]["path"]),
                        Path(inputs["visualDecisions"]["path"]))
        if current != prior:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"],
                          "counts": current["counts"]}))
        return
    if not all((args.canonical, args.old_outline, args.sam, args.model_probe,
                args.decisions, args.output)):
        parser.error("all inputs and --output required")
    if args.output.exists():
        raise FileExistsError(args.output)
    report = build(args.canonical.resolve(), args.old_outline.resolve(),
                   args.sam.resolve(), args.model_probe.resolve(),
                   args.decisions.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"],
                      "counts": report["counts"]}))


if __name__ == "__main__":
    main()
