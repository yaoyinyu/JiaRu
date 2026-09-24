#!/usr/bin/env python3
"""Bind one original-pixel manual root repair and nine SAM candidate polygons.

The manifest feeds the existing hybrid builder. Its output remains a review
candidate until all ten nails pass original-resolution visual adjudication.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build(audit_path: Path, retry_path: Path) -> dict:
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    retry = json.loads(retry_path.read_text(encoding="utf-8"))
    if audit.get("ok") is not True or audit.get("decision") != "geometry_pass_visual_review_pending":
        raise ValueError("candidate audit is invalid")
    if retry.get("ok") is not True or retry.get("promptCount") != 5 or retry.get("boxOnlyFallbackPromptCount") != 0:
        raise ValueError("directed retry is invalid")
    if retry["outputs"][0]["fileName"] != "real_training_20260711_0008.jpg":
        raise ValueError("directed retry targeted the wrong source")
    base = {row["fileName"]: row for row in audit["images"]}
    if len(base) != 2:
        raise ValueError("candidate source count drift")
    source8 = base["real_training_20260711_0008.jpg"]
    source18 = base["candidate58_openai_positive_001_translucent_five_nails.png"]
    retry_annotation = Path(retry["outputs"][0]["annotationPath"])
    if json.loads(retry_annotation.read_text(encoding="utf-8"))["annotations"][0]["polygon"] == json.loads(Path(source8["annotation"]["path"]).read_text(encoding="utf-8"))["annotations"][0]["polygon"]:
        raise ValueError("directed retry was identical to original")
    for source in (source8, source18):
        for key in ("sourceImage", "annotation", "overlay"):
            if sha256(Path(source[key]["path"])) != source[key]["sha256"]:
                raise ValueError(f"candidate evidence drift: {key}")
    # The proximal natural nail arc in the native source lies above SAM's
    # y=436 truncation. Keep its reviewed distal contour and replace the short
    # proximal arc only. These are original-image pixel coordinates.
    sam_points = json.loads(Path(source8["annotation"]["path"]).read_text(encoding="utf-8"))["annotations"][0]["polygon"]
    def point(x: int, y: int) -> dict[str, int]:
        return {"x": x, "y": y}
    manual = ([point(707, 430), point(690, 427), point(673, 428), point(657, 434),
               point(649, 443), point(644, 455)]
              + sam_points[3:34]
              + [point(720, 451), point(722, 441)])
    images = [
        {"fileName": source8["fileName"], "sourceGroup": source8["sourceGroup"],
         "sourceAnnotationPath": source8["annotation"]["path"],
         "nails": [{"polygon": manual, "attributes": {"annotationMethod": "codex-original-pixel-manual-proximal-arc-repair"}},
                   *({"sourceIndex": n} for n in range(2, 6))]},
        {"fileName": source18["fileName"], "sourceGroup": source18["sourceGroup"],
         "sourceAnnotationPath": source18["annotation"]["path"],
         "nails": [{"sourceIndex": n} for n in range(1, 6)]},
    ]
    return {"schemaVersion": 1, "decision": "hybrid_candidate_only_original_resolution_review_required",
            "trainingUse": "prohibited", "candidateAudit": {"path": str(audit_path), "sha256": sha256(audit_path)},
            "directedRetry": {"path": str(retry_path), "sha256": sha256(retry_path)},
            "images": images}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-audit", type=Path, required=True)
    parser.add_argument("--directed-retry", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    current = build(args.candidate_audit.resolve(), args.directed_retry.resolve())
    if args.verify:
        old = json.loads(args.output.read_text(encoding="utf-8"))
        if current != old:
            raise ValueError("hybrid manifest reconstruction mismatch")
        print(json.dumps({"ok": True, "decision": "hybrid_manifest_replayed"}))
        return
    if args.output.exists():
        raise FileExistsError(args.output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": current["decision"], "images": len(current["images"])}))


if __name__ == "__main__":
    main()
