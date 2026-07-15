from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from PIL import Image, UnidentifiedImageError


FILE_PATTERN = re.compile(
    r"^nail_(?P<sequence>\d+)_(?P<note>.+)_(?P<image_index>\d+)\.(?:jpg|jpeg|png|webp)$",
    re.IGNORECASE,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a provenance-grouped, training-prohibited intake for newly collected real-photo candidates."
    )
    parser.add_argument("--audit", required=True)
    parser.add_argument("--root", required=True)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--output", required=True)
    return parser


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_source_group(batch_id: str, note_id: str) -> str:
    note_digest = hashlib.sha256(note_id.encode("utf-8")).hexdigest()[:16]
    return f"{batch_id}:note-{note_digest}"


def main() -> None:
    args = build_parser().parse_args()
    audit_path = Path(args.audit).resolve()
    root = Path(args.root).resolve()
    output_path = Path(args.output).resolve()
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    errors: list[str] = []

    if not root.is_dir():
        raise FileNotFoundError(f"candidate root not found: {root}")
    if not audit.get("ok") or audit.get("totals", {}).get("invalidImages") != 0:
        errors.append("corpus audit must pass with zero invalid images")
    if Path(str(audit.get("root", ""))).resolve() != root:
        errors.append("corpus audit root does not match candidate root")

    entries: list[dict[str, object]] = []
    seen_files: set[str] = set()
    source_groups: set[str] = set()
    for record in audit.get("images", []):
        relative = str(record.get("path", ""))
        file_name = Path(relative).name
        if relative != file_name:
            errors.append(f"candidate images must be flat files: {relative}")
            continue
        if file_name in seen_files:
            errors.append(f"duplicate candidate filename: {file_name}")
            continue
        seen_files.add(file_name)
        match = FILE_PATTERN.fullmatch(file_name)
        if not match:
            errors.append(f"candidate filename does not preserve note provenance: {file_name}")
            continue
        image_path = (root / file_name).resolve()
        if image_path.parent != root or not image_path.is_file():
            errors.append(f"candidate image is missing or unsafe: {file_name}")
            continue
        actual_sha256 = sha256_file(image_path)
        if actual_sha256 != record.get("sha256"):
            errors.append(f"candidate sha256 drift: {file_name}")
            continue
        try:
            with Image.open(image_path) as image:
                image.load()
                width, height = image.size
        except (OSError, ValueError, UnidentifiedImageError) as error:
            errors.append(f"candidate decode failed: {file_name}: {error}")
            continue
        if width != record.get("width") or height != record.get("height"):
            errors.append(f"candidate dimensions drift: {file_name}")
            continue

        source_group = stable_source_group(args.batch_id, match.group("note"))
        source_groups.add(source_group)
        entries.append(
            {
                "fileName": file_name,
                "sha256": actual_sha256,
                "dhash": record.get("dhash"),
                "width": width,
                "height": height,
                "sourceGroup": source_group,
                "sourceSequence": int(match.group("sequence")),
                "sourceImageIndex": int(match.group("image_index")),
                "sourceType": "real-photo-reference-candidate",
                "decision": "pending-visual-review-and-authorization",
                "trainingUse": "prohibited",
            }
        )

    expected = int(audit.get("totals", {}).get("validImages", 0))
    if len(entries) != expected:
        errors.append(f"expected {expected} audited images, built {len(entries)} intake entries")

    comparisons = audit.get("comparisons", {})
    document = {
        "schemaVersion": 1,
        "batchId": args.batch_id,
        "ok": not errors,
        "root": str(root),
        "auditPath": str(audit_path),
        "authorization": {
            "status": "pending-user-confirmation",
            "authorizedUses": [],
            "trainingUse": "prohibited",
        },
        "status": "candidate_inventory_pass_authorization_and_visual_review_pending"
        if not errors
        else "invalid",
        "counts": {
            "images": len(entries),
            "sourceGroups": len(source_groups),
            "batchExactDuplicateGroups": audit.get("totals", {}).get("exactDuplicateGroups", 0),
            "batchNearDuplicatePairs": audit.get("totals", {}).get("nearDuplicatePairs", 0),
            "referenceImages": comparisons.get("referenceImages", 0),
            "crossCorpusExactMatches": len(comparisons.get("exactMatches", [])),
            "crossCorpusNearMatches": len(comparisons.get("nearMatches", [])),
        },
        "errors": errors,
        "entries": entries,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(output_path),
                "ok": document["ok"],
                "status": document["status"],
                **document["counts"],
            },
            ensure_ascii=True,
        )
    )
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
