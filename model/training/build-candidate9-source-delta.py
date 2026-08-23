#!/usr/bin/env python3
"""Build a hash-bound candidate9 source-image delta workspace."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def manifest_items(report: dict, label: str) -> list[dict]:
    items = report.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError(f"{label} items are missing")
    if not all(isinstance(item, dict) for item in items):
        raise ValueError(f"{label} contains malformed items")
    return items


def verify_source_item(item: dict) -> tuple[Path, str, str]:
    file_name = str(item.get("fileName", "")).strip()
    expected_hash = str(item.get("imageSha256", "")).strip().lower()
    image_path = Path(str(item.get("imagePath", ""))).resolve()
    if not file_name or not expected_hash or not image_path.is_file():
        raise ValueError(f"candidate source item is incomplete: {file_name!r}")
    if image_path.name != file_name:
        raise ValueError(f"candidate file name/path mismatch: {file_name}")
    actual_hash = sha256_file(image_path)
    if actual_hash != expected_hash:
        raise ValueError(f"candidate image hash drift: {file_name}")
    return image_path, file_name, actual_hash


def build(expanded_path: Path, prior_path: Path, output_dir: Path, expected: int) -> dict:
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite output directory: {output_dir}")
    expanded = load_json(expanded_path)
    prior = load_json(prior_path)
    expanded_items = manifest_items(expanded, "expanded manifest")
    prior_items = manifest_items(prior, "prior manifest")
    expanded_inputs = expanded.get("inputs")
    if not isinstance(expanded_inputs, dict):
        raise ValueError("expanded manifest inputs are missing")
    inventory_path = Path(str(expanded_inputs.get("inventory", ""))).resolve()
    inventory_hash = str(expanded_inputs.get("inventorySha256", "")).lower()
    if not inventory_path.is_file() or sha256_file(inventory_path) != inventory_hash:
        raise ValueError("expanded inventory evidence is missing or has drifted")
    inventory = load_json(inventory_path)
    inventory_items = manifest_items(inventory, "source inventory")
    inventory_by_name = {str(item.get("fileName", "")): item for item in inventory_items}

    prior_names = {str(item.get("fileName", "")) for item in prior_items}
    prior_hashes = {str(item.get("imageSha256", "")).lower() for item in prior_items}
    if "" in prior_names or "" in prior_hashes:
        raise ValueError("prior manifest contains incomplete identities")

    selected: list[dict] = []
    seen_names: set[str] = set()
    seen_hashes: set[str] = set()
    for item in expanded_items:
        image_path, file_name, image_hash = verify_source_item(item)
        if file_name in prior_names or image_hash in prior_hashes:
            continue
        if file_name in seen_names or image_hash in seen_hashes:
            raise ValueError(f"duplicate delta identity: {file_name}")
        seen_names.add(file_name)
        seen_hashes.add(image_hash)
        inventory_item = inventory_by_name.get(file_name)
        if not isinstance(inventory_item, dict):
            raise ValueError(f"delta item is absent from source inventory: {file_name}")
        if str(inventory_item.get("imageSha256", "")).lower() != image_hash:
            raise ValueError(f"source inventory image identity mismatch: {file_name}")
        if inventory_item.get("sourceScreeningDecision") != "keep-for-annotation":
            raise ValueError(f"source inventory did not keep item: {file_name}")
        if inventory_item.get("sourceQualityReview") != "passed-for-annotation-candidate":
            raise ValueError(f"source quality review did not pass item: {file_name}")
        selected.append(
            {
                "deltaIndex": len(selected) + 1,
                "fileName": file_name,
                "sourceImage": str(image_path),
                "imageSha256": image_hash,
                "width": int(item["width"]),
                "height": int(item["height"]),
                "sourceGroup": str(item["sourceGroup"]),
                "expectedFullyVisibleNails": int(item["fullyVisibleNails"]),
                "sourceReview": "passed-by-hash-bound-original-resolution-screening",
                "sourceReviewEvidence": {
                    "inventory": str(inventory_path),
                    "inventorySha256": inventory_hash,
                    "sourceScreeningDecision": "keep-for-annotation",
                    "sourceQualityReview": "passed-for-annotation-candidate",
                },
                "annotationTruthStatus": "not-started",
                "trainingUse": "prohibited",
            }
        )

    if len(selected) != expected:
        raise ValueError(f"expected {expected} delta items, found {len(selected)}")

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}-", dir=output_dir.parent))
    try:
        images_dir = temporary / "images"
        images_dir.mkdir()
        for item in selected:
            destination = images_dir / item["fileName"]
            os.link(item["sourceImage"], destination)
            if sha256_file(destination) != item["imageSha256"]:
                raise ValueError(f"materialized image hash mismatch: {item['fileName']}")
            item["workspaceImage"] = f"images/{item['fileName']}"
            item["materializationMethod"] = "hardlink"

        report = {
            "schemaVersion": 1,
            "ok": True,
            "decision": "candidate9_source_delta_ready_for_complete_mask_annotation",
            "trainingUse": "prohibited",
            "inputs": {
                "expandedManifest": str(expanded_path.resolve()),
                "expandedManifestSha256": sha256_file(expanded_path),
                "priorSecondaryManifest": str(prior_path.resolve()),
                "priorSecondaryManifestSha256": sha256_file(prior_path),
                "sourceInventory": str(inventory_path),
                "sourceInventorySha256": inventory_hash,
            },
            "counts": {
                "images": len(selected),
                "sourceGroups": len({item["sourceGroup"] for item in selected}),
                "expectedFullyVisibleNails": sum(
                    item["expectedFullyVisibleNails"] for item in selected
                ),
            },
            "itemsSha256": canonical_sha256(selected),
            "items": selected,
            "invariants": {
                "fileNamesUnique": len(seen_names) == len(selected),
                "imageHashesUnique": len(seen_hashes) == len(selected),
                "priorFileNameOverlap": 0,
                "priorImageHashOverlap": 0,
                "sourceImagesHashBound": True,
                "originalResolutionSourceReviewReplayed": True,
                "trainingUseProhibited": True,
            },
            "errors": [],
        }
        (temporary / "manifest.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        temporary.replace(output_dir)
        return report
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expanded", type=Path, required=True)
    parser.add_argument("--prior", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected", type=int, default=75)
    args = parser.parse_args()
    report = build(args.expanded, args.prior, args.output_dir.resolve(), args.expected)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "decision": report["decision"],
                "counts": report["counts"],
                "itemsSha256": report["itemsSha256"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
