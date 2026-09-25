#!/usr/bin/env python3
"""Replay source25 stop-loss and source27 five-nail visual decision."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from shapely.geometry import Polygon


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


def build(progress_path: Path, preflight_path: Path, old_path: Path,
          sam_path: Path, hybrid_path: Path, manual_path: Path) -> dict:
    progress, preflight, old, sam, hybrid, manual = map(
        load, (progress_path, preflight_path, old_path,
               sam_path, hybrid_path, manual_path))
    if (progress["schemaVersion"] != 10 or not progress["ok"] or
            progress["counts"]["sourceImages"] != 20 or
            progress["counts"]["oldLabelNails"] != 104 or
            progress["counts"]["sourceGroups"] != 8 or
            progress["counts"]["newTrainingApprovedSources"] != 0 or
            preflight["counts"]["sourceImages"] != 5 or
            old["decision"] !=
            "source025027_old_polygon_original_resolution_review_pending" or
            sam["decision"] != "source025027_sam_geometry_pass_visual_review_pending" or
            hybrid["decision"] !=
            "source027_five_nail_hybrid_candidate_visual_review_pending" or
            hybrid["counts"]["polygons"] != 5 or
            hybrid["counts"]["legalPolygons"] != 5 or
            hybrid["counts"]["overlapPairs"] != 0 or
            hybrid["counts"]["logoOverlapPairs"] != 0 or
            hybrid["counts"]["retainedOldPolygons"] != 3 or
            hybrid["counts"]["directedSamPolygons"] != 2 or
            manual["schemaVersion"] != 1 or
            manual["reviewer"] != "Codex" or
            manual["reviewDate"] != "2026-09-24"):
        raise ValueError("source25/27 visual input contract mismatch")
    for row in (progress, preflight, old, sam, hybrid):
        for binding in row["inputs"].values():
            checked(binding)
    for source in old["sources"]:
        checked(source["fullOutline"])
        checked(source["isolatedImage"])
        for crop in source["crops"]:
            checked(crop["source"])
            checked(crop["old-outline"])
    for source in sam["sources"]:
        checked(source["samAnnotation"])
        checked(source["fullOutline"])
        for nail in source["nails"]:
            checked(nail["source"])
            checked(nail["outline"])
    for key in ("annotation", "fullOutline"):
        checked(hybrid[key])
    for crop in hybrid["crops"]:
        checked(crop["source"])
        checked(crop["outline"])
    state25 = next(row for row in progress["sourceDispositions"] if row["ordinal"] == 25)
    state27 = next(row for row in progress["sourceDispositions"] if row["ordinal"] == 27)
    batch25 = next(row for row in preflight["sources"] if row["ordinal"] == 25)
    batch27 = next(row for row in preflight["sources"] if row["ordinal"] == 27)
    old25 = next(row for row in old["sources"] if row["ordinal"] == 25)
    old27 = next(row for row in old["sources"] if row["ordinal"] == 27)
    sam25 = next(row for row in sam["sources"] if row["ordinal"] == 25)
    sam27 = next(row for row in sam["sources"] if row["ordinal"] == 27)
    if (any(row["decision"] != "confirmed_label_rework" or
            row["oldLabelNails"] != 5 or row["everyNailVisualApproval"] or
            row["trainingUse"] != "prohibited" for row in (state25, state27)) or
            old25["sourceImage"] != state25["sourceImage"] or
            old27["sourceImage"] != state27["sourceImage"] or
            batch25["sameGroupVisualPassOrdinals"] != [21, 22, 23, 26] or
            batch25["sourceGroup"] != batch27["sourceGroup"] or
            batch25["historicalCanonicalCount"] != 0 or
            batch27["historicalCanonicalCount"] != 0 or
            old25["sourceGroup"] != batch25["sourceGroup"] or
            old27["sourceGroup"] != batch27["sourceGroup"] or
            hybrid["sourceFileName"] != batch27["sourceFileName"] or
            hybrid["sourceGroup"] != batch27["sourceGroup"] or
            sam25["sourceFileName"] != batch25["sourceFileName"] or
            sam27["sourceFileName"] != batch27["sourceFileName"]):
        raise ValueError("source25/27 frozen identity/role mismatch")
    label25 = Path(batch25["sourceLabel"]["path"]).read_text(encoding="utf-8").splitlines()
    values = [float(value) for value in label25[4].split()[1:]]
    width, height = old25["dimensions"]
    old_shape = Polygon([(x * width, y * height)
                         for x, y in zip(values[::2], values[1::2], strict=True)])
    sam25_annotation = load(Path(sam25["samAnnotation"]["path"]))
    new_shape = Polygon([(p["x"], p["y"])
                         for p in sam25_annotation["annotations"][0]["polygon"]])
    if not old_shape.is_valid or not new_shape.is_valid or not old_shape.union(new_shape).area:
        raise ValueError("source25 old/SAM polygon invalid")
    unchanged_iou = old_shape.intersection(new_shape).area / old_shape.union(new_shape).area
    if not 0.95 <= unchanged_iou < 1.0:
        raise ValueError("source25 SAM stop-loss measured overlap drift")
    stop = manual["source25"]
    if (stop["sourceOrdinal"] != 25 or
            stop["decision"] != "watermark_source_isolated_from_next_train_candidate" or
            stop["maskVisualApproval"] or stop["watermarkShortcutAbsenceProven"] or
            stop["trainingUse"] != "prohibited" or not stop["reason"]):
        raise ValueError("source25 stop-loss decision invalid")
    accept = manual["source27"]
    if (accept["sourceOrdinal"] != 27 or
            accept["decision"] !=
            "repaired_mask_visual_pass_pending_watermark_and_full_split" or
            accept["visibleNailCount"] != 5 or
            any(accept[key] != 0 for key in
                ("missingNails", "duplicateMasks", "croppedNails", "maskContaminations")) or
            [item["truthIndex"] for item in accept["nails"]] != [1, 2, 3, 4, 5] or
            any(item["decision"] != "pass_original_resolution" or not item["reason"]
                for item in accept["nails"]) or
            not accept["watermarkReviewRequired"] or
            accept["watermarkShortcutAbsenceProven"] or
            accept["fullTrainSplitApproved"] or
            accept["trainingUse"] != "prohibited"):
        raise ValueError("source27 visual decision incomplete")
    annotation = load(Path(hybrid["annotation"]["path"]))
    if (annotation["decision"] != "candidate_only_not_training_truth" or
            annotation["trainingUse"] != "prohibited" or
            len(annotation["annotations"]) != 5 or
            annotation["image"]["sourceImageSha256"] != batch27["sourceImage"]["sha256"]):
        raise ValueError("source27 hybrid annotation mismatch")
    old27_lines = Path(batch27["sourceLabel"]["path"]).read_text(encoding="utf-8").splitlines()
    sam27_annotations = load(Path(sam27["samAnnotation"]["path"]))["annotations"]
    for index, nail in enumerate(annotation["annotations"], start=1):
        if index in (1, 5):
            if nail["polygon"] != sam27_annotations[(1, 5).index(index)]["polygon"]:
                raise ValueError("source27 SAM polygon not preserved")
        else:
            values = [float(value) for value in old27_lines[index - 1].split()[1:]]
            expected = [{"x": x * 800, "y": y * 800}
                        for x, y in zip(values[::2], values[1::2], strict=True)]
            if nail["polygon"] != expected:
                raise ValueError("source27 retained old polygon changed")
    return {"schemaVersion": 1, "ok": True,
            "decision": "source025_isolated_source027_five_masks_visual_pass_watermark_and_split_hold",
            "inputs": {"sourceScript": bind(Path(__file__)),
                       "progressV10": bind(progress_path),
                       "batchPreflight": bind(preflight_path),
                       "oldOutline": bind(old_path),
                       "samCandidateAudit": bind(sam_path),
                       "source27Hybrid": bind(hybrid_path),
                       "visualDecisions": bind(manual_path),
                       "source25OldLabel": batch25["sourceLabel"],
                       "source25SamAnnotation": sam25["samAnnotation"],
                       "source27HybridAnnotation": hybrid["annotation"]},
            "source25": {"sourceOrdinal": 25,
                         "sourceFileName": batch25["sourceFileName"],
                         "sourceGroup": batch25["sourceGroup"],
                         "sourceImage": batch25["sourceImage"],
                         "oldLabel": batch25["sourceLabel"],
                         "decision": stop["decision"],
                         "oldVsSamNail5Iou": round(unchanged_iou, 8),
                         "sameGroupVisualPassOrdinals": batch25["sameGroupVisualPassOrdinals"],
                         "maskVisualApproval": False,
                         "watermarkShortcutAbsenceProven": False,
                         "trainingUse": "prohibited"},
            "source27": {"sourceOrdinal": 27,
                         "sourceFileName": batch27["sourceFileName"],
                         "sourceGroup": batch27["sourceGroup"],
                         "sourceImage": batch27["sourceImage"],
                         "oldLabel": batch27["sourceLabel"],
                         "hybridAnnotation": hybrid["annotation"],
                         "decision": accept["decision"],
                         "visualPassNails": 5,
                         "retainedOldPolygons": 3,
                         "directedSamPolygons": 2,
                         "legalPolygons": 5,
                         "overlapPairs": 0, "logoOverlapPairs": 0,
                         "watermarkShortcutAbsenceProven": False,
                         "fullTrainSplitApproved": False,
                         "trainingUse": "prohibited"},
            "newTrainingApprovedSources": 0,
            "historicalSnapshotChanged": False,
            "trainingUse": "prohibited"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--progress", type=Path)
    parser.add_argument("--preflight", type=Path)
    parser.add_argument("--old-outline", type=Path)
    parser.add_argument("--sam-audit", type=Path)
    parser.add_argument("--hybrid", type=Path)
    parser.add_argument("--visual-decisions", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        previous = load(args.verify_report)
        for binding in previous["inputs"].values():
            checked(binding)
        inputs = previous["inputs"]
        current = build(Path(inputs["progressV10"]["path"]),
                        Path(inputs["batchPreflight"]["path"]),
                        Path(inputs["oldOutline"]["path"]),
                        Path(inputs["samCandidateAudit"]["path"]),
                        Path(inputs["source27Hybrid"]["path"]),
                        Path(inputs["visualDecisions"]["path"]))
        if current != previous:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"]}))
        return
    if not all((args.progress, args.preflight, args.old_outline,
                args.sam_audit, args.hybrid, args.visual_decisions, args.output)):
        parser.error("all inputs/outputs required")
    if args.output.exists():
        raise FileExistsError(args.output)
    report = build(args.progress.resolve(), args.preflight.resolve(),
                   args.old_outline.resolve(), args.sam_audit.resolve(),
                   args.hybrid.resolve(), args.visual_decisions.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"]}))


if __name__ == "__main__":
    main()
