from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def require_file(path: Path, label: str, errors: list[str]) -> None:
    if not path.is_file():
        errors.append(f"{label} is missing: {path}")


def priority_rank(row: dict[str, Any]) -> tuple[int, int, int, str]:
    candidate_count = int(row["candidateCount"])
    expected_count = int(row["expectedFullyVisibleNails"])
    suspect_count = int(row["geometrySuspectCount"])
    if candidate_count == 0:
        tier = 0
    elif candidate_count < expected_count:
        tier = 1
    elif suspect_count:
        tier = 2
    elif candidate_count > expected_count:
        tier = 3
    else:
        tier = 4
    return tier, candidate_count - expected_count, -suspect_count, str(row["fileName"])


def contain(path: Path, size: tuple[int, int]) -> Image.Image:
    with Image.open(path) as source:
        return ImageOps.contain(source.convert("RGB"), size, Image.Resampling.LANCZOS)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a hash-bound original-resolution mask review workspace for the first real annotation batch."
    )
    parser.add_argument("--workspace-manifest", required=True)
    parser.add_argument("--prelabel-audit", required=True)
    parser.add_argument("--sam-report", required=True)
    parser.add_argument("--geometry-audit", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--target-shard-size", type=int, default=20)
    parser.add_argument("--images-per-page", type=int, default=2)
    args = parser.parse_args()

    if args.target_shard_size < 1:
        raise ValueError("--target-shard-size must be positive")
    if args.images_per_page < 1 or args.images_per_page > 2:
        raise ValueError("--images-per-page must be 1 or 2")

    workspace_path = Path(args.workspace_manifest).resolve()
    prelabel_audit_path = Path(args.prelabel_audit).resolve()
    sam_report_path = Path(args.sam_report).resolve()
    geometry_audit_path = Path(args.geometry_audit).resolve()
    output_dir = Path(args.output_dir).resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"output directory must be absent or empty: {output_dir}")

    errors: list[str] = []
    for path, label in (
        (workspace_path, "workspace manifest"),
        (prelabel_audit_path, "prelabel audit"),
        (sam_report_path, "SAM report"),
        (geometry_audit_path, "geometry audit"),
    ):
        require_file(path, label, errors)
    if errors:
        raise ValueError("; ".join(errors))

    workspace = read_json(workspace_path)
    prelabel_audit = read_json(prelabel_audit_path)
    sam_report = read_json(sam_report_path)
    geometry_audit = read_json(geometry_audit_path)
    if workspace.get("ok") is not True or workspace.get("decision") != "annotation_workspace_ready_candidate_only":
        errors.append("a passing candidate-only annotation workspace is required")
    if prelabel_audit.get("ok") is not True or prelabel_audit.get("decision") != "prelabel_candidate_audit_pass_original_resolution_review_required":
        errors.append("a passing candidate-only prelabel audit is required")
    bound_workspace_hash = prelabel_audit.get("inputs", {}).get("workspaceManifestSha256")
    if bound_workspace_hash != sha256_file(workspace_path):
        errors.append("prelabel audit does not bind the current workspace manifest")
    if sam_report.get("ok") is not True or sam_report.get("decision") != "sam_candidate_only_not_training_truth":
        errors.append("a complete candidate-only SAM report is required")
    if sam_report.get("trainingUse") != "prohibited" or sam_report.get("originalResolutionReviewRequired") is not True:
        errors.append("SAM report does not preserve the training prohibition and visual review gate")
    if geometry_audit.get("decision") != "candidate_only_not_training_truth":
        errors.append("geometry audit must remain candidate-only")

    review_csv_path = Path(str(prelabel_audit.get("inputs", {}).get("reviewCsv", ""))).resolve()
    if not review_csv_path.is_file() or sha256_file(review_csv_path) != prelabel_audit.get("inputs", {}).get("reviewCsvSha256"):
        errors.append("bound prelabel review CSV is missing or changed")
        prelabel_rows: list[dict[str, str]] = []
    else:
        with review_csv_path.open("r", encoding="utf-8-sig", newline="") as source:
            prelabel_rows = list(csv.DictReader(source))

    workspace_items = {str(item.get("fileName", "")): item for item in workspace.get("items", [])}
    sam_outputs = {str(item.get("fileName", "")): item for item in sam_report.get("outputs", [])}
    geometry_by_file: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in geometry_audit.get("rows", []):
        geometry_by_file[str(row.get("fileName", ""))].append(row)
    if len(workspace_items) != int(workspace.get("counts", {}).get("images", -1)):
        errors.append("workspace item count differs from its summary")
    if set(workspace_items) != {str(row.get("fileName", "")) for row in prelabel_rows}:
        errors.append("prelabel review CSV does not exactly cover the workspace")
    if set(workspace_items) != set(sam_outputs):
        errors.append("SAM outputs do not exactly cover the workspace")

    rows: list[dict[str, Any]] = []
    for prelabel_row in prelabel_rows:
        file_name = prelabel_row["fileName"]
        item = workspace_items[file_name]
        sam_output = sam_outputs.get(file_name, {})
        image_path = Path(str(item.get("workspacePath", ""))).resolve()
        annotation_path = Path(str(sam_output.get("annotationPath", ""))).resolve()
        overlay_path = Path(str(sam_output.get("overlayPath", ""))).resolve()
        if not image_path.is_file() or sha256_file(image_path) != item.get("sha256"):
            errors.append(f"workspace image is missing or changed: {file_name}")
        require_file(annotation_path, f"annotation for {file_name}", errors)
        require_file(overlay_path, f"overlay for {file_name}", errors)
        if sam_output.get("sourceGroup") != item.get("sourceGroup"):
            errors.append(f"SAM source group differs from workspace: {file_name}")
        annotation = read_json(annotation_path) if annotation_path.is_file() else {}
        if annotation.get("trainingUse") != "prohibited" or annotation.get("decision") != "candidate_only_not_training_truth":
            errors.append(f"annotation is not safely candidate-only: {file_name}")
        if annotation.get("image", {}).get("fileName") != file_name or annotation.get("image", {}).get("sourceGroup") != item.get("sourceGroup"):
            errors.append(f"annotation image identity differs from workspace: {file_name}")
        geometry_rows = geometry_by_file.get(file_name, [])
        candidate_count = int(sam_output.get("polygonCount", -1))
        if candidate_count != len(annotation.get("annotations", [])) or candidate_count != int(prelabel_row["candidateCount"]):
            errors.append(f"candidate count differs across evidence: {file_name}")
        if len(geometry_rows) != candidate_count:
            errors.append(f"geometry audit count differs from candidates: {file_name}")
        suspect_rows = [row for row in geometry_rows if row.get("status") == "suspect"]
        reason_codes = sorted({reason for row in suspect_rows for reason in row.get("reasons", [])})
        row = {
            "fileName": file_name,
            "sha256": item.get("sha256"),
            "sourceGroup": item.get("sourceGroup"),
            "expectedFullyVisibleNails": int(item.get("expectedFullyVisibleNails") or 0),
            "candidateCount": candidate_count,
            "countDelta": candidate_count - int(item.get("expectedFullyVisibleNails") or 0),
            "geometrySuspectCount": len(suspect_rows),
            "geometryIssueCodes": ";".join(reason_codes),
            "prelabelReviewPriority": prelabel_row.get("reviewPriority", ""),
            "annotationPath": str(annotation_path),
            "annotationSha256": sha256_file(annotation_path) if annotation_path.is_file() else "",
            "overlayPath": str(overlay_path),
            "overlaySha256": sha256_file(overlay_path) if overlay_path.is_file() else "",
            "trainingUse": "prohibited",
            "annotationTruthStatus": "candidate-only",
        }
        row["riskRank"] = priority_rank(row)[0]
        rows.append(row)
    if errors:
        raise ValueError("; ".join(errors))

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row["sourceGroup"])].append(row)
    ordered_groups = sorted(
        groups.items(),
        key=lambda entry: (min(priority_rank(row) for row in entry[1]), entry[0]),
    )
    shards: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for _, group_rows in ordered_groups:
        ordered_rows = sorted(group_rows, key=priority_rank)
        if current and len(current) + len(ordered_rows) > args.target_shard_size:
            shards.append(current)
            current = []
        current.extend(ordered_rows)
    if current:
        shards.append(current)

    shard_dir = output_dir / "shards"
    sheet_dir = output_dir / "sheets"
    shard_dir.mkdir(parents=True)
    sheet_dir.mkdir(parents=True)
    fieldnames = [
        "fileName", "sha256", "sourceGroup", "expectedFullyVisibleNails", "candidateCount",
        "countDelta", "geometrySuspectCount", "geometryIssueCodes", "riskRank",
        "annotationSha256", "overlaySha256", "reviewStatus", "finalCompleteMaskCount",
        "issueCodes", "keepPromptIndices", "dropPromptIndices", "addPromptBoxesJson", "note",
    ]
    font = ImageFont.load_default()
    shard_reports: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []
    for shard_index, shard_rows in enumerate(shards, start=1):
        csv_path = shard_dir / f"mask-review-{shard_index:03d}.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=fieldnames)
            writer.writeheader()
            for row in shard_rows:
                writer.writerow({
                    **{key: row.get(key, "") for key in fieldnames},
                    "reviewStatus": "",
                    "finalCompleteMaskCount": "",
                    "issueCodes": "",
                    "keepPromptIndices": "",
                    "dropPromptIndices": "",
                    "addPromptBoxesJson": "",
                    "note": "",
                })
        shard_reports.append({
            "index": shard_index,
            "path": str(csv_path),
            "sha256": sha256_file(csv_path),
            "images": len(shard_rows),
            "sourceGroups": sorted({str(row["sourceGroup"]) for row in shard_rows}),
            "riskCounts": {str(rank): sum(int(row["riskRank"]) == rank for row in shard_rows) for rank in range(5)},
        })

        for start in range(0, len(shard_rows), args.images_per_page):
            page_index = start // args.images_per_page + 1
            canvas = Image.new("RGB", (2200, 1900), "white")
            draw = ImageDraw.Draw(canvas)
            draw.text((24, 16), f"Mask review shard {shard_index:03d} page {page_index:03d} | original left, SAM overlay right", fill="black", font=font)
            for offset, row in enumerate(shard_rows[start : start + args.images_per_page]):
                y = 65 + offset * 900
                original = contain(Path(str(workspace_items[row["fileName"]]["workspacePath"])), (1040, 760))
                overlay = contain(Path(str(row["overlayPath"])), (1040, 760))
                canvas.paste(original, (24 + (1040 - original.width) // 2, y + (760 - original.height) // 2))
                canvas.paste(overlay, (1136 + (1040 - overlay.width) // 2, y + (760 - overlay.height) // 2))
                group_suffix = str(row["sourceGroup"]).rsplit(":", 1)[-1]
                label = (
                    f"{start + offset + 1:03d} {row['fileName']} | source {group_suffix} | "
                    f"expected {row['expectedFullyVisibleNails']} candidate {row['candidateCount']} "
                    f"delta {row['countDelta']:+d} suspect {row['geometrySuspectCount']} risk {row['riskRank']}"
                )
                draw.text((24, y + 772), label, fill="black", font=font)
            page_path = sheet_dir / f"mask-review-{shard_index:03d}-page-{page_index:03d}.jpg"
            canvas.save(page_path, quality=94)
            pages.append({
                "shardIndex": shard_index,
                "pageIndex": page_index,
                "path": str(page_path),
                "sha256": sha256_file(page_path),
                "startRow": start + 1,
                "endRow": min(start + args.images_per_page, len(shard_rows)),
            })

    report = {
        "schemaVersion": 1,
        "ok": True,
        "decision": "first_annotation_mask_review_workspace_ready_original_resolution_review_required",
        "inputs": {
            "workspaceManifest": str(workspace_path),
            "workspaceManifestSha256": sha256_file(workspace_path),
            "prelabelAudit": str(prelabel_audit_path),
            "prelabelAuditSha256": sha256_file(prelabel_audit_path),
            "prelabelReviewCsv": str(review_csv_path),
            "prelabelReviewCsvSha256": sha256_file(review_csv_path),
            "samReport": str(sam_report_path),
            "samReportSha256": sha256_file(sam_report_path),
            "geometryAudit": str(geometry_audit_path),
            "geometryAuditSha256": sha256_file(geometry_audit_path),
        },
        "policy": {
            "sourceGroupsRemainAtomicAcrossShards": True,
            "contactSheetsAreNavigationOnly": True,
            "originalResolutionReviewRequired": True,
            "reviewWorkspaceDoesNotApproveMasks": True,
            "trainingUse": "prohibited",
            "promptIndicesAreOneBased": True,
        },
        "counts": {
            "images": len(rows),
            "sourceGroups": len(groups),
            "expectedFullyVisibleNails": sum(int(row["expectedFullyVisibleNails"]) for row in rows),
            "candidatePolygons": sum(int(row["candidateCount"]) for row in rows),
            "geometrySuspects": sum(int(row["geometrySuspectCount"]) for row in rows),
            "zeroCandidateImages": sum(int(row["candidateCount"]) == 0 for row in rows),
            "shards": len(shards),
            "pages": len(pages),
        },
        "riskLegend": {
            "0": "zero candidates",
            "1": "candidate count below expected",
            "2": "geometry suspect at or above expected count",
            "3": "candidate count above expected",
            "4": "count matches and no geometry suspect",
        },
        "shards": shard_reports,
        "pages": pages,
        "errors": [],
    }
    report_path = output_dir / "mask-review-workspace-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, **report["counts"]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
