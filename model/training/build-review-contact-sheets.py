from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build paginated contact sheets for visual label review.")
    parser.add_argument("--image-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--page-size", type=int, default=12)
    parser.add_argument("--columns", type=int, default=3)
    parser.add_argument("--cell-width", type=int, default=640)
    parser.add_argument("--cell-height", type=int, default=640)
    parser.add_argument("--label-height", type=int, default=72)
    parser.add_argument("--quality", type=int, default=90)
    return parser


def fit_image(source: Image.Image, width: int, height: int) -> Image.Image:
    image = source.convert("RGB")
    scale = min(width / image.width, height / image.height)
    resized = image.resize(
        (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
        Image.Resampling.LANCZOS,
    )
    canvas = Image.new("RGB", (width, height), "white")
    canvas.paste(resized, ((width - resized.width) // 2, (height - resized.height) // 2))
    return canvas


def main() -> None:
    args = build_parser().parse_args()
    if args.page_size < 1 or args.columns < 1:
        raise ValueError("page-size and columns must be positive")
    image_dir = Path(args.image_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    images = sorted(
        path for path in image_dir.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )
    if not images:
        raise RuntimeError(f"no supported images found in {image_dir}")

    font = ImageFont.load_default(size=18)
    page_count = math.ceil(len(images) / args.page_size)
    for page_index in range(page_count):
        page_images = images[page_index * args.page_size:(page_index + 1) * args.page_size]
        rows = math.ceil(len(page_images) / args.columns)
        sheet = Image.new(
            "RGB",
            (
                args.columns * args.cell_width,
                rows * (args.cell_height + args.label_height),
            ),
            "white",
        )
        draw = ImageDraw.Draw(sheet)
        for cell_index, image_path in enumerate(page_images):
            row, column = divmod(cell_index, args.columns)
            x = column * args.cell_width
            y = row * (args.cell_height + args.label_height)
            with Image.open(image_path) as source:
                fitted = fit_image(source, args.cell_width, args.cell_height)
            sheet.paste(fitted, (x, y))
            label = f"{page_index * args.page_size + cell_index + 1:03d}  {image_path.stem}"
            draw.rectangle((x, y + args.cell_height, x + args.cell_width, y + args.cell_height + args.label_height), fill="white")
            draw.text((x + 8, y + args.cell_height + 8), label, fill="black", font=font)
        output_path = output_dir / f"contact-sheet-{page_index + 1:02d}.jpg"
        sheet.save(output_path, quality=args.quality, optimize=True)

    print(f"images={len(images)} pages={page_count} output={output_dir}")


if __name__ == "__main__":
    main()
