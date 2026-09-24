#!/usr/bin/env python3
"""One directed SAM retry for source28 nail 3's root-side background teeth."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ADDED_NEGATIVES_PX = [[425, 685], [425, 711], [562, 666]]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(original_path: Path) -> dict:
    original = json.loads(original_path.read_text(encoding="utf-8"))
    if original["decision"] != "source028_sam_candidates_only" or original["trainingUse"] != "prohibited":
        raise ValueError("original prompt contract mismatch")
    if len(original["images"]) != 1 or len(original["images"][0]["boxes"]) != 5:
        raise ValueError("prompt count mismatch")
    source = Path(original["inputs"]["isolatedImage"]["path"])
    if sha(source) != original["images"][0]["sourceImageSha256"]:
        raise ValueError("isolated source drift")
    new = json.loads(json.dumps(original, ensure_ascii=False))
    new["schemaVersion"] = 2
    new["decision"] = "source028_nail3_one_directed_sam_retry_candidates_only"
    new["revisionOf"] = {"path": str(original_path.resolve()), "sha256": sha(original_path)}
    new["directedChange"] = {"truthIndex": 3, "reason": "nail3 proximal side contour has background teeth",
                             "addedNegativePointsPx": ADDED_NEGATIVES_PX}
    new["images"][0]["negativePoints"][2].extend([[x / 1080, y / 1352] for x, y in ADDED_NEGATIVES_PX])
    return new


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    current = build(args.original.resolve())
    if args.verify:
        recorded = json.loads(args.output.read_text(encoding="utf-8"))
        if current != recorded:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"]}))
        return
    if args.output.exists():
        raise FileExistsError(args.output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": current["decision"]}))


if __name__ == "__main__":
    main()
