from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from PIL import Image


MANIFEST_VERSION = "nail-texture-region-extraction/v1"
SAFE_REGION_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract reviewed photo regions from screenshot/collage sources with provenance."
    )
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--image-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--min-side", type=int, default=192)
    return parser


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_parent(image_dir: Path, file_name: str) -> Path:
    if not file_name or Path(file_name).name != file_name:
        raise ValueError("parentFileName must be a file name without directory components")
    path = (image_dir / file_name).resolve()
    if path.parent != image_dir:
        raise ValueError("parentFileName escapes image-dir")
    if not path.is_file():
        raise FileNotFoundError(f"parent image does not exist: {file_name}")
    return path


def normalized_box(value: object) -> tuple[float, float, float, float]:
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError("box must contain four normalized numbers")
    if not all(isinstance(item, (int, float)) for item in value):
        raise ValueError("box values must be numbers")
    x1, y1, x2, y2 = (float(item) for item in value)
    if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
        raise ValueError("box must satisfy 0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1")
    return x1, y1, x2, y2


def pixel_box(
    box: tuple[float, float, float, float], width: int, height: int
) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = box
    left = max(0, min(width - 1, round(x1 * width)))
    top = max(0, min(height - 1, round(y1 * height)))
    right = max(left + 1, min(width, round(x2 * width)))
    bottom = max(top + 1, min(height, round(y2 * height)))
    return left, top, right, bottom


def main() -> None:
    args = build_parser().parse_args()
    if args.min_side < 1:
        raise ValueError("min-side must be positive")

    manifest_path = Path(args.manifest).resolve()
    image_dir = Path(args.image_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    report_path = Path(args.report).resolve()
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    if document.get("version") != MANIFEST_VERSION:
        raise ValueError(f"manifest version must be {MANIFEST_VERSION}")
    prefix = str(document.get("sourceGroupPrefix", "")).strip()
    if not prefix:
        raise ValueError("sourceGroupPrefix is required")
    regions = document.get("regions")
    if not isinstance(regions, list) or not regions:
        raise ValueError("regions must be a non-empty list")

    output_dir.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    outputs: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []
    output_names: set[str] = set()

    for index, region in enumerate(regions, start=1):
        parent_file_name = region.get("parentFileName") if isinstance(region, dict) else None
        region_id = region.get("regionId") if isinstance(region, dict) else None
        try:
            if not isinstance(parent_file_name, str):
                raise ValueError("parentFileName is required")
            if not isinstance(region_id, str) or not SAFE_REGION_ID.fullmatch(region_id):
                raise ValueError("regionId must be lowercase letters/numbers/dash/underscore")
            box = normalized_box(region.get("box"))
            parent_path = resolve_parent(image_dir, parent_file_name)
            parent_key = hashlib.sha256(parent_file_name.encode("utf-8")).hexdigest()[:12]
            output_name = f"{parent_key}-{region_id}.png"
            if output_name in output_names:
                raise ValueError("duplicate parentFileName/regionId output")
            output_names.add(output_name)

            with Image.open(parent_path) as source:
                image = source.convert("RGB")
                coordinates = pixel_box(box, image.width, image.height)
                crop = image.crop(coordinates)
                parent_width, parent_height = image.size
            if min(crop.size) < args.min_side:
                raise ValueError(
                    f"cropped region minimum side {min(crop.size)} is below {args.min_side}"
                )
            output_path = output_dir / output_name
            crop.save(output_path, format="PNG", optimize=True)
            outputs.append(
                {
                    "parentFileName": parent_file_name,
                    "parentSha256": sha256_file(parent_path),
                    "parentSize": {"width": parent_width, "height": parent_height},
                    "regionId": region_id,
                    "normalizedBox": list(box),
                    "pixelBox": list(coordinates),
                    "outputFileName": output_name,
                    "outputSha256": sha256_file(output_path),
                    "outputSize": {"width": crop.width, "height": crop.height},
                    "sourceGroup": f"{prefix}:parent-{parent_key}",
                    "reviewRequired": True,
                }
            )
        except Exception as error:
            errors.append(
                {
                    "index": index,
                    "parentFileName": parent_file_name,
                    "regionId": region_id,
                    "message": str(error),
                }
            )

    report = {
        "ok": not errors and len(outputs) == len(regions),
        "version": MANIFEST_VERSION,
        "manifestPath": str(manifest_path),
        "imageDir": str(image_dir),
        "outputDir": str(output_dir),
        "requestedCount": len(regions),
        "completedCount": len(outputs),
        "errors": errors,
        "outputs": outputs,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    # Keep the persisted report readable while making stdout safe for legacy Windows code pages.
    print(json.dumps(report, ensure_ascii=True, indent=2))
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
