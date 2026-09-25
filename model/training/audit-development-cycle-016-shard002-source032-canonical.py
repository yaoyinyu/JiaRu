#!/usr/bin/env python3
"""Prove source32's historical approved truth equals its defective cycle012 label."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


TARGET = "nail_00356_69eda4b9000000003502a7b8_3.jpg"


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


def build(index_path: Path, shard_path: Path, progress_path: Path) -> dict:
    index, shard, progress = map(load, (index_path, shard_path, progress_path))
    matches = [item for item in index["canonicalTruths"] if item["fileName"] == TARGET]
    if len(matches) != 1:
        raise ValueError("historical truth identity missing or duplicated")
    canonical = matches[0]
    source = next(item for item in shard["sourceImages"] if item["ordinal"] == 32)
    row = next(item for item in progress["sourceDispositions"] if item["ordinal"] == 32)
    if (not progress["ok"] or shard["shard"]["shard"] != 2 or
            row["decision"] != "confirmed_label_rework" or
            row["sourceFileName"] != TARGET or source["sourceFileName"] != TARGET or
            row["sourceImage"] != source["sourceImage"] or
            row["sourceLabel"] != source["sourceLabel"] or
            canonical["imageSha256"] != source["sourceImage"]["sha256"] or
            canonical["sourceGroup"] != source["sourceGroup"] or
            canonical["completeMaskCount"] != 5):
        raise ValueError("historical/current source identity mismatch")
    annotation_path = Path(canonical["annotationPath"])
    if sha(annotation_path) != canonical["annotationSha256"]:
        raise ValueError("historical annotation drift")
    if sha(Path(canonical["reportPath"])) != canonical["reportSha256"]:
        raise ValueError("historical approval report drift")
    document = load(annotation_path)
    if (document["image"]["fileName"] != TARGET or
            document["image"]["sourceGroup"] != canonical["sourceGroup"] or
            len(document["annotations"]) != 5):
        raise ValueError("historical annotation structure mismatch")
    width, height = document["image"]["width"], document["image"]["height"]
    lines = Path(source["sourceLabel"]["path"]).read_text(encoding="utf-8").splitlines()
    if len(lines) != 5:
        raise ValueError("cycle012 label count mismatch")
    max_delta = 0.0
    vertex_counts = []
    for index_nail, (nail, line) in enumerate(zip(document["annotations"], lines, strict=True), start=1):
        values = [float(value) for value in line.split()]
        points = nail["polygon"]
        if values[0] != 0 or len(values) != 1 + 2 * len(points):
            raise ValueError(f"nail {index_nail} point count/class mismatch")
        vertex_counts.append(len(points))
        for vertex, point in enumerate(points):
            delta = max(abs(float(point["x"]) / width - values[1 + 2 * vertex]),
                        abs(float(point["y"]) / height - values[2 + 2 * vertex]))
            max_delta = max(max_delta, delta)
    if max_delta > 5e-9:
        raise ValueError(f"historical/cycle012 polygon mismatch: {max_delta}")
    return {"schemaVersion": 1, "ok": True,
            "decision": "historical_approved_truth_is_same_defective_cycle012_polygon",
            "sourceOrdinal": 32, "sourceFileName": TARGET,
            "inputs": {"sourceScript": bind(Path(__file__)), "canonicalIndex": bind(index_path),
                       "historicalApprovalReport": bind(Path(canonical["reportPath"])),
                       "historicalAnnotation": bind(annotation_path),
                       "shardReport": bind(shard_path), "progressV9": bind(progress_path),
                       "sourceImage": bind(Path(source["sourceImage"]["path"])),
                       "cycle012Label": bind(Path(source["sourceLabel"]["path"]))},
            "historicalSequence": canonical["sequence"],
            "historicalAnnotationSha256": canonical["annotationSha256"],
            "sourceImageSha256": canonical["imageSha256"],
            "sourceGroup": canonical["sourceGroup"],
            "counts": {"canonicalRecordsWithSameFileName": 1,
                       "polygons": 5, "vertexCounts": vertex_counts,
                       "maxNormalizedVertexDelta": max_delta},
            "historicalSnapshotChanged": False, "newImageCount": 0,
            "newTrainingApprovedSources": 0, "trainingUse": "prohibited"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=Path)
    parser.add_argument("--shard", type=Path)
    parser.add_argument("--progress", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        old = load(args.verify_report)
        for binding in old["inputs"].values():
            checked(binding)
        inputs = old["inputs"]
        current = build(Path(inputs["canonicalIndex"]["path"]),
                        Path(inputs["shardReport"]["path"]),
                        Path(inputs["progressV9"]["path"]))
        if current != old:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"],
                          "counts": current["counts"]}))
        return
    if not all((args.index, args.shard, args.progress, args.output)):
        parser.error("all inputs and --output required")
    if args.output.exists():
        raise FileExistsError(args.output)
    report = build(args.index.resolve(), args.shard.resolve(), args.progress.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"],
                      "counts": report["counts"]}))


if __name__ == "__main__":
    main()
