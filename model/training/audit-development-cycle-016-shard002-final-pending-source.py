#!/usr/bin/env python3
"""Replay one original-resolution decision for a pending shard-002 train source."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from shapely.geometry import Polygon


PASS_WITH_WATERMARK = "mask_visual_pass_pending_watermark_and_full_split"
PASS_CLEAN = "mask_visual_pass_pending_full_split"
REWORK = "confirmed_label_rework"
EXCLUDE = "confirmed_source_exclude"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for part in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


def bind(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha(path)}


def checked(binding: dict) -> None:
    path = Path(binding["path"])
    if not path.is_file() or sha(path) != binding["sha256"]:
        raise ValueError(f"bound file drift: {path}")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def geometry(label_path: Path) -> tuple[int, int]:
    polygons = []
    for line in label_path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) < 7 or parts[0] != "0" or (len(parts) - 1) % 2:
            raise ValueError("unexpected label format")
        values = [float(value) for value in parts[1:]]
        if any(value < 0 or value > 1 for value in values):
            raise ValueError("polygon coordinate out of range")
        polygon = Polygon(list(zip(values[::2], values[1::2])))
        if not polygon.is_valid or polygon.area <= 1e-6:
            raise ValueError("invalid polygon")
        polygons.append(polygon)
    overlap_pairs = sum(polygons[i].intersection(polygons[j]).area > 1e-10
                        for i in range(len(polygons)) for j in range(i + 1, len(polygons)))
    return len(polygons), overlap_pairs


def build(shard_path: Path, prior_path: Path, decision_path: Path) -> dict:
    shard, prior, manual = map(load, (shard_path, prior_path, decision_path))
    if not shard["ok"] or shard["shard"]["shard"] != 2 or not prior["ok"]:
        raise ValueError("shard/prior contract mismatch")
    if prior["counts"]["sourceImages"] != 20 or prior["counts"]["oldLabelNails"] != 104:
        raise ValueError("prior denominator drift")
    ordinal = manual["sourceOrdinal"]
    source = next((item for item in shard["sourceImages"] if item["ordinal"] == ordinal), None)
    earlier = next((item for item in prior["sourceDispositions"] if item["ordinal"] == ordinal), None)
    if source is None or earlier is None or earlier["decision"] != "pending_every_nail_review":
        raise ValueError("source is not pending")
    if manual["sourceFileName"] != source["sourceFileName"] or source["sourceGroup"] != earlier["sourceGroup"]:
        raise ValueError("source identity mismatch")
    if source["sourceImage"] != earlier["sourceImage"] or source["sourceLabel"] != earlier["sourceLabel"]:
        raise ValueError("source/label binding mismatch")
    if prior["inputs"]["priorProgressV1"]["sha256"] != sha(Path(prior["inputs"]["priorProgressV1"]["path"])):
        raise ValueError("prior chain drift")
    for binding in (source["sourceImage"], source["sourceLabel"], source["overview"]):
        checked(binding)
    for nail in source["nails"]:
        checked(nail["nativeOverlay"])
    if not manual.get("reason") or manual["trainingUse"] != "prohibited":
        raise ValueError("manual decision incomplete")
    count, overlaps = geometry(Path(source["sourceLabel"]["path"]))
    if count != len(source["nails"]) or count != earlier["oldLabelNails"]:
        raise ValueError("label count mismatch")
    decision = manual["decision"]
    if decision in (PASS_CLEAN, PASS_WITH_WATERMARK):
        if not manual["everyNailVisualApproval"] or manual["visibleNailCount"] != count:
            raise ValueError("full visual review not recorded")
        if sorted(nail["truthIndex"] for nail in manual["nails"]) != list(range(1, count + 1)):
            raise ValueError("missing nail review")
        if any(nail["decision"] != "pass_original_resolution" or not nail["reason"]
               for nail in manual["nails"]):
            raise ValueError("unreviewed nail")
        if any(manual[key] != 0 for key in
               ("missingNails", "duplicateMasks", "croppedNails", "maskContaminations")):
            raise ValueError("visual failure cannot pass")
        if overlaps != 0 or manual["watermarkReviewRequired"] != (decision == PASS_WITH_WATERMARK):
            raise ValueError("geometry or watermark contract mismatch")
        focus = list(range(1, count + 1))
        visual_pass = count
    elif decision in (REWORK, EXCLUDE):
        focus = manual["focusTruthIndices"]
        if not focus or len(set(focus)) != len(focus) or any(index < 1 or index > count for index in focus):
            raise ValueError("missing or invalid focus")
        if manual["everyNailVisualApproval"]:
            raise ValueError("failed source cannot approve masks")
        if decision == EXCLUDE and manual.get("sourceQualityFailure") != "required_nail_not_fully_visible":
            raise ValueError("source exclusion lacks hard-gate reason")
        visual_pass = 0
    else:
        raise ValueError("unknown decision")
    return {"schemaVersion": 1, "ok": True, "decision": decision,
            "inputs": {"sourceScript": bind(Path(__file__)), "shardReport": bind(shard_path),
                       "priorProgressV2": bind(prior_path), "visualDecisions": bind(decision_path)},
            "sourceOrdinal": ordinal, "sourceFileName": source["sourceFileName"],
            "sourceGroup": source["sourceGroup"], "sourceImage": source["sourceImage"],
            "sourceLabel": source["sourceLabel"], "priorDecision": earlier["decision"],
            "humanDecision": manual,
            "geometry": {"legalPolygons": count, "overlapPairs": overlaps},
            "focusOverlays": [{"truthIndex": index,
                               "nativeOverlay": source["nails"][index - 1]["nativeOverlay"]}
                              for index in focus],
            "counts": {"visualPassNails": visual_pass, "newTrainingApprovedSources": 0},
            "fullTrainSplitApproved": False, "trainingUse": "prohibited"}


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("shard-report", "prior-progress", "visual-decisions", "output", "verify-report"):
        parser.add_argument("--" + name, type=Path)
    args = parser.parse_args()
    if args.verify_report:
        old = load(args.verify_report)
        for binding in old["inputs"].values():
            checked(binding)
        inputs = old["inputs"]
        current = build(Path(inputs["shardReport"]["path"]),
                        Path(inputs["priorProgressV2"]["path"]),
                        Path(inputs["visualDecisions"]["path"]))
        if current != old:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"],
                          "sourceOrdinal": current["sourceOrdinal"], "counts": current["counts"]}))
        return
    if not all((args.shard_report, args.prior_progress, args.visual_decisions, args.output)):
        parser.error("all inputs and --output required")
    if args.output.exists():
        raise FileExistsError(args.output)
    report = build(args.shard_report.resolve(), args.prior_progress.resolve(), args.visual_decisions.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"],
                      "sourceOrdinal": report["sourceOrdinal"], "counts": report["counts"]}))


if __name__ == "__main__":
    main()
