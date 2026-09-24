#!/usr/bin/env python3
"""Reconstruct shard-001 disposition after source repairs and watermark probe."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bind(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha(path)}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build(disposition_path: Path, repair_path: Path, variant_path: Path,
          probe_path: Path, *, script_path: Path) -> dict:
    disposition, repair, variant, probe = map(load, (disposition_path, repair_path,
                                                     variant_path, probe_path))
    rows = disposition["sourceDispositions"]
    if not disposition["evidenceOk"] or len(rows) != 20 or sum(r["oldLabelNails"] for r in rows) != 116:
        raise ValueError("original shard reconstruction mismatch")
    if not repair["ok"] or not repair["fullShardMaskReviewComplete"] or repair["counts"]["repairedSources"] != 2 or repair["counts"]["repairedNails"] != 10:
        raise ValueError("repair gate mismatch")
    if variant["nailPixelsChanged"] != 0 or variant["sourceOrdinal"] != 7 or not probe["ok"]:
        raise ValueError("watermark probe gate mismatch")
    if probe["inputs"]["variantBuild"]["sha256"] != sha(variant_path):
        raise ValueError("variant binding mismatch")
    if probe["variantPredictions"]["original"]["instanceCount"] != 7:
        raise ValueError("original prediction count drift")
    for name in ("remove", "occlude", "blur", "move_position"):
        if probe["variantPredictions"][name]["instanceCount"] != 6 or probe["comparisonsToOriginal"][name]["instanceCountDelta"] != -1:
            raise ValueError(f"watermark sensitivity drift: {name}")
    drop_box = probe["variantPredictions"]["original"]["boxesXyxy"][6]
    x1, y1, x2, y2 = drop_box
    if not (350 < x1 < 400 and 430 < y1 < 460 and 500 < x2 < 530 and 520 < y2 < 550):
        raise ValueError("watermark-adjacent original box drift")
    ordinal_sets = {
        "oldVisualPass": {r["ordinal"] for r in rows if r["disposition"] == "visual_polygon_pass_pending_full_split"},
        "oldSourceExcluded": {r["ordinal"] for r in rows if r["disposition"] == "source_exclude"},
        "repaired": {r["ordinal"] for r in rows if r["disposition"] == "label_rework"},
    }
    if ordinal_sets["repaired"] != {8, 18} or 7 not in ordinal_sets["oldVisualPass"]:
        raise ValueError("shard role drift")
    provisional = (ordinal_sets["oldVisualPass"] | ordinal_sets["repaired"]) - {7}
    if len(provisional) != 9 or len(ordinal_sets["oldSourceExcluded"]) != 10:
        raise ValueError("clean source count drift")
    nails = sum(r["oldLabelNails"] for r in rows if r["ordinal"] in provisional)
    if nails != 49:
        raise ValueError("clean nail count drift")
    return {
        "schemaVersion": 1, "ok": True,
        "decision": "source7_watermark_sensitive_quarantined_nine_sources_pending_full_split",
        "inputs": {"sourceScript": bind(script_path), "priorDisposition": bind(disposition_path),
                   "repairVisual": bind(repair_path), "variantBuild": bind(variant_path),
                   "modelProbe": bind(probe_path)},
        "counts": {"originalShardSources": 20, "originalOldLabelNails": 116,
                   "visualMaskPassSourcesBeforeWatermarkGate": 10,
                   "visualMaskPassNailsBeforeWatermarkGate": 54,
                   "sourceExcludedForImageOrMask": 10,
                   "watermarkQuarantinedSources": 1,
                   "provisionalCleanSources": 9, "provisionalCleanNails": 49,
                   "newTrainingApprovedSources": 0},
        "watermarkFinding": {
            "sourceOrdinal": 7,
            "originalPredictionCount": 7, "variantPredictionCounts": {name: 6 for name in ("remove", "occlude", "blur", "move_position")},
            "disappearingOriginalBoxXyxy": drop_box,
            "interpretation": "One watermark-adjacent false positive disappears in every altered-background arm; this is diagnostic sensitivity, not proof of causal watermark reliance or a future-model pass.",
            "newTrainDisposition": "quarantine_source_until_independent_shortcut_exclusion_or_remove_from_new_train",
        },
        "provisionalCleanOrdinals": sorted(provisional),
        "sourceExcludedOrdinals": sorted(ordinal_sets["oldSourceExcluded"]),
        "watermarkQuarantineOrdinals": [7],
        "fullTrainSplitApproved": False, "trainingUse": "prohibited",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("disposition", "repair", "variant", "probe", "report", "verify-report"):
        parser.add_argument("--" + name, type=Path)
    args = parser.parse_args()
    if args.verify_report:
        old = load(args.verify_report)
        for item in old["inputs"].values():
            if sha(Path(item["path"])) != item["sha256"]:
                raise ValueError("bound input drift")
        inputs = old["inputs"]
        current = build(*(Path(inputs[key]["path"]) for key in ("priorDisposition", "repairVisual", "variantBuild", "modelProbe")),
                        script_path=Path(inputs["sourceScript"]["path"]))
        if current != old:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"], "counts": current["counts"]}))
        return
    if not all((args.disposition, args.repair, args.variant, args.probe, args.report)):
        parser.error("all input reports and --report required")
    if args.report.exists():
        raise FileExistsError(args.report)
    report = build(args.disposition.resolve(), args.repair.resolve(), args.variant.resolve(),
                   args.probe.resolve(), script_path=Path(__file__).resolve())
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"], "counts": report["counts"]}))


if __name__ == "__main__":
    main()
