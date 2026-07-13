from __future__ import annotations

import argparse
import hashlib
import json
import re
import uuid
from pathlib import Path


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
XHS_NAME = re.compile(
    r"^(?P<title>.*)_(?P<sequence>\d+)_(?P<author>.+)_来自小红书网页版$"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_metadata(stem: str) -> dict[str, str | int | None]:
    match = XHS_NAME.match(stem)
    if not match:
        source_key = stem
        return {
            "sourceGroup": "file-" + hashlib.sha256(source_key.encode("utf-8")).hexdigest()[:12],
            "sourceTitle": None,
            "sourceAuthor": None,
            "sourceSequence": None,
        }

    title = match.group("title") or None
    author = match.group("author")
    source_key = f"{title or ''}|{author}"
    return {
        "sourceGroup": "xhs-" + hashlib.sha256(source_key.encode("utf-8")).hexdigest()[:12],
        "sourceTitle": title,
        "sourceAuthor": author,
        "sourceSequence": int(match.group("sequence")),
    }


def build_manifest(root: Path, prefix: str, min_width: int = 3) -> dict[str, object]:
    files = sorted(
        path for path in root.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )
    width = max(min_width, len(str(len(files))))
    entries: list[dict[str, object]] = []
    for index, path in enumerate(files, start=1):
        renamed = f"{prefix}_{index:0{width}d}{path.suffix.lower()}"
        entries.append(
            {
                "index": index,
                "originalName": path.name,
                "renamedName": renamed,
                "sha256": sha256_file(path),
                **source_metadata(path.stem),
            }
        )
    return {
        "schemaVersion": 1,
        "root": str(root),
        "prefix": prefix,
        "sequenceWidth": width,
        "count": len(entries),
        "entries": entries,
    }


def apply_rename(root: Path, manifest: dict[str, object]) -> None:
    entries = list(manifest["entries"])
    destinations = [root / str(entry["renamedName"]) for entry in entries]
    if len({path.name.casefold() for path in destinations}) != len(destinations):
        raise RuntimeError("generated destination names are not unique")

    source_names = {str(entry["originalName"]).casefold() for entry in entries}
    conflicts = [
        path.name for path in destinations
        if path.exists() and path.name.casefold() not in source_names
    ]
    if conflicts:
        raise FileExistsError("destination names already exist: " + ", ".join(conflicts))

    operation = uuid.uuid4().hex
    staged: list[tuple[Path, Path, Path]] = []
    try:
        for entry in entries:
            source = root / str(entry["originalName"])
            destination = root / str(entry["renamedName"])
            temporary = root / f".__rename_{operation}_{int(entry['index']):04d}{source.suffix.lower()}"
            source.rename(temporary)
            staged.append((source, temporary, destination))
        for _, temporary, destination in staged:
            temporary.rename(destination)
    except Exception:
        for source, temporary, destination in reversed(staged):
            current = destination if destination.exists() else temporary
            if current.exists() and not source.exists():
                current.rename(source)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rename an image corpus deterministically while preserving a source manifest."
    )
    parser.add_argument("--root", required=True)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--min-width",
        type=int,
        default=3,
        help="Minimum zero-padded sequence width (default: 3).",
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    output = Path(args.output).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"image corpus directory not found: {root}")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", args.prefix):
        raise ValueError("prefix must contain only lowercase ASCII letters, numbers, underscores or hyphens")
    if args.min_width < 1:
        raise ValueError("min-width must be at least 1")

    manifest = build_manifest(root, args.prefix, args.min_width)
    if not manifest["entries"]:
        raise RuntimeError(f"no supported images found in {root}")
    if args.apply:
        apply_rename(root, manifest)
        manifest["status"] = "applied"
    else:
        manifest["status"] = "dry-run"

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": manifest["status"],
                "count": manifest["count"],
                "output": str(output),
            },
            ensure_ascii=True,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
