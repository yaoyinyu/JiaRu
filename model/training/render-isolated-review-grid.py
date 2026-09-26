#!/usr/bin/env python3
"""Render coordinate guides from an already isolated nail review image."""

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--ordinal", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.review.read_text(encoding="utf-8"))
    source = next(row for row in report["sources"] if row["ordinal"] == args.ordinal)
    args.output.mkdir(parents=True, exist_ok=True)
    with Image.open(source["isolatedImage"]["path"]) as opened:
        image = opened.convert("RGB")
    for nail in source["nails"]:
        if nail["truthIndex"] not in (3, 4, 5):
            continue
        x1, y1, x2, y2 = nail["cropBox"]
        crop = image.crop((x1, y1, x2, y2))
        draw = ImageDraw.Draw(crop)
        for x in range((x1 // 25 + 1) * 25, x2, 25):
            draw.line((x - x1, 0, x - x1, crop.height), fill=(0, 255, 0), width=1)
            draw.text((x - x1 + 2, 2), str(x), fill=(0, 100, 0), stroke_width=1,
                      stroke_fill=(255, 255, 255))
        for y in range((y1 // 25 + 1) * 25, y2, 25):
            draw.line((0, y - y1, crop.width, y - y1), fill=(0, 255, 0), width=1)
            draw.text((2, y - y1 + 2), str(y), fill=(0, 100, 0), stroke_width=1,
                      stroke_fill=(255, 255, 255))
        crop.save(args.output / f"source-{args.ordinal:03d}-nail-{nail['truthIndex']:02d}-grid.png")


if __name__ == "__main__":
    main()
