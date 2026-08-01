#!/usr/bin/env python3
"""Select a diverse positive-reinforcement batch and build its exact authorization request."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


QUOTAS = {"visible-1-4": 25, "visible-6-9": 5, "visible-10": 40, "visible-5": 90}
MAX_PER_SOURCE_GROUP = 3


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="Build an exact positive training authorization request.")
    value.add_argument("--inventory")
    value.add_argument("--output")
    value.add_argument("--verify-report")
    return value


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def stratum(visible_nails: int) -> str | None:
    if 1 <= visible_nails <= 4:
        return "visible-1-4"
    if visible_nails == 5:
        return "visible-5"
    if 6 <= visible_nails <= 9:
        return "visible-6-9"
    if visible_nails == 10:
        return "visible-10"
    return None


def select_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pools: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        bucket = stratum(int(item.get("fullyVisibleNails") or 0))
        if bucket:
            pools[bucket].append(item)
    for bucket in pools:
        pools[bucket].sort(key=lambda item: (item["imageSha256"], item["fileName"]))

    selected: list[dict[str, Any]] = []
    group_counts: dict[str, int] = defaultdict(int)
    for bucket, quota in QUOTAS.items():
        pool = pools.get(bucket, [])
        available = list(pool)
        bucket_selected: list[dict[str, Any]] = []
        while len(bucket_selected) < quota:
            eligible = [item for item in available if group_counts[item["sourceGroup"]] < MAX_PER_SOURCE_GROUP]
            if not eligible:
                raise ValueError(f"Insufficient candidates for {bucket}: need {quota}, found {len(bucket_selected)}")
            minimum_group_count = min(group_counts[item["sourceGroup"]] for item in eligible)
            item = next(item for item in eligible if group_counts[item["sourceGroup"]] == minimum_group_count)
            available.remove(item)
            group_counts[item["sourceGroup"]] += 1
            bucket_selected.append(item)
        selected.extend(bucket_selected)
    selected.sort(key=lambda item: (item["sourceGroup"], item["fileName"]))
    return selected


def build_report(inventory_path: Path) -> dict[str, Any]:
    inventory = load_object(inventory_path)
    if inventory.get("ok") is not True or inventory.get("decision") != "candidate_inventory_ready_for_original_resolution_review":
        raise ValueError("Candidate inventory is not approved for selection")
    if inventory.get("policy", {}).get("trainingUse") != "prohibited":
        raise ValueError("Candidate inventory must remain training prohibited")
    items = inventory.get("items")
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise ValueError("Inventory items are invalid")
    if canonical_sha256(items) != inventory.get("itemsSha256"):
        raise ValueError("Inventory items digest mismatch")
    selected = select_items(items)
    requested_items = [
        {
            "fileName": item["fileName"],
            "imagePath": item["imagePath"],
            "imageSha256": item["imageSha256"],
            "width": item["width"],
            "height": item["height"],
            "sourceGroup": item["sourceGroup"],
            "fullyVisibleNails": item["fullyVisibleNails"],
            "sourceQualityReview": item["sourceQualityReview"],
            "completeMaskReview": "not-started",
            "trainingUse": "prohibited",
        }
        for item in selected
    ]
    items_sha = canonical_sha256(requested_items)
    request_id = "candidate6-positive-reinforcement-v1"
    authorization_text = (
        f"我授权 {request_id} 的160张精确文件清单（requestedItemsSha256={items_sha}）"
        "用于商业模型训练、长期回归、模型诊断评估和数据质量审核；授权不放宽源图、完整甲面mask、"
        "来源隔离、val30校准、冻结test100、独立困难负样本留出或发布质量门。"
    )
    return {
        "schemaVersion": 1,
        "ok": True,
        "decision": "exact_positive_training_authorization_required",
        "requestId": request_id,
        "inputs": {"inventory": str(inventory_path), "inventorySha256": sha256_path(inventory_path)},
        "policy": {
            "selectionCount": sum(QUOTAS.values()),
            "visibleNailQuotas": QUOTAS,
            "maxSelectedImagesPerSourceGroup": MAX_PER_SOURCE_GROUP,
            "selectedSourceGroupsReservedToTrainingRole": True,
            "authorizationDoesNotApproveMasks": True,
            "authorizationDoesNotPermitTrainingBeforeMaskReview": True,
            "trainingUseBeforeAuthorizationAndMaskReview": "prohibited",
        },
        "counts": {
            "requestedImages": len(requested_items),
            "requestedSourceGroups": len({item["sourceGroup"] for item in requested_items}),
            "requestedVisibleNails": sum(item["fullyVisibleNails"] for item in requested_items),
        },
        "requestedItemsSha256": items_sha,
        "authorizationText": authorization_text,
        "authorizationStatus": "missing",
        "trainingUse": "prohibited",
        "requestedItems": requested_items,
        "errors": [],
    }


def main() -> int:
    args = parser().parse_args()
    try:
        if args.verify_report:
            report_path = Path(args.verify_report).resolve()
            existing = load_object(report_path)
            inventory_path = Path(existing.get("inputs", {}).get("inventory", "")).resolve()
            current = build_report(inventory_path)
            if current != existing:
                raise ValueError("Authorization request does not match current replayed evidence")
            print(json.dumps({"ok": True, "decision": "verified", "report": str(report_path)}, ensure_ascii=False))
            return 0
        if not args.inventory or not args.output:
            raise ValueError("Both --inventory and --output are required")
        inventory_path = Path(args.inventory).resolve()
        if not inventory_path.is_file():
            raise ValueError(f"Missing inventory: {inventory_path}")
        report = build_report(inventory_path)
        output = Path(args.output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"ok": True, "decision": report["decision"], "output": str(output)}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, json.JSONDecodeError, KeyError) as error:
        print(json.dumps({"ok": False, "decision": "error", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
