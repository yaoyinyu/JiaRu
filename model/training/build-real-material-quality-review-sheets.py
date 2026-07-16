from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a source-group-aware screening sheet for one quality review shard.")
    parser.add_argument("--queue-report", required=True)
    parser.add_argument("--shard-index", required=True, type=int)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--images-per-page", type=int, default=4)
    args = parser.parse_args()
    if args.images_per_page <= 0 or args.images_per_page > 4:
        raise ValueError("--images-per-page must be between 1 and 4")
    queue_path = Path(args.queue_report).resolve()
    output_dir = Path(args.output_dir).resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"output directory must be absent or empty: {output_dir}")
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    if queue.get("ok") is not True or queue.get("decision") != "quality_review_queue_ready":
        errors.append("quality review queue must pass")
    shard = next((item for item in queue.get("shards", []) if int(item.get("index", -1)) == args.shard_index), None)
    if shard is None:
        errors.append(f"unknown shard index: {args.shard_index}")
        shard_path = Path("missing")
    else:
        shard_path = Path(str(shard.get("path", ""))).resolve()
        if not shard_path.is_file() or sha256_file(shard_path) != shard.get("sha256"):
            errors.append("quality review shard is missing or changed")
    workspace_path = Path(str(queue.get("inputs", {}).get("workspaceReport", ""))).resolve()
    if not workspace_path.is_file() or sha256_file(workspace_path) != queue.get("inputs", {}).get("workspaceReportSha256"):
        errors.append("bound workspace report is missing or changed")
        image_root = Path("missing")
    else:
        workspace = json.loads(workspace_path.read_text(encoding="utf-8"))
        image_root = Path(str(workspace.get("inputs", {}).get("root", ""))).resolve()
    rows: list[dict[str, str]] = []
    if shard_path.is_file():
        with shard_path.open("r", encoding="utf-8-sig", newline="") as source:
            rows = list(csv.DictReader(source))
    for row in rows:
        image_path = image_root / row["fileName"]
        if not image_path.is_file() or sha256_file(image_path) != row.get("sha256"):
            errors.append(f"candidate image is missing or changed: {row.get('fileName')}")
    output_dir.mkdir(parents=True, exist_ok=True)
    if errors:
        (output_dir / "quality-review-sheets-report.json").write_text(json.dumps({"ok": False, "errors": errors}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise SystemExit(1)

    pages: list[dict[str, object]] = []
    font = ImageFont.load_default()
    for start in range(0, len(rows), args.images_per_page):
        page_index = start // args.images_per_page + 1
        canvas = Image.new("RGB", (1800, 2200), "white")
        draw = ImageDraw.Draw(canvas)
        draw.text((24, 16), f"Quality review shard {args.shard_index:03d} page {page_index:03d}", fill="black", font=font)
        for offset, row in enumerate(rows[start : start + args.images_per_page]):
            x = 24 + (offset % 2) * 888
            y = 60 + (offset // 2) * 1050
            with Image.open(image_root / row["fileName"]) as image:
                thumb = ImageOps.contain(image.convert("RGB"), (840, 900), Image.Resampling.LANCZOS)
            canvas.paste(thumb, (x + (840 - thumb.width) // 2, y + (900 - thumb.height) // 2))
            group_suffix = row["sourceGroup"].rsplit(":", 1)[-1]
            draw.text((x, y + 910), f"{start + offset + 1:04d} {row['fileName'][:72]}\nsource {group_suffix}", fill="black", font=font)
        page_path = output_dir / f"quality-shard-{args.shard_index:03d}-page-{page_index:03d}.jpg"
        canvas.save(page_path, quality=92)
        pages.append({"path": str(page_path), "sha256": sha256_file(page_path), "startRow": start + 1, "endRow": min(start + args.images_per_page, len(rows))})
    report = {
        "ok": True,
        "decision": "screening_sheets_ready_original_resolution_review_still_required",
        "inputs": {"queueReport": str(queue_path), "queueReportSha256": sha256_file(queue_path), "shard": str(shard_path), "shardSha256": sha256_file(shard_path)},
        "shardIndex": args.shard_index,
        "counts": {"images": len(rows), "pages": len(pages), "sourceGroups": len({row["sourceGroup"] for row in rows})},
        "policy": {"contactSheetsCannotApproveImages": True, "originalResolutionReviewRequired": True},
        "pages": pages,
        "errors": [],
    }
    (output_dir / "quality-review-sheets-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, **report["counts"]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
