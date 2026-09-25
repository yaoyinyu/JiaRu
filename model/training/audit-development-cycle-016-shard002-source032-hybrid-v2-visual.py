#!/usr/bin/env python3
"""Bind source32 five-nail original-resolution visual approval, without train promotion."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from shapely.geometry import Polygon, box


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


def build(candidate_path: Path, preflight_path: Path, decisions_path: Path) -> dict:
    candidate, preflight, decisions = map(load, (candidate_path, preflight_path,
                                                decisions_path))
    row = next(item for item in preflight["sources"] if item["ordinal"] == 32)
    if (candidate["decision"] != "source032_hybrid_v2_geometry_pass_visual_pending" or
            candidate["counts"]["manualPolygonsTotal"] != 4 or
            candidate["counts"]["retainedDirectedSamPolygons"] != 1 or
            candidate["counts"]["legalPolygons"] != 5 or
            candidate["counts"]["overlapPairs"] != 0 or
            candidate["counts"]["manualPositiveInside"] != 12 or
            candidate["counts"]["manualNegativeOutside"] != 12 or
            candidate["trainingUse"] != "prohibited" or
            row["oldMaskQuality"] != "confirmed_label_rework" or
            row["historicalCanonicalCount"] != 1 or
            decisions["decision"] !=
            "source032_five_complete_nail_masks_visual_pass_watermark_pending" or
            decisions["sourceOrdinal"] != 32 or
            not decisions["fullOriginalImageReviewed"] or
            not decisions["allFiveVisibleNailsCounted"] or
            not decisions["logoBoxOutsideAllMasks"] or
            decisions["watermarkShortcutAbsenceProven"] or
            decisions["fullTrainSplitApproved"] or
            decisions["newTrainingApprovedSources"] != 0 or
            decisions["trainingUse"] != "prohibited"):
        raise ValueError("source32 visual/role contract mismatch")
    if ([item["nailIndex"] for item in decisions["nails"]] != [1, 2, 3, 4, 5] or
            any(item["decision"] != "pass_complete_nail" or not item["reason"]
                for item in decisions["nails"])):
        raise ValueError("source32 five-nail visual coverage mismatch")
    for item in candidate["inputs"].values():
        if isinstance(item, list):
            for binding in item:
                checked(binding)
        else:
            checked(item)
    for key in ("sourceImage", "sourceLabel", "isolatedSourceImage", "logoCrop"):
        checked(row[key])
    annotation = load(Path(candidate["inputs"]["candidateAnnotation"]["path"]))
    polygons = [Polygon([(p["x"], p["y"]) for p in nail["polygon"]])
                for nail in annotation["annotations"]]
    mark = box(*row["markBoxPixels"])
    if (len(polygons) != 5 or
            any(not shape.is_valid or shape.area <= 1 or shape.intersects(mark)
                for shape in polygons) or
            any(polygons[i].intersection(polygons[j]).area > 0
                for i in range(5) for j in range(i + 1, 5))):
        raise ValueError("source32 visual polygon/watermark geometry failure")
    if (annotation["image"]["fileName"] != row["sourceFileName"] or
            annotation["image"]["sourceGroup"] != row["sourceGroup"] or
            annotation["trainingUse"] != "prohibited"):
        raise ValueError("source32 visual source identity mismatch")
    return {"schemaVersion": 1, "ok": True,
            "decision": "source032_repaired_five_masks_visual_pass_watermark_and_full_split_pending",
            "inputs": {"sourceScript": bind(Path(__file__)),
                       "hybridCandidateAudit": bind(candidate_path),
                       "batchPreflight": bind(preflight_path),
                       "visualDecisions": bind(decisions_path),
                       "sourceImage": row["sourceImage"],
                       "oldLabel": row["sourceLabel"],
                       "repairedAnnotation": candidate["inputs"]["candidateAnnotation"],
                       "fullOutline": candidate["inputs"]["fullOutline"],
                       "reviewCrops": candidate["inputs"]["reviewCrops"]},
            "sourceOrdinal": 32, "sourceFileName": row["sourceFileName"],
            "sourceGroup": row["sourceGroup"],
            "counts": {"fullyVisibleNails": 5, "visualPassNails": 5,
                       "legalPolygons": 5, "overlapPairs": 0,
                       "manualPolygons": 4, "retainedSamPolygons": 1,
                       "logoOverlapPolygons": 0,
                       "newTrainingApprovedSources": 0},
            "watermarkShortcutAbsenceProven": False,
            "fullTrainSplitApproved": False,
            "historicalSnapshotChanged": False,
            "trainingUse": "prohibited"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--preflight", type=Path)
    parser.add_argument("--decisions", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        prior = load(args.verify_report)
        for item in prior["inputs"].values():
            if isinstance(item, list):
                for binding in item:
                    checked(binding)
            else:
                checked(item)
        inputs = prior["inputs"]
        current = build(Path(inputs["hybridCandidateAudit"]["path"]),
                        Path(inputs["batchPreflight"]["path"]),
                        Path(inputs["visualDecisions"]["path"]))
        if current != prior:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"],
                          "counts": current["counts"]}))
        return
    if not all((args.candidate, args.preflight, args.decisions, args.output)):
        parser.error("all inputs and --output required")
    if args.output.exists():
        raise FileExistsError(args.output)
    report = build(args.candidate.resolve(), args.preflight.resolve(),
                   args.decisions.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"],
                      "counts": report["counts"]}))


if __name__ == "__main__":
    main()
