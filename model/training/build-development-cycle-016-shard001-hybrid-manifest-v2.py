#!/usr/bin/env python3
"""Refine source-8 nail 1 against the original-pixel cuticle and side grid."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v1-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    original = json.loads(args.v1_manifest.read_text(encoding="utf-8"))
    if original.get("decision") != "hybrid_candidate_only_original_resolution_review_required":
        raise ValueError("v1 manifest drift")
    if original["images"][0]["fileName"] != "real_training_20260711_0008.jpg":
        raise ValueError("source-8 manifest drift")
    sam_path = Path(original["images"][0]["sourceAnnotationPath"])
    sam = json.loads(sam_path.read_text(encoding="utf-8"))
    old = sam["annotations"][0]["polygon"]
    def pt(x: int, y: int) -> dict[str, int]:
        return {"x": x, "y": y}
    # Original-pixel cuticle arc: x=655..720, y=432..450. Right lateral
    # plate is outside SAM's jewellery-following notches by up to ~8 px.
    polygon = ([pt(707, 436), pt(690, 432), pt(673, 432), pt(657, 438),
                pt(649, 447), pt(644, 458)]
               + old[3:24]
               + [pt(728, 594), pt(736, 578), pt(740, 552), pt(740, 529),
                  pt(738, 503), pt(738, 481), pt(734, 457), pt(722, 444)])
    original["images"][0]["nails"][0]["polygon"] = polygon
    original["images"][0]["nails"][0]["attributes"]["annotationMethod"] = "codex-original-pixel-manual-cuticle-and-lateral-edge-v2"
    original["revisionOf"] = {"path": str(args.v1_manifest.resolve()), "sha256": sha256(args.v1_manifest)}
    original["decision"] = "hybrid_v2_candidate_only_original_resolution_review_required"
    if args.verify:
        recorded = json.loads(args.output.read_text(encoding="utf-8"))
        if original != recorded:
            raise ValueError("v2 manifest reconstruction mismatch")
        print(json.dumps({"ok": True, "decision": "hybrid_v2_manifest_replayed"}))
        return
    if args.output.exists():
        raise FileExistsError(args.output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(original, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": original["decision"]}))


if __name__ == "__main__":
    main()
