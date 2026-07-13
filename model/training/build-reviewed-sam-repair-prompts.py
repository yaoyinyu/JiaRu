from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build provenance-safe SAM repair prompts from a reviewed keep/drop/add manifest."
    )
    parser.add_argument("--source-prompts", required=True)
    parser.add_argument("--repair-manifest", required=True)
    parser.add_argument("--output", required=True)
    return parser


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_box(box: object, label: str) -> list[float]:
    if not isinstance(box, list) or len(box) != 4:
        raise ValueError(f"{label} must contain four normalized coordinates")
    values = [float(value) for value in box]
    x1, y1, x2, y2 = values
    if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
        raise ValueError(f"{label} must satisfy 0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1")
    if (x2 - x1) * (y2 - y1) < 0.0001:
        raise ValueError(f"{label} is too small")
    return values


def build_document(source_path: Path, manifest_path: Path) -> dict:
    source = json.loads(source_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schemaVersion") != 1:
        raise ValueError("repair manifest schemaVersion must be 1")
    if manifest.get("decision") != "human_reviewed_prompt_repair_candidate_only":
        raise ValueError("repair manifest decision must keep repaired prompts candidate-only")

    source_images = {item["fileName"]: item for item in source.get("images", [])}
    repairs = manifest.get("images")
    if not isinstance(repairs, list) or not repairs:
        raise ValueError("repair manifest images must be a non-empty list")

    output_images = []
    seen_files: set[str] = set()
    for repair in repairs:
        file_name = repair.get("fileName")
        if not isinstance(file_name, str) or not file_name:
            raise ValueError("repair item fileName must be a non-empty string")
        if file_name in seen_files:
            raise ValueError(f"duplicate repair item: {file_name}")
        seen_files.add(file_name)
        if file_name not in source_images:
            raise ValueError(f"repair item is not present in source prompts: {file_name}")

        source_item = source_images[file_name]
        source_boxes = source_item.get("boxes", [])
        keep_indices = repair.get("keepPromptIndices", [])
        if not isinstance(keep_indices, list) or any(
            not isinstance(index, int) for index in keep_indices
        ):
            raise ValueError(f"{file_name} keepPromptIndices must be an integer list")
        if len(keep_indices) != len(set(keep_indices)):
            raise ValueError(f"{file_name} keepPromptIndices contains duplicates")
        invalid_indices = [index for index in keep_indices if index < 1 or index > len(source_boxes)]
        if invalid_indices:
            raise ValueError(f"{file_name} keepPromptIndices out of range: {invalid_indices}")

        source_modes = source_item.get("promptModes", ["box"] * len(source_boxes))
        if not isinstance(source_modes, list) or len(source_modes) != len(source_boxes):
            raise ValueError(f"{file_name} source promptModes count must match source boxes")
        allowed_prompt_modes = {"box", "center", "box-center", "center-negative-corners"}
        invalid_source_modes = [mode for mode in source_modes if mode not in allowed_prompt_modes]
        if invalid_source_modes:
            raise ValueError(f"{file_name} has invalid source promptModes: {invalid_source_modes}")

        boxes = [
            validate_box(source_boxes[index - 1], f"{file_name} source box {index}")
            for index in keep_indices
        ]
        prompt_modes = [source_modes[index - 1] for index in keep_indices]
        add_boxes = repair.get("addBoxes", [])
        add_prompt_modes = repair.get("addPromptModes", ["box"] * len(add_boxes))
        if not isinstance(add_prompt_modes, list) or len(add_prompt_modes) != len(add_boxes):
            raise ValueError(f"{file_name} addPromptModes count must match addBoxes")
        invalid_add_modes = [mode for mode in add_prompt_modes if mode not in allowed_prompt_modes]
        if invalid_add_modes:
            raise ValueError(f"{file_name} has invalid addPromptModes: {invalid_add_modes}")
        for add_index, box in enumerate(add_boxes, start=1):
            boxes.append(validate_box(box, f"{file_name} add box {add_index}"))
        prompt_modes.extend(add_prompt_modes)
        if not boxes:
            raise ValueError(f"{file_name} repair produces no prompts")
        if len({tuple(box) for box in boxes}) != len(boxes):
            raise ValueError(f"{file_name} repair produces duplicate boxes")

        source_group = source_item.get("sourceGroup", source.get("sourceGroup"))
        if not isinstance(source_group, str) or not source_group.strip():
            raise ValueError(f"{file_name} has no sourceGroup")
        output_images.append(
            {
                "fileName": file_name,
                "sourceGroup": source_group.strip(),
                "boxes": boxes,
                "promptModes": prompt_modes,
                "repairProvenance": {
                    "keptSourcePromptIndices": keep_indices,
                    "addedBoxCount": len(add_boxes),
                    "addedPromptModes": add_prompt_modes,
                    "reviewReason": repair.get("reviewReason", "manual_original_resolution_review"),
                },
            }
        )

    return {
        "schemaVersion": 1,
        "source": "human-reviewed-keep-drop-add-repair",
        "decision": "sam_repair_candidate_only_not_test_truth",
        "sourcePromptFile": source_path.name,
        "sourcePromptSha256": sha256(source_path),
        "repairManifestFile": manifest_path.name,
        "repairManifestSha256": sha256(manifest_path),
        "imageCount": len(output_images),
        "promptCount": sum(len(item["boxes"]) for item in output_images),
        "images": output_images,
    }


def main() -> None:
    args = build_parser().parse_args()
    source_path = Path(args.source_prompts).resolve()
    manifest_path = Path(args.repair_manifest).resolve()
    output_path = Path(args.output).resolve()
    try:
        document = build_document(source_path, manifest_path)
    except Exception as error:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps({"ok": False, "errors": [str(error)]}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        raise
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: document[key] for key in ("decision", "imageCount", "promptCount")}, indent=2))


if __name__ == "__main__":
    main()
