#!/usr/bin/env python3
"""Replay a focused original-resolution source decision in shard 002."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from shapely.geometry import Polygon


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for part in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


def bind(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha(path)}


def checked(item: dict) -> None:
    path = Path(item["path"])
    if not path.is_file() or sha(path) != item["sha256"]:
        raise ValueError(f"bound file drift: {path}")


def geometry(label_path: Path) -> tuple[int, int]:
    polygons = []
    for line in label_path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if parts[0] != "0" or len(parts) < 7 or (len(parts) - 1) % 2:
            raise ValueError("unexpected label format")
        values = [float(value) for value in parts[1:]]
        if any(value < 0 or value > 1 for value in values):
            raise ValueError("polygon coordinate out of range")
        polygon = Polygon(list(zip(values[::2], values[1::2])))
        if not polygon.is_valid or polygon.area <= 1e-6:
            raise ValueError("invalid polygon")
        polygons.append(polygon)
    overlaps = sum(polygons[i].intersection(polygons[j]).area > 1e-10
                   for i in range(len(polygons)) for j in range(i + 1, len(polygons)))
    return len(polygons), overlaps


def build(shard_path: Path, triage_path: Path, decisions_path: Path) -> dict:
    shard = json.loads(shard_path.read_text(encoding="utf-8"))
    triage = json.loads(triage_path.read_text(encoding="utf-8"))
    manual = json.loads(decisions_path.read_text(encoding="utf-8"))
    if not shard["ok"] or shard["shard"]["shard"] != 2 or not triage["evidenceOk"]:
        raise ValueError("shard or triage contract mismatch")
    if triage["inputs"]["shardReport"]["sha256"] != sha(shard_path):
        raise ValueError("triage does not bind shard")
    ordinal = manual["sourceOrdinal"]
    source = next((item for item in shard["sourceImages"] if item["ordinal"] == ordinal), None)
    earlier = next((item for item in triage["sourceTriage"] if item["ordinal"] == ordinal), None)
    if source is None or earlier is None or manual["sourceFileName"] != source["sourceFileName"]:
        raise ValueError("source identity mismatch")
    for key in ("sourceImage", "sourceLabel", "overview"):
        checked(source[key])
    for nail in source["nails"]:
        checked(nail["nativeOverlay"])
    if not manual.get("reason") or manual["trainingUse"] != "prohibited":
        raise ValueError("manual decision incomplete")
    count, overlap = geometry(Path(source["sourceLabel"]["path"]))
    if count != len(source["nails"]):
        raise ValueError("label count drift")
    decision = manual["decision"]
    if decision == "confirmed_label_rework":
        focus = manual["focusTruthIndices"]
        if not focus or any(index < 1 or index > count for index in focus):
            raise ValueError("missing rework focus")
        if manual["everyNailVisualApproval"]:
            raise ValueError("rework cannot approve masks")
        visual_pass = 0
    elif decision == "mask_visual_pass_pending_watermark_and_full_split":
        if not manual["everyNailVisualApproval"] or manual["visibleNailCount"] != count:
            raise ValueError("full visual review not recorded")
        if sorted(nail["truthIndex"] for nail in manual["nails"]) != list(range(1, count + 1)):
            raise ValueError("missing visual nail row")
        if any(nail["decision"] != "pass_original_resolution" or not nail["reason"]
               for nail in manual["nails"]):
            raise ValueError("unreviewed nail")
        if overlap != 0 or any(manual[key] != 0 for key in
                               ("missingNails", "duplicateMasks", "croppedNails", "maskContaminations")):
            raise ValueError("visual or geometry gate failed")
        if not manual["watermarkReviewRequired"]:
            raise ValueError("watermark debt must be retained")
        focus = list(range(1, count + 1))
        visual_pass = count
    else:
        raise ValueError("unknown decision")
    return {"schemaVersion": 1, "ok": True, "decision": decision,
            "inputs": {"sourceScript": bind(Path(__file__)), "shardReport": bind(shard_path),
                       "sourceTriage": bind(triage_path), "visualDecisions": bind(decisions_path)},
            "sourceOrdinal": ordinal, "sourceFileName": source["sourceFileName"],
            "sourceGroup": source["sourceGroup"], "sourceImage": source["sourceImage"],
            "sourceLabel": source["sourceLabel"], "priorTriageDecision": earlier["decision"],
            "humanDecision": manual,
            "geometry": {"legalPolygons": count, "overlapPairs": overlap},
            "focusOverlays": [{"truthIndex": index, "nativeOverlay": source["nails"][index - 1]["nativeOverlay"]}
                              for index in focus],
            "counts": {"visualPassNails": visual_pass, "newTrainingApprovedSources": 0},
            "fullTrainSplitApproved": False, "trainingUse": "prohibited"}


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("shard-report", "source-triage", "visual-decisions", "output", "verify-report"):
        parser.add_argument("--" + name, type=Path)
    args = parser.parse_args()
    if args.verify_report:
        old = json.loads(args.verify_report.read_text(encoding="utf-8"))
        for binding in old["inputs"].values():
            checked(binding)
        inputs = old["inputs"]
        current = build(Path(inputs["shardReport"]["path"]),
                        Path(inputs["sourceTriage"]["path"]),
                        Path(inputs["visualDecisions"]["path"]))
        if current != old:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"],
                          "sourceOrdinal": current["sourceOrdinal"], "counts": current["counts"]}))
        return
    if not all((args.shard_report, args.source_triage, args.visual_decisions, args.output)):
        parser.error("all inputs and --output required")
    if args.output.exists():
        raise FileExistsError(args.output)
    report = build(args.shard_report.resolve(), args.source_triage.resolve(), args.visual_decisions.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"],
                      "sourceOrdinal": report["sourceOrdinal"], "counts": report["counts"]}))


if __name__ == "__main__":
    main()
