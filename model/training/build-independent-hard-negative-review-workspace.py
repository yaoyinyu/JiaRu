#!/usr/bin/env python3
"""Build a hash-bound original-resolution review workspace for AI hard negatives.

The workspace is candidate-only. It verifies the user's authorization, the
machine inventory, every current image byte, and identity isolation from the
protected train/validation/frozen-test roles. Review sheets preserve every
source pixel at 1:1 scale; they are navigation aids and never replace the
bound source files.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
FILE_PATTERN = re.compile(
    r"^hard_negative_independent_\d{8}_(?P<sequence>\d{3})_"
    r"(?P<family>[a-z0-9_]+)_(?P<variant>\d{2})\.(?P<suffix>png|jpe?g|webp)$",
    re.IGNORECASE,
)
CSV_FIELDS = (
    "reviewId",
    "fileName",
    "imageSha256",
    "width",
    "height",
    "sourceGroup",
    "decision",
    "defectCodes",
    "notes",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is unreadable JSON: {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain an object: {path}")
    return value


def require_sha256(value: Any, label: str) -> str:
    result = str(value or "")
    if not SHA256_PATTERN.fullmatch(result):
        raise ValueError(f"{label} is not a lowercase SHA-256")
    return result


def decode_image(path: Path) -> tuple[int, int, str]:
    try:
        with Image.open(path) as image:
            image_format = str(image.format or "").upper()
            width, height = image.size
            image.verify()
        with Image.open(path) as image:
            image.load()
            if image.size != (width, height):
                raise ValueError("image dimensions changed during decode")
    except (OSError, SyntaxError, UnidentifiedImageError) as error:
        raise ValueError(f"image cannot be fully decoded: {path}: {error}") from error
    if path.suffix.lower() not in IMAGE_SUFFIXES:
        raise ValueError(f"unsupported image suffix: {path}")
    if min(width, height) < 320:
        raise ValueError(f"image minimum side is below 320px: {path}")
    return width, height, image_format


def collect_identity_values(value: Any) -> dict[str, set[str]]:
    result = {"fileNames": set(), "imageSha256": set(), "sourceGroups": set()}

    def visit(item: Any) -> None:
        if isinstance(item, list):
            for child in item:
                visit(child)
            return
        if not isinstance(item, dict):
            return
        for key, child in item.items():
            if isinstance(child, str) and child:
                if key in {"fileName", "sourceFileName", "originalFileName"}:
                    result["fileNames"].add(child.casefold())
                elif key in {"imageSha256", "sourceImageSha256", "sha256"}:
                    if SHA256_PATTERN.fullmatch(child):
                        result["imageSha256"].add(child)
                elif key in {"sourceGroup", "parentSourceGroup"}:
                    result["sourceGroups"].add(child)
            if isinstance(child, (dict, list)):
                visit(child)

    visit(value)
    return result


def validate_authorization(
    authorization_path: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    authorization = read_json(authorization_path, "authorization evidence")
    if (
        authorization.get("ok") is not True
        or authorization.get("decision") != "A"
        or authorization.get("status") != "confirmed"
        or authorization.get("currentTrainingUse") != "prohibited"
    ):
        raise ValueError("authorization is not a confirmed candidate-only A decision")
    authorized_uses = list(authorization.get("authorizedUses") or [])
    for required in ("commercial-model-training", "long-term-regression"):
        if required not in authorized_uses:
            raise ValueError(f"authorization does not include {required}")
    if authorization.get("qualityConstraint") != "authorization-does-not-relax-quality-gates":
        raise ValueError("authorization does not preserve the quality gate")
    if (
        authorization.get("roleConstraint")
        != "authorization-does-not-assign-train-validation-or-holdout-role"
    ):
        raise ValueError("authorization does not preserve role isolation")
    entries = authorization.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("authorization entries are missing")
    if canonical_sha256(entries) != require_sha256(
        authorization.get("entriesSha256"), "authorization entriesSha256"
    ):
        raise ValueError("authorization entries SHA-256 drift")
    return authorization, entries


def render_sheets(
    items: list[dict[str, Any]],
    output_dir: Path,
    overwrite: bool,
) -> list[dict[str, Any]]:
    sheets_dir = output_dir / "review-sheets-1x"
    sheets_dir.mkdir(parents=True, exist_ok=True)
    font = ImageFont.load_default()
    margin = 16
    label_height = 42
    columns = 2
    rows = 2
    max_width = max(int(item["width"]) for item in items)
    max_height = max(int(item["height"]) for item in items)
    cell_width = max_width + margin * 2
    cell_height = max_height + label_height + margin * 2
    sheet_records: list[dict[str, Any]] = []

    for offset in range(0, len(items), columns * rows):
        batch = items[offset : offset + columns * rows]
        sheet_number = offset // (columns * rows) + 1
        sheet_path = sheets_dir / f"review-sheet-{sheet_number:03d}.png"
        if sheet_path.exists() and not overwrite:
            raise ValueError(f"refusing to overwrite review sheet: {sheet_path}")
        canvas = Image.new(
            "RGB",
            (columns * cell_width, rows * cell_height),
            (235, 235, 235),
        )
        draw = ImageDraw.Draw(canvas)
        sheet_items: list[dict[str, Any]] = []
        for index, item in enumerate(batch):
            column = index % columns
            row = index // columns
            left = column * cell_width + margin
            top = row * cell_height + margin
            label = f"{item['reviewId']}  {item['fileName']}  {item['width']}x{item['height']}"
            draw.text((left, top), label, fill=(0, 0, 0), font=font)
            image_top = top + label_height
            with Image.open(Path(str(item["sourcePath"]))) as source:
                source.load()
                rendered = source.convert("RGB")
                canvas.paste(rendered, (left, image_top))
            sheet_items.append(
                {
                    "reviewId": item["reviewId"],
                    "fileName": item["fileName"],
                    "imageSha256": item["imageSha256"],
                    "pixelScale": "1:1-no-resampling",
                    "pasteBox": [
                        left,
                        image_top,
                        left + int(item["width"]),
                        image_top + int(item["height"]),
                    ],
                }
            )
        canvas.save(sheet_path, format="PNG", optimize=True)
        sheet_records.append(
            {
                "sheetNumber": sheet_number,
                "path": str(sheet_path),
                "sha256": sha256_file(sheet_path),
                "width": canvas.width,
                "height": canvas.height,
                "items": sheet_items,
            }
        )
    return sheet_records


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a strict original-resolution hard-negative review workspace."
    )
    parser.add_argument("--authorization", required=True)
    parser.add_argument("--machine-audit", required=True)
    parser.add_argument("--train-index", required=True)
    parser.add_argument("--val-index", required=True)
    parser.add_argument("--frozen-test-manifest", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    authorization_path = Path(args.authorization).resolve()
    machine_audit_path = Path(args.machine_audit).resolve()
    output_dir = Path(args.output_dir).resolve()
    report_path = output_dir / "review-workspace-v1.json"
    decisions_path = output_dir / "review-decisions-v1.csv"
    if (report_path.exists() or decisions_path.exists()) and not args.overwrite:
        raise ValueError(f"refusing to overwrite existing workspace: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    authorization, authorization_entries = validate_authorization(authorization_path)
    audit = read_json(machine_audit_path, "machine audit")
    records = audit.get("records")
    if (
        audit.get("decodedCount") != len(authorization_entries)
        or audit.get("decodeFailures")
        or not isinstance(records, list)
        or len(records) != len(authorization_entries)
    ):
        raise ValueError("machine audit does not cover every authorized decoded image")
    audit_by_name = {
        str(item.get("fileName")): item for item in records if isinstance(item, dict)
    }
    authorization_by_name = {
        str(item.get("fileName")): item
        for item in authorization_entries
        if isinstance(item, dict)
    }
    if (
        len(audit_by_name) != len(records)
        or len(authorization_by_name) != len(authorization_entries)
        or set(audit_by_name) != set(authorization_by_name)
    ):
        raise ValueError("machine audit and authorization file coverage differ")

    protected_paths = {
        "train": Path(args.train_index).resolve(),
        "val": Path(args.val_index).resolve(),
        "frozenTest": Path(args.frozen_test_manifest).resolve(),
    }
    protected_inputs: dict[str, dict[str, str]] = {}
    protected_identities: dict[str, dict[str, set[str]]] = {}
    for role, path in protected_paths.items():
        document = read_json(path, f"{role} evidence")
        protected_inputs[role] = {"path": str(path), "sha256": sha256_file(path)}
        protected_identities[role] = collect_identity_values(document)

    items: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    source_groups: set[str] = set()
    total_matches = 0
    for sequence, file_name in enumerate(sorted(authorization_by_name), start=1):
        match = FILE_PATTERN.fullmatch(file_name)
        if not match:
            raise ValueError(f"file name does not match the independent-batch contract: {file_name}")
        authorized = authorization_by_name[file_name]
        audited = audit_by_name[file_name]
        image_hash = require_sha256(authorized.get("sha256"), f"{file_name} authorization hash")
        if image_hash != require_sha256(audited.get("sha256"), f"{file_name} audit hash"):
            raise ValueError(f"{file_name}: authorization and audit hashes differ")
        source_path = Path(str(authorized.get("sourcePath") or "")).resolve()
        if source_path.name != file_name or not source_path.is_file():
            raise ValueError(f"{file_name}: authorized source path is missing or mismatched")
        if sha256_file(source_path) != image_hash:
            raise ValueError(f"{file_name}: source image SHA-256 drift")
        if image_hash in seen_hashes:
            raise ValueError(f"duplicate authorized image SHA-256: {image_hash}")
        seen_hashes.add(image_hash)
        width, height, image_format = decode_image(source_path)
        if width != int(audited.get("width", -1)) or height != int(audited.get("height", -1)):
            raise ValueError(f"{file_name}: current dimensions differ from machine audit")

        family = match.group("family").lower()
        source_group = f"ai-hard-negative-independent-2026-07-24:{family}"
        source_groups.add(source_group)
        matches: dict[str, int] = {}
        for role, identities in protected_identities.items():
            count = int(file_name.casefold() in identities["fileNames"])
            count += int(image_hash in identities["imageSha256"])
            count += int(source_group in identities["sourceGroups"])
            matches[f"{role}IdentityMatches"] = count
            total_matches += count
        items.append(
            {
                "reviewId": f"hn-review-{sequence:03d}",
                "fileName": file_name,
                "sourcePath": str(source_path),
                "imageSha256": image_hash,
                "width": width,
                "height": height,
                "imageFormat": image_format,
                "promptFamily": family,
                "promptVariant": int(match.group("variant")),
                "sourceGroup": source_group,
                "authorizationEntryMatched": True,
                "machineAuditEntryMatched": True,
                "sourceIsolationEvidence": {
                    **matches,
                    "isolated": all(value == 0 for value in matches.values()),
                },
                "trainingUse": "prohibited",
                "reviewStatus": "pending-original-resolution-review",
            }
        )
    if total_matches:
        raise ValueError(f"authorized images overlap protected roles: matches={total_matches}")

    sheets = render_sheets(items, output_dir, args.overwrite)
    with decisions_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for item in items:
            writer.writerow(
                {
                    "reviewId": item["reviewId"],
                    "fileName": item["fileName"],
                    "imageSha256": item["imageSha256"],
                    "width": item["width"],
                    "height": item["height"],
                    "sourceGroup": item["sourceGroup"],
                    "decision": "",
                    "defectCodes": "",
                    "notes": "",
                }
            )

    generated_at = datetime.now(timezone.utc).isoformat()
    report = {
        "schemaVersion": 1,
        "generatedAt": generated_at,
        "ok": True,
        "decision": "review_workspace_ready_no_quality_decisions",
        "inputs": {
            "authorization": {
                "path": str(authorization_path),
                "sha256": sha256_file(authorization_path),
                "entriesSha256": authorization["entriesSha256"],
            },
            "machineAudit": {
                "path": str(machine_audit_path),
                "sha256": sha256_file(machine_audit_path),
            },
            "protectedRoles": protected_inputs,
        },
        "policy": {
            "aiOriginDoesNotRelaxQualityGate": True,
            "reviewEveryImageAtOriginalResolution": True,
            "reviewSheetsUseSourcePixelsWithoutResampling": True,
            "reviewSheetsDoNotReplaceBoundSourceFiles": True,
            "rejectLowQualityOrBlur": True,
            "rejectImpossibleOrIncompleteTopology": True,
            "rejectValidHumanManicureSurfaceAnywhere": True,
            "rejectCollageTemplateOrIndependentNailTips": True,
            "authorizationDoesNotAssignTrainingRole": True,
            "trainingUseBeforeFinalization": "prohibited",
        },
        "summary": {
            "authorizedImages": len(items),
            "pendingReviewImages": len(items),
            "promptFamilies": len(source_groups),
            "protectedRoleIdentityMatches": total_matches,
            "reviewSheets": len(sheets),
        },
        "decisionsTemplate": {
            "path": str(decisions_path),
            "sha256": sha256_file(decisions_path),
            "encoding": "utf-8-sig",
            "fields": list(CSV_FIELDS),
        },
        "itemsSha256": canonical_sha256(items),
        "items": items,
        "reviewSheetsSha256": canonical_sha256(sheets),
        "reviewSheets": sheets,
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "ok": True,
                "reviewWorkspace": str(report_path),
                "reviewWorkspaceSha256": sha256_file(report_path),
                "decisionsTemplate": str(decisions_path),
                "images": len(items),
                "promptFamilies": len(source_groups),
                "reviewSheets": len(sheets),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
