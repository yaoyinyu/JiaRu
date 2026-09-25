#!/usr/bin/env python3
"""Bind source-59 original-pixel five-nail review and earlier candidate failures."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


REASONS = {
    1: "Manual contour includes the nude proximal bed and complete gold-covered distal nail; v1 old contour only covered foil.",
    2: "Retained old contour covers the complete clear-to-nude extension to the cuticle without adjacent skin.",
    3: "Retained old contour covers the gold-covered tip and visible nude proximal bed; protruding foil outside the nail silhouette is excluded.",
    4: "Manual contour removes the dark non-nail wedge above the old upper edge and restores the small clear distal tip missed by v2.",
    5: "Retained old contour follows the complete nude thumb surface and distal transparent edge without fur or skin.",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked(item: dict) -> Path:
    path = Path(item["path"])
    if not path.is_file() or sha(path) != item["sha256"]:
        raise ValueError(f"bound file drift: {path}")
    return path


def bind(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha(path)}


def build(v1_path: Path, v2_path: Path, v3_path: Path) -> dict:
    v1, v2, v3 = [json.loads(path.read_text(encoding="utf-8"))
                  for path in (v1_path, v2_path, v3_path)]
    for document in (v1, v2, v3):
        if (document["decision"] != "source059_five_nail_candidate_geometry_pass_visual_pending" or
                document["counts"] != {"sourceImages": 1, "nails": 5, "legalPolygons": 5,
                                       "overlapPairs": 0, "visualApprovals": 0,
                                       "trainingApproved": 0}):
            raise ValueError("candidate geometry state drift")
        for item in document["inputs"].values():
            checked(item)
        source = document["source"]
        if source["ordinal"] != 59 or len(source["nails"]) != 5:
            raise ValueError("candidate source count drift")
        for key in ("sourceImage", "sourceLabel", "isolatedImage", "candidateAnnotation", "fullOutline"):
            checked(source[key])
        for nail in source["nails"]:
            checked(nail["raw3x"])
            checked(nail["outline3x"])
    if any(doc["source"]["sourceImage"] != v3["source"]["sourceImage"] or
           doc["source"]["sourceGroup"] != v3["source"]["sourceGroup"]
           for doc in (v1, v2)):
        raise ValueError("candidate identity drift")
    source = v3["source"]
    if [nail["method"] for nail in source["nails"]] != [
        "manual_original_resolution", "retained_old", "retained_old",
        "manual_original_resolution", "retained_old"
    ]:
        raise ValueError("final hybrid methods drift")
    if source["historicalCanonicalTruthCount"] != 0 or source["trainingUse"] != "prohibited":
        raise ValueError("canonical identity or training role drift")
    return {
        "schemaVersion": 1, "ok": True,
        "decision": "source059_five_complete_masks_visual_pass_training_prohibited",
        "inputs": {"sourceScript": bind(Path(__file__)), "candidateV1": bind(v1_path),
                   "candidateV2": bind(v2_path), "candidateV3": bind(v3_path)},
        "rejectedCandidates": [
            {"candidateReport": bind(v1_path), "reason": "Nail 4 old outline includes a dark non-nail wedge above its upper border."},
            {"candidateReport": bind(v2_path), "reason": "Nail 4 first manual outline removes the wedge but misses its small transparent distal tip."},
        ],
        "source": {
            "ordinal": 59, "sourceFileName": source["sourceFileName"],
            "sourceGroup": source["sourceGroup"], "sourceImage": source["sourceImage"],
            "sourceLabel": source["sourceLabel"],
            "candidateAnnotation": source["candidateAnnotation"],
            "fullOutline": source["fullOutline"],
            "nails": [
                {"truthIndex": nail["truthIndex"], "method": nail["method"],
                 "decision": "pass_original_resolution_complete_surface",
                 "reason": REASONS[nail["truthIndex"]],
                 "raw3x": nail["raw3x"], "outline3x": nail["outline3x"]}
                for nail in source["nails"]
            ],
            "visibleSourceMarkerDecision": "none_observed_on_full_original_image",
            "historicalCanonicalTruthCount": 0,
            "historicalCycle012TrainIdentity": True,
            "trainingUse": "prohibited",
        },
        "counts": {"sourceImages": 1, "nails": 5,
                   "maskVisualPassImages": 1, "maskVisualPassNails": 5,
                   "trainingApproved": 0},
        "limitations": [
            "Visual review is human judgment on bound original pixels; deterministic replay verifies identity, not visual correctness.",
            "This source is already present in the historical cycle012 train snapshot and is not a new training image.",
            "No visible text/logo in this image does not close other sources' watermark shortcut ablations or full-split role checks.",
        ],
        "trainingUse": "prohibited",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-v1", type=Path)
    parser.add_argument("--candidate-v2", type=Path)
    parser.add_argument("--candidate-v3", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        saved = json.loads(args.verify_report.read_text(encoding="utf-8"))
        for item in saved["inputs"].values():
            checked(item)
        current = build(*(Path(saved["inputs"][key]["path"]) for key in
                          ("candidateV1", "candidateV2", "candidateV3")))
        if current != saved:
            raise SystemExit("reconstruction_mismatch")
        result = {"ok": True, "decision": "verified_source059_visual_adjudication",
                  "counts": saved["counts"]}
    else:
        if not all((args.candidate_v1, args.candidate_v2, args.candidate_v3, args.report)):
            parser.error("all three candidates and --report required")
        if args.report.exists():
            raise FileExistsError(args.report)
        result = build(args.candidate_v1.resolve(), args.candidate_v2.resolve(),
                       args.candidate_v3.resolve())
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("ok", "decision", "counts")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
