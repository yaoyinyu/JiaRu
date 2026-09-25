#!/usr/bin/env python3
"""Bind original-pixel nail-by-nail visual decisions without granting training use."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


DECISIONS = {
    47: {
        1: "Second SAM follows the complete nude bed, decoration, and clear tip; old upper-right spur removed.",
        2: "Retained old outline follows the complete nude bed and clear extension.",
        3: "Retained old outline follows the complete nude bed and clear extension.",
        4: "Manual outline follows the whole bed and clear tip without the old right-side zigzag or SAM skin bulge.",
        5: "First SAM follows the full nude bed and transparent tip, including the distal edge missed by old truth.",
    },
    53: {
        1: "Retained old outline follows the full green extension and nude proximal bed.",
        2: "Retained old outline follows the full clear extension and nude proximal bed.",
        3: "Second SAM follows the pale green tip and nude bed; dark protrusion outside the tip is background hair, not nail.",
        4: "Retained old outline follows the full thin green extension and nude proximal bed.",
        5: "Tight retry follows the green tip and full nude proximal bed without finger skin.",
    },
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked(binding: dict) -> Path:
    path = Path(binding["path"])
    if not path.is_file() or sha(path) != binding["sha256"]:
        raise ValueError(f"bound artifact drift: {path}")
    return path


def make(report_path: Path) -> dict:
    hybrid = json.loads(report_path.read_text(encoding="utf-8"))
    if hybrid["decision"] != "source047053_hybrid_candidates_geometry_pass_visual_pending":
        raise ValueError("hybrid decision drift")
    if hybrid["counts"] != {"sourceImages": 2, "nails": 10, "legalPolygons": 10,
                            "overlapPairs": 0, "visualApprovals": 0, "trainingApproved": 0}:
        raise ValueError("hybrid counts drift")
    rows = []
    for source in hybrid["sources"]:
        ordinal = source["ordinal"]
        if ordinal not in DECISIONS or len(source["nails"]) != 5:
            raise ValueError("source identity/count drift")
        for key in ("sourceImage", "sourceLabel", "isolatedImage", "candidateAnnotation", "fullOutline"):
            checked(source[key])
        if source["sourceImage"]["sha256"] != source["isolatedImage"]["sha256"]:
            raise ValueError("isolated image drift")
        nails = []
        for nail in source["nails"]:
            index = nail["truthIndex"]
            if index not in DECISIONS[ordinal] or nail["visualDecision"] != "pending_original_resolution_review":
                raise ValueError("nail index or state drift")
            checked(nail["raw3x"])
            checked(nail["outline3x"])
            nails.append({"truthIndex": index, "method": nail["method"],
                          "decision": "pass_original_resolution_complete_surface",
                          "reason": DECISIONS[ordinal][index],
                          "raw3x": nail["raw3x"], "outline3x": nail["outline3x"]})
        rows.append({"ordinal": ordinal, "sourceFileName": source["sourceFileName"],
                     "sourceGroup": source["sourceGroup"], "sourceImage": source["sourceImage"],
                     "candidateAnnotation": source["candidateAnnotation"],
                     "fullOutline": source["fullOutline"], "nails": nails,
                     "decision": "complete_five_nail_masks_visual_pass_training_prohibited",
                     "watermarkDebt": ordinal == 47, "trainingUse": "prohibited"})
    if [row["ordinal"] for row in rows] != [47, 53]:
        raise ValueError("source order drift")
    return {"schemaVersion": 1, "ok": True,
            "decision": "two_source_masks_visual_pass_training_still_prohibited",
            "inputs": {"sourceScript": {"path": str(Path(__file__).resolve()), "sha256": sha(Path(__file__))},
                       "hybridReport": {"path": str(report_path.resolve()), "sha256": sha(report_path)}},
            "counts": {"sourceImages": 2, "nails": 10, "maskVisualPassImages": 2,
                       "maskVisualPassNails": 10, "trainingApproved": 0},
            "sources": rows, "trainingUse": "prohibited",
            "limitations": ["Visual review binds original-resolution pixels; it is not a new source authorization or train split approval.",
                            "Source 47 has a right-bottom source watermark requiring a four-variant shortcut ablation or isolation.",
                            "Historical failures, protected roles, and original cycle012 labels are unchanged."]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hybrid-report", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        saved = json.loads(args.verify_report.read_text(encoding="utf-8"))
        checked(saved["inputs"]["sourceScript"])
        checked(saved["inputs"]["hybridReport"])
        current = make(Path(saved["inputs"]["hybridReport"]["path"]))
        if current != saved:
            raise SystemExit("reconstruction_mismatch")
        result = {"ok": True, "decision": "verified_source047053_visual_adjudication",
                  "counts": saved["counts"]}
    else:
        if not args.hybrid_report or not args.report:
            parser.error("--hybrid-report and --report required")
        if args.report.exists():
            raise FileExistsError(args.report)
        result = make(args.hybrid_report.resolve())
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("ok", "decision", "counts")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
