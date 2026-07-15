from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image, UnidentifiedImageError


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".avif", ".heic"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def difference_hash(image: Image.Image, size: int = 8) -> str:
    grayscale = image.convert("L").resize((size + 1, size))
    pixels = list(grayscale.get_flattened_data())
    bits = 0
    for y in range(size):
        for x in range(size):
            left = pixels[y * (size + 1) + x]
            right = pixels[y * (size + 1) + x + 1]
            bits = (bits << 1) | int(left > right)
    return f"{bits:0{size * size // 4}x}"


def hamming_distance(left: str, right: str) -> int:
    return (int(left, 16) ^ int(right, 16)).bit_count()


def print_json(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=True, indent=2))


def audit_comparisons(
    candidates: list[dict[str, object]],
    compare_roots: list[Path],
    near_duplicate_distance: int,
) -> dict[str, object]:
    reference_records: list[dict[str, object]] = []
    invalid_references: list[dict[str, str]] = []
    by_root: Counter[str] = Counter()

    for root in compare_roots:
        for path in sorted(
            item for item in root.rglob("*")
            if item.is_file() and item.suffix.lower() in IMAGE_SUFFIXES
        ):
            relative = path.relative_to(root).as_posix()
            try:
                digest = sha256_file(path)
                with Image.open(path) as image:
                    image.load()
                    perceptual_hash = difference_hash(image)
                reference_records.append(
                    {
                        "root": str(root),
                        "path": relative,
                        "sha256": digest,
                        "dhash": perceptual_hash,
                    }
                )
                by_root[str(root)] += 1
            except (OSError, ValueError, UnidentifiedImageError) as error:
                invalid_references.append(
                    {"root": str(root), "path": relative, "error": str(error)}
                )

    exact_matches: list[dict[str, object]] = []
    near_matches: list[dict[str, object]] = []
    for candidate in candidates:
        for reference in reference_records:
            if candidate["sha256"] == reference["sha256"]:
                exact_matches.append(
                    {
                        "candidate": candidate["path"],
                        "referenceRoot": reference["root"],
                        "reference": reference["path"],
                    }
                )
                continue
            distance = hamming_distance(str(candidate["dhash"]), str(reference["dhash"]))
            if distance <= near_duplicate_distance:
                near_matches.append(
                    {
                        "candidate": candidate["path"],
                        "referenceRoot": reference["root"],
                        "reference": reference["path"],
                        "distance": distance,
                    }
                )

    return {
        "roots": [str(root) for root in compare_roots],
        "referenceImages": len(reference_records),
        "referenceImagesByRoot": dict(sorted(by_root.items())),
        "invalidReferences": invalid_references,
        "exactMatches": exact_matches,
        "nearMatches": near_matches,
    }


def audit_corpus(
    root: Path,
    near_duplicate_distance: int,
    compare_roots: list[Path] | None = None,
) -> dict[str, object]:
    files = sorted(
        path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )
    records: list[dict[str, object]] = []
    invalid: list[dict[str, str]] = []
    exact_groups: dict[str, list[str]] = defaultdict(list)

    for path in files:
        relative = path.relative_to(root).as_posix()
        try:
            digest = sha256_file(path)
            with Image.open(path) as image:
                image.load()
                width, height = image.size
                image_format = image.format or path.suffix.lstrip(".").upper()
                perceptual_hash = difference_hash(image)
            exact_groups[digest].append(relative)
            records.append(
                {
                    "path": relative,
                    # A flat corpus should be summarized as one root bucket rather
                    # than creating one pseudo-directory bucket per filename.
                    "topLevelDirectory": relative.split("/", 1)[0] if "/" in relative else ".",
                    "bytes": path.stat().st_size,
                    "width": width,
                    "height": height,
                    "format": image_format,
                    "sha256": digest,
                    "dhash": perceptual_hash,
                }
            )
        except (OSError, ValueError, UnidentifiedImageError) as error:
            invalid.append({"path": relative, "error": str(error)})

    exact_duplicates = [paths for paths in exact_groups.values() if len(paths) > 1]
    near_duplicates: list[dict[str, object]] = []
    for left_index, left in enumerate(records):
        for right in records[left_index + 1 :]:
            if left["sha256"] == right["sha256"]:
                continue
            distance = hamming_distance(str(left["dhash"]), str(right["dhash"]))
            if distance <= near_duplicate_distance:
                near_duplicates.append(
                    {"left": left["path"], "right": right["path"], "distance": distance}
                )

    by_top_level = Counter(str(record["topLevelDirectory"]) for record in records)
    resolutions = Counter(f'{record["width"]}x{record["height"]}' for record in records)
    report: dict[str, object] = {
        "ok": not invalid,
        "root": str(root),
        "totals": {
            "files": len(files),
            "validImages": len(records),
            "invalidImages": len(invalid),
            "exactDuplicateGroups": len(exact_duplicates),
            "exactDuplicateFiles": sum(len(group) - 1 for group in exact_duplicates),
            "nearDuplicatePairs": len(near_duplicates),
        },
        "byTopLevelDirectory": dict(sorted(by_top_level.items())),
        "topResolutions": [
            {"resolution": resolution, "count": count}
            for resolution, count in resolutions.most_common(20)
        ],
        "invalid": invalid,
        "exactDuplicateGroups": exact_duplicates,
        "nearDuplicatePairs": near_duplicates,
        "images": records,
    }
    if compare_roots:
        report["comparisons"] = audit_comparisons(
            records, compare_roots, near_duplicate_distance
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit an image corpus before dataset intake.")
    parser.add_argument("--root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--near-duplicate-distance", type=int, default=2)
    parser.add_argument(
        "--compare-root",
        action="append",
        default=[],
        help="Reference image root used for exact and near-duplicate leakage checks. Repeatable.",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    output = Path(args.output).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"image corpus directory not found: {root}")
    if args.near_duplicate_distance < 0 or args.near_duplicate_distance > 16:
        raise ValueError("near-duplicate-distance must be between 0 and 16")
    compare_roots = [Path(value).resolve() for value in args.compare_root]
    missing_compare_roots = [str(path) for path in compare_roots if not path.is_dir()]
    if missing_compare_roots:
        raise FileNotFoundError(
            "compare image corpus directory not found: " + ", ".join(missing_compare_roots)
        )

    report = audit_corpus(root, args.near_duplicate_distance, compare_roots)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print_json({key: report[key] for key in ("ok", "root", "totals", "byTopLevelDirectory")})
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
