#!/usr/bin/env python3
"""物化 candidate7 第二批待审源图候选，不授予训练或真值资格。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--prior-authorization", required=True, type=Path)
    parser.add_argument("--first-representatives", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--limit", type=int, default=48)
    parser.add_argument("--max-per-source-group", type=int, default=2)
    parser.add_argument("--min-visible-nails", type=int, default=4)
    parser.add_argument("--max-visible-nails", type=int, default=5)
    args = parser.parse_args()

    if args.output_dir.exists():
        raise ValueError(f"output directory already exists: {args.output_dir}")
    if args.limit < 1 or args.max_per_source_group < 1:
        raise ValueError("limit and max-per-source-group must be positive")
    if args.min_visible_nails < 1 or args.min_visible_nails > args.max_visible_nails:
        raise ValueError("invalid visible nail range")

    inventory = load_json(args.inventory)
    authorization = load_json(args.prior_authorization)
    representatives = load_json(args.first_representatives)
    if inventory.get("ok") is not True or authorization.get("ok") is not True:
        raise ValueError("inventory or prior authorization is not a passing report")

    excluded_hashes = {
        str(item["imageSha256"]) for item in authorization.get("authorizedItems", [])
    }
    excluded_hashes.update(
        str(item["imageSha256"]) for item in representatives.get("representatives", [])
    )
    candidates = []
    for item in inventory.get("items", []):
        visible_nails = int(item.get("fullyVisibleNails") or 0)
        if item.get("imageSha256") in excluded_hashes:
            continue
        if not args.min_visible_nails <= visible_nails <= args.max_visible_nails:
            continue
        candidates.append(item)
    candidates.sort(
        key=lambda item: (
            -int(item.get("fullyVisibleNails") or 0),
            -(int(item.get("width") or 0) * int(item.get("height") or 0)),
            str(item.get("sourceGroup") or ""),
            str(item.get("fileName") or ""),
        )
    )

    selected: list[dict] = []
    per_group: dict[str, int] = {}
    for item in candidates:
        source_group = str(item["sourceGroup"])
        if per_group.get(source_group, 0) >= args.max_per_source_group:
            continue
        selected.append(item)
        per_group[source_group] = per_group.get(source_group, 0) + 1
        if len(selected) == args.limit:
            break
    if len(selected) < args.limit:
        raise ValueError(f"only {len(selected)} candidates satisfy the frozen selection policy")

    args.output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{args.output_dir.name}-", dir=args.output_dir.parent))
    try:
        image_dir = staging / "images"
        image_dir.mkdir()
        outputs: list[dict] = []
        for index, item in enumerate(selected, start=1):
            source = Path(item["imagePath"]).resolve()
            if not source.is_file() or sha256_file(source) != item["imageSha256"]:
                raise ValueError(f"source image missing or hash drifted: {source}")
            target = image_dir / item["fileName"]
            method = "hardlink"
            try:
                os.link(source, target)
            except OSError:
                shutil.copy2(source, target)
                method = "copy"
            if sha256_file(target) != item["imageSha256"]:
                raise ValueError(f"materialized image hash mismatch: {target}")
            outputs.append({
                "reviewIndex": index,
                "fileName": item["fileName"],
                "imagePath": str(source),
                "workspacePath": str(args.output_dir / "images" / item["fileName"]),
                "imageSha256": item["imageSha256"],
                "width": item["width"],
                "height": item["height"],
                "sourceGroup": item["sourceGroup"],
                "fullyVisibleNails": item["fullyVisibleNails"],
                "materializationMethod": method,
                "sourceReview": "pending-original-resolution",
                "completeMaskReview": "not-started",
                "exactCandidate7TrainingAuthorization": "missing",
                "trainingUse": "prohibited",
            })
        report = {
            "schemaVersion": 1,
            "ok": True,
            "decision": "candidate7_secondary_source_candidates_pending_original_resolution_review",
            "inputs": {
                "inventory": str(args.inventory.resolve()),
                "inventorySha256": sha256_file(args.inventory),
                "priorAuthorization": str(args.prior_authorization.resolve()),
                "priorAuthorizationSha256": sha256_file(args.prior_authorization),
                "firstRepresentatives": str(args.first_representatives.resolve()),
                "firstRepresentativesSha256": sha256_file(args.first_representatives),
            },
            "policy": {
                "limit": args.limit,
                "maxPerSourceGroup": args.max_per_source_group,
                "visibleNailRange": [args.min_visible_nails, args.max_visible_nails],
                "modelInferenceUsedForSelection": False,
                "originalResolutionReviewRequired": True,
                "completeMaskReviewRequired": True,
                "exactCandidate7TrainingAuthorizationRequired": True,
                "trainingUse": "prohibited",
            },
            "counts": {
                "images": len(outputs),
                "sourceGroups": len({item["sourceGroup"] for item in outputs}),
                "expectedFullyVisibleNails": sum(int(item["fullyVisibleNails"]) for item in outputs),
            },
            "itemsSha256": canonical_sha256(outputs),
            "items": outputs,
            "errors": [],
        }
        (staging / "candidate-manifest.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(staging, args.output_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    print(json.dumps({"ok": True, "counts": report["counts"], "itemsSha256": report["itemsSha256"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
