from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="按原分辨率审核选择既有提示并补充人工框，生成 candidate7 精确返修提示。"
    )
    parser.add_argument("--input-prompts", required=True)
    parser.add_argument("--selection", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    input_path = Path(args.input_prompts).resolve()
    selection_path = Path(args.selection).resolve()
    output_path = Path(args.output).resolve()
    if output_path.exists():
        raise ValueError(f"refusing to overwrite existing output: {output_path}")
    source = read_json(input_path)
    selection = read_json(selection_path)
    if selection.get("schemaVersion") != 1 or selection.get("decision") != "candidate7_selected_sam_repair_prompts":
        raise ValueError("unsupported selection contract")
    if selection.get("inputPromptsSha256") != sha256_file(input_path):
        raise ValueError("selection does not bind current input prompts")

    source_by_file = {str(item["fileName"]): item for item in source.get("images", [])}
    images: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in selection.get("items", []):
        file_name = str(item.get("fileName", ""))
        if not file_name or file_name in seen or file_name not in source_by_file:
            raise ValueError(f"invalid or duplicate fileName: {file_name}")
        seen.add(file_name)
        source_item = source_by_file[file_name]
        boxes = source_item.get("boxes", [])
        modes = source_item.get("promptModes", [])
        keep = item.get("keepPromptIndices", [])
        add = item.get("addBoxes", [])
        if (
            not isinstance(keep, list)
            or len(set(keep)) != len(keep)
            or any(not isinstance(index, int) or index < 1 or index > len(boxes) for index in keep)
        ):
            raise ValueError(f"invalid 1-based keepPromptIndices: {file_name}")
        if not isinstance(add, list):
            raise ValueError(f"addBoxes must be a list: {file_name}")
        for box in add:
            if (
                not isinstance(box, list)
                or len(box) != 4
                or any(not isinstance(value, (int, float)) for value in box)
                or not (0 <= float(box[0]) < float(box[2]) <= 1)
                or not (0 <= float(box[1]) < float(box[3]) <= 1)
            ):
                raise ValueError(f"invalid normalized add box: {file_name}")
        expected = int(source_item["expectedFullyVisibleNails"])
        if len(keep) + len(add) != expected:
            raise ValueError(f"selected prompt count differs from expected: {file_name}")
        selected_boxes = [boxes[index - 1] for index in keep]
        selected_modes = [modes[index - 1] for index in keep]
        selected_boxes.extend([[float(value) for value in box] for box in add])
        selected_modes.extend(["center-negative-corners"] * len(add))
        images.append(
            {
                **{key: source_item[key] for key in ("fileName", "sha256", "sourceGroup", "expectedFullyVisibleNails")},
                "boxes": selected_boxes,
                "promptModes": selected_modes,
                "keptPromptIndices": keep,
                "manualAddedBoxCount": len(add),
                "selectionPolicy": "original_resolution_selected_prompts_candidate_only",
                "note": str(item.get("note", "")),
            }
        )

    document = {
        "schemaVersion": 1,
        "source": "candidate7-original-resolution-selected-repair",
        "decision": "sam_candidate_only_not_training_truth",
        "inputs": {
            "inputPrompts": str(input_path),
            "inputPromptsSha256": sha256_file(input_path),
            "selection": str(selection_path),
            "selectionSha256": sha256_file(selection_path),
        },
        "promptMode": "mixed-selected-and-center-negative-corners",
        "imageCount": len(images),
        "promptCount": sum(len(item["boxes"]) for item in images),
        "unresolvedImageCount": 0,
        "unresolved": [],
        "policy": {"originalResolutionReviewRequired": True, "trainingUse": "prohibited"},
        "images": images,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "images": len(images), "prompts": document["promptCount"]}))


if __name__ == "__main__":
    main()
