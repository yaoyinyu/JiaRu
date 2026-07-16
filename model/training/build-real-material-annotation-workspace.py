from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build an external, hash-bound annotation workspace from a reviewed first-batch plan."
    )
    parser.add_argument("--plan", required=True)
    parser.add_argument("--authorization", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--target-shard-size", type=int, default=20)
    args = parser.parse_args()

    plan_path = Path(args.plan).resolve()
    authorization_path = Path(args.authorization).resolve()
    output_dir = Path(args.output_dir).resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"output directory must be absent or empty: {output_dir}")
    if args.target_shard_size < 1:
        raise ValueError("target shard size must be positive")

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    authorization = json.loads(authorization_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    if plan.get("ok") is not True or plan.get("decision") != "first_annotation_batch_plan_ready_mask_review_required":
        errors.append("a passing first annotation batch plan is required")
    if plan.get("inputs", {}).get("authorizationSha256") != sha256_file(authorization_path):
        errors.append("annotation plan does not bind the current authorization manifest")
    if authorization.get("ok") is not True or authorization.get("authorization", {}).get("decision") != "A":
        errors.append("a passing authorization decision A is required")

    root = Path(str(authorization.get("root", ""))).resolve()
    authorized_by_file = {
        str(item.get("fileName", "")): item for item in authorization.get("entries", [])
    }
    selected = [item for item in plan.get("items", []) if item.get("firstAnnotationBatch") is True]
    expected_count = int(plan.get("counts", {}).get("firstAnnotationBatchImages", -1))
    if len(selected) != expected_count:
        errors.append("first annotation batch count differs from the plan summary")

    by_group: dict[str, list[dict[str, object]]] = {}
    seen_files: set[str] = set()
    for item in selected:
        file_name = str(item.get("fileName", ""))
        authorized = authorized_by_file.get(file_name)
        if not file_name or file_name in seen_files:
            errors.append(f"duplicate or empty selected fileName: {file_name}")
            continue
        seen_files.add(file_name)
        if authorized is None:
            errors.append(f"selected file is missing from authorization: {file_name}")
            continue
        if item.get("assignedRole") != "train":
            errors.append(f"first annotation batch item is not assigned to train: {file_name}")
        if item.get("sha256") != authorized.get("sha256") or item.get("sourceGroup") != authorized.get("sourceGroup"):
            errors.append(f"selected identity differs from authorization: {file_name}")
        if item.get("trainingUse") != "prohibited" or item.get("annotationTruthStatus") != "not-started":
            errors.append(f"selected item has unsafe eligibility state: {file_name}")
        source_path = (root / file_name).resolve()
        if source_path.parent != root or not source_path.is_file() or sha256_file(source_path) != item.get("sha256"):
            errors.append(f"selected source image is missing, unsafe, or changed: {file_name}")
        group = str(item.get("sourceGroup", ""))
        by_group.setdefault(group, []).append(item)
    if errors:
        raise ValueError("; ".join(errors))

    ordered_groups = sorted(by_group.items(), key=lambda entry: entry[0])
    shards: list[list[dict[str, object]]] = []
    current: list[dict[str, object]] = []
    for _, items in ordered_groups:
        if current and len(current) + len(items) > args.target_shard_size:
            shards.append(current)
            current = []
        current.extend(sorted(items, key=lambda item: str(item["fileName"])))
    if current:
        shards.append(current)

    image_dir = output_dir / "images"
    shard_dir = output_dir / "shards"
    image_dir.mkdir(parents=True)
    shard_dir.mkdir(parents=True)
    materialized: list[dict[str, object]] = []
    link_methods: dict[str, int] = {}
    for shard_index, shard_items in enumerate(shards, start=1):
        shard_id = f"{shard_index:03d}"
        shard_rows: list[dict[str, object]] = []
        for item in shard_items:
            file_name = str(item["fileName"])
            source_path = root / file_name
            target_path = image_dir / file_name
            method = "hardlink"
            try:
                os.link(source_path, target_path)
            except OSError:
                shutil.copy2(source_path, target_path)
                method = "copy"
            if sha256_file(target_path) != item["sha256"]:
                raise RuntimeError(f"materialized image hash mismatch: {file_name}")
            link_methods[method] = link_methods.get(method, 0) + 1
            record = {
                "fileName": file_name,
                "sourcePath": str(source_path),
                "workspacePath": str(target_path),
                "sha256": item["sha256"],
                "sourceGroup": item["sourceGroup"],
                "assignedRole": "train",
                "expectedFullyVisibleNails": item.get("fullyVisibleNails"),
                "shardIndex": shard_index,
                "materializationMethod": method,
                "trainingUse": "prohibited",
                "annotationTruthStatus": "not-started",
            }
            materialized.append(record)
            shard_rows.append(record)
        shard_path = shard_dir / f"annotation-shard-{shard_id}.csv"
        with shard_path.open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(
                target,
                fieldnames=[
                    "fileName", "sha256", "sourceGroup", "expectedFullyVisibleNails",
                    "candidateCount", "reviewStatus", "issueCodes", "note",
                ],
            )
            writer.writeheader()
            for row in shard_rows:
                writer.writerow(
                    {
                        "fileName": row["fileName"],
                        "sha256": row["sha256"],
                        "sourceGroup": row["sourceGroup"],
                        "expectedFullyVisibleNails": row["expectedFullyVisibleNails"],
                        "candidateCount": "",
                        "reviewStatus": "",
                        "issueCodes": "",
                        "note": "",
                    }
                )

    manifest = {
        "schemaVersion": 1,
        "ok": True,
        "decision": "annotation_workspace_ready_candidate_only",
        "inputs": {
            "plan": str(plan_path),
            "planSha256": sha256_file(plan_path),
            "authorization": str(authorization_path),
            "authorizationSha256": sha256_file(authorization_path),
        },
        "policy": {
            "sourceGroupsRemainAtomicAcrossShards": True,
            "workspaceDoesNotApproveMasks": True,
            "workspaceDoesNotGrantTrainingUse": True,
            "originalResolutionReviewRequired": True,
            "workspaceMustRemainOutsideGit": True,
        },
        "imageDir": str(image_dir),
        "counts": {
            "images": len(materialized),
            "sourceGroups": len(by_group),
            "shards": len(shards),
            "expectedFullyVisibleNails": sum(
                int(item.get("expectedFullyVisibleNails") or 0) for item in materialized
            ),
            "materializationMethods": link_methods,
        },
        "shards": [
            {
                "index": index,
                "path": str(shard_dir / f"annotation-shard-{index:03d}.csv"),
                "sha256": sha256_file(shard_dir / f"annotation-shard-{index:03d}.csv"),
                "images": len(items),
                "sourceGroups": sorted({str(item["sourceGroup"]) for item in items}),
            }
            for index, items in enumerate(shards, start=1)
        ],
        "items": materialized,
        "errors": [],
    }
    manifest_path = output_dir / "annotation-workspace-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, **manifest["counts"]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
