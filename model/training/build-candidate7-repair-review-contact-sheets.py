from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Build hash-bound candidate7 repair overlay contact sheets.")
    parser.add_argument("--visual-evidence", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--images-per-page", type=int, default=4)
    args = parser.parse_args()
    if args.images_per_page < 1 or args.images_per_page > 9:
        raise ValueError("images-per-page must be between 1 and 9")

    evidence_path = Path(args.visual_evidence).resolve()
    output_dir = Path(args.output_dir).resolve()
    if output_dir.exists():
        raise ValueError(f"refusing to overwrite output directory: {output_dir}")
    evidence = read_json(evidence_path)
    if (
        evidence.get("ok") is not True
        or evidence.get("decision") != "sam_visual_review_evidence_ready_not_truth"
        or evidence.get("policy", {}).get("trainingUse") != "prohibited"
    ):
        raise ValueError("a passing candidate-only visual evidence report is required")
    items = list(evidence.get("items", []))
    if len(items) != int(evidence.get("summary", {}).get("images", -1)):
        raise ValueError("visual evidence image summary differs")

    columns = 2 if args.images_per_page > 1 else 1
    rows = (args.images_per_page + columns - 1) // columns
    tile_width, tile_height, header_height = 720, 720, 52
    font = ImageFont.load_default(size=22)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.tmp-", dir=output_dir.parent))
    pages: list[dict[str, Any]] = []
    try:
        for page_index, start in enumerate(range(0, len(items), args.images_per_page), start=1):
            page_items = items[start : start + args.images_per_page]
            canvas = Image.new("RGB", (columns * tile_width, rows * (tile_height + header_height)), "white")
            draw = ImageDraw.Draw(canvas)
            names: list[str] = []
            for slot, item in enumerate(page_items):
                file_name = str(item["fileName"])
                overlay_path = Path(str(item["overlayPath"])).resolve()
                if not overlay_path.is_file() or sha256_file(overlay_path) != item.get("overlaySha256"):
                    raise ValueError(f"overlay is missing or changed: {file_name}")
                with Image.open(overlay_path) as source:
                    overlay = source.convert("RGB")
                scale = min(tile_width / overlay.width, tile_height / overlay.height)
                resized = overlay.resize(
                    (max(1, round(overlay.width * scale)), max(1, round(overlay.height * scale))),
                    Image.Resampling.LANCZOS,
                )
                column = slot % columns
                row = slot // columns
                x0 = column * tile_width
                y0 = row * (tile_height + header_height)
                x = x0 + (tile_width - resized.width) // 2
                y = y0 + header_height + (tile_height - resized.height) // 2
                draw.text(
                    (x0 + 8, y0 + 8),
                    f"{start + slot + 1:02d}  {file_name}  masks={item['polygonCount']} suspects={item['geometrySuspectCount']}",
                    fill="black",
                    font=font,
                )
                canvas.paste(resized, (x, y))
                draw.rectangle((x0, y0, x0 + tile_width - 1, y0 + tile_height + header_height - 1), outline="#777777", width=2)
                names.append(file_name)
            page_path = temporary / f"candidate7-repair-review-page-{page_index:02d}.jpg"
            canvas.save(page_path, quality=94, subsampling=0)
            pages.append(
                {
                    "index": page_index,
                    "path": str(output_dir / page_path.name),
                    "sha256": sha256_file(page_path),
                    "fileNames": names,
                }
            )
        report = {
            "schemaVersion": 1,
            "ok": True,
            "decision": "candidate7_repair_contact_sheets_ready_original_resolution_review_required",
            "trainingUse": "prohibited",
            "inputs": {
                "visualEvidence": str(evidence_path),
                "visualEvidenceSha256": sha256_file(evidence_path),
            },
            "counts": {"images": len(items), "pages": len(pages)},
            "pages": pages,
        }
        (temporary / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        temporary.replace(output_dir)
    except Exception:
        if temporary.exists():
            for child in temporary.iterdir():
                child.unlink()
            temporary.rmdir()
        raise
    print(json.dumps({"ok": True, **report["counts"]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
