#!/usr/bin/env python3
"""Build hash-bound source/overlay 2x crop sheets for selected SAM candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def verified_image(path_value: object, sha_value: object, label: str) -> Image.Image:
    path = Path(str(path_value or "")).resolve()
    if not path.is_file() or sha256_path(path) != sha_value:
        raise ValueError(f"Missing or changed {label}: {path}")
    with Image.open(path) as source:
        return source.convert("RGB")


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="Build selected SAM 2x crop review sheets.")
    value.add_argument("--visual-evidence", required=True)
    value.add_argument("--file-name", action="append", required=True)
    value.add_argument("--output-dir", required=True)
    value.add_argument("--crop-pairs-per-page", type=int, default=5)
    return value


def main() -> int:
    args = parser().parse_args()
    evidence_path = Path(args.visual_evidence).resolve()
    output_dir = Path(args.output_dir).resolve()
    if args.crop_pairs_per_page < 1 or args.crop_pairs_per_page > 8:
        raise ValueError("crop-pairs-per-page must be between 1 and 8")
    if output_dir.exists():
        raise ValueError(f"Refusing to overwrite output directory: {output_dir}")
    evidence = read_object(evidence_path)
    if (
        evidence.get("ok") is not True
        or evidence.get("decision") != "sam_visual_review_evidence_ready_not_truth"
        or evidence.get("policy", {}).get("trainingUse") != "prohibited"
    ):
        raise ValueError("Visual evidence must be passing and candidate-only")
    requested = args.file_name
    if len(requested) != len(set(requested)):
        raise ValueError("Selected file names must be unique")
    by_name = {str(item.get("fileName", "")): item for item in evidence.get("items", [])}
    if any(name not in by_name for name in requested):
        raise ValueError("A selected file is absent from visual evidence")

    crop_records: list[tuple[str, dict[str, Any]]] = []
    for file_name in requested:
        item = by_name[file_name]
        for crop in item.get("crops", []):
            crop_records.append((file_name, crop))
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}-", dir=output_dir.parent))
    pages: list[dict[str, Any]] = []
    try:
        pair_height = 350
        tile_size = (470, 310)
        font = ImageFont.load_default(size=18)
        for page_index, start in enumerate(range(0, len(crop_records), args.crop_pairs_per_page), start=1):
            rows = crop_records[start : start + args.crop_pairs_per_page]
            sheet = Image.new("RGB", (960, pair_height * len(rows)), "white")
            draw = ImageDraw.Draw(sheet)
            identities: list[dict[str, Any]] = []
            for row_index, (file_name, crop) in enumerate(rows):
                source = verified_image(crop.get("sourceCrop"), crop.get("sourceCropSha256"), "source crop")
                overlay = verified_image(crop.get("overlayCrop"), crop.get("overlayCropSha256"), "overlay crop")
                source = ImageOps.contain(source, tile_size, Image.Resampling.LANCZOS)
                overlay = ImageOps.contain(overlay, tile_size, Image.Resampling.LANCZOS)
                y0 = row_index * pair_height
                sheet.paste(source, ((470 - source.width) // 2, y0 + 34 + (310 - source.height) // 2))
                sheet.paste(overlay, (480 + (470 - overlay.width) // 2, y0 + 34 + (310 - overlay.height) // 2))
                label = (
                    f"{file_name} | nail {int(crop['nailIndex']):02d} | "
                    f"geometry {crop.get('geometryStatus')} | source left / overlay right"
                )
                draw.text((8, y0 + 7), label, fill="black", font=font)
                draw.line((0, y0 + pair_height - 1, 959, y0 + pair_height - 1), fill="#777777", width=1)
                identities.append({"fileName": file_name, "nailIndex": int(crop["nailIndex"])})
            page_path = staging / f"sam-crop-review-page-{page_index:03d}.jpg"
            sheet.save(page_path, quality=96, subsampling=0)
            pages.append(
                {
                    "index": page_index,
                    "path": str(output_dir / page_path.name),
                    "sha256": sha256_path(page_path),
                    "crops": identities,
                }
            )
        report = {
            "schemaVersion": 1,
            "ok": True,
            "decision": "selected_sam_crop_review_sheets_ready_not_truth",
            "inputs": {
                "visualEvidence": str(evidence_path),
                "visualEvidenceSha256": sha256_path(evidence_path),
            },
            "selectedFileNames": requested,
            "counts": {"images": len(requested), "cropPairs": len(crop_records), "pages": len(pages)},
            "pages": pages,
            "trainingUse": "prohibited",
        }
        (staging / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(staging, output_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    print(json.dumps({"ok": True, **report["counts"]}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
