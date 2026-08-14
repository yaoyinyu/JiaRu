#!/usr/bin/env python3
"""按哈希绑定的声明删除已确认无效的单个 SAM 候选提示。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--drop", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    document = json.loads(args.input.read_text(encoding="utf-8"))
    declaration = json.loads(args.drop.read_text(encoding="utf-8"))
    if declaration.get("inputSha256") != sha256_file(args.input):
        raise ValueError("drop declaration does not bind the current prompt file")
    drops = {item["fileName"]: set(item["promptIndices"]) for item in declaration.get("drops", [])}
    removed = 0
    for image in document.get("images", []):
        indices = drops.get(image["fileName"], set())
        if not indices:
            continue
        boxes = image.get("boxes", [])
        modes = image.get("promptModes", [])
        invalid = {index for index in indices if not isinstance(index, int) or index < 1 or index > len(boxes)}
        if invalid:
            raise ValueError(f"invalid 1-based prompt indices for {image['fileName']}: {sorted(invalid)}")
        keep = [position for position in range(len(boxes)) if position + 1 not in indices]
        image["boxes"] = [boxes[position] for position in keep]
        image["promptModes"] = [modes[position] for position in keep]
        removed += len(indices)
    document["sourcePromptFile"] = str(args.input)
    document["sourcePromptSha256"] = sha256_file(args.input)
    document["dropDeclaration"] = str(args.drop)
    document["dropDeclarationSha256"] = sha256_file(args.drop)
    document["removedPromptCount"] = removed
    document["promptCount"] = sum(len(item.get("boxes", [])) for item in document.get("images", []))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"removedPromptCount": removed, "promptCount": document["promptCount"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
