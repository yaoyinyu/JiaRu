#!/usr/bin/env python3
"""将素材字节身份与已冻结来源/角色元数据保守交叉，不授予训练资格。"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROLE_NAMES = (
    "developmentTrain", "historicalDevelopmentEvaluation", "cleanDevelopment",
    "historicalValidation", "consumedPositiveTest",
)
PROTECTED_ROLES = set(ROLE_NAMES) - {"developmentTrain"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bound(path: Path) -> dict[str, str]:
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    return {"path": str(path), "sha256": sha256_file(path)}


def read_bound(binding: dict[str, str]) -> dict[str, Any]:
    path = Path(binding["path"])
    if not path.is_file() or sha256_file(path) != binding["sha256"]:
        raise ValueError(f"权威输入漂移：{path}")
    return json.loads(path.read_text(encoding="utf-8"))


def role_sets(source_supply: dict[str, Any]) -> tuple[dict[str, dict[str, set[str]]], dict[str, dict[str, int]]]:
    if source_supply.get("ok") is not True:
        raise ValueError("来源供给角色账未通过")
    inputs = source_supply["inputs"]
    documents = {name: read_bound(inputs[name]) for name in (
        "cycle012Materialization", "cleanDevelopmentEvaluation", "historicalValidationTruth", "consumedPositiveTest"
    )}
    if documents["consumedPositiveTest"].get("trainingUse") != "prohibited":
        raise ValueError("已消费测试角色漂移")
    cycle_records = documents["cycle012Materialization"]["records"]
    sources = {
        "developmentTrain": [row for row in cycle_records if row.get("developmentSplit") == "train" and row.get("role") == "train-positive"],
        "historicalDevelopmentEvaluation": [row for row in cycle_records if row.get("developmentSplit") == "val" and row.get("role") == "train-positive"],
        "cleanDevelopment": [row for row in documents["cleanDevelopmentEvaluation"]["records"] if row.get("developmentSplit") == "val" and row.get("role") == "train-positive"],
        "historicalValidation": documents["historicalValidationTruth"]["canonicalTruths"],
        "consumedPositiveTest": documents["consumedPositiveTest"]["items"],
    }
    expected = {"developmentTrain": 290, "historicalDevelopmentEvaluation": 66,
                "cleanDevelopment": 58, "historicalValidation": 30, "consumedPositiveTest": 100}
    if {key: len(value) for key, value in sources.items()} != expected:
        raise ValueError("历史角色账记录数漂移")
    result: dict[str, dict[str, set[str]]] = {}
    summary: dict[str, dict[str, int]] = {}
    for role, rows in sources.items():
        hashes = {str(row.get("imageSha256") or "").lower() for row in rows}
        groups = {str(row.get("sourceGroup") or row.get("parentSourceGroup") or "") for row in rows}
        if "" in groups or any(len(value) != 64 for value in hashes):
            raise ValueError(f"{role}身份不完整")
        result[role] = {"hashes": hashes, "sourceGroups": groups}
        summary[role] = {"records": len(rows), "byteIdentities": len(hashes), "sourceGroups": len(groups)}
    return result, summary


def build_report(inputs: dict[str, dict[str, str]]) -> dict[str, Any]:
    inventory = read_bound(inputs["inventory"])
    supply = read_bound(inputs["sourceSupply"])
    intake = read_bound(inputs["intakeAudit"])
    if inventory.get("schemaVersion") != 1 or inventory.get("trainingUse") != "prohibited_until_role_and_visual_truth_review":
        raise ValueError("字节身份账角色不符")
    if intake.get("ok") is not True or intake.get("trainingUse") != "prohibited":
        raise ValueError("源图入库审核状态不符")
    roles, role_summary = role_sets(supply)
    root = Path(inventory["root"])
    files = inventory["files"]
    if len(files) != inventory["counts"]["imageFiles"]:
        raise ValueError("素材字节账条目数漂移")
    by_path = {row["path"]: row["sha256"] for row in files}
    if len(by_path) != len(files):
        raise ValueError("字节账相对路径重复")
    by_hash: dict[str, list[str]] = defaultdict(list)
    for row in files:
        by_hash[row["sha256"]].append(row["path"])
    if len(by_hash) != inventory["counts"]["uniqueByteIdentities"]:
        raise ValueError("字节账不同身份数漂移")

    groups_by_hash: dict[str, set[str]] = defaultdict(set)
    lineage_by_hash: dict[str, set[str]] = defaultdict(set)
    excluded_hashes: set[str] = set()
    for item in intake["items"]:
        digest = str(item["imageSha256"]).lower()
        if digest in by_hash:
            groups_by_hash[digest].add(str(item["sourceGroup"]))
            lineage_by_hash[digest].add("approved-source-intake-v3")
    for item in intake["excludedItems"]:
        digest = str(item["imageSha256"]).lower()
        if digest in by_hash:
            excluded_hashes.add(digest)
            lineage_by_hash[digest].add("excluded-source-intake-v3")
    freeze_counts: dict[str, int] = {}
    for name in ("freezeV3", "freezeV4", "freezeV5"):
        manifest = read_bound(inputs[name])
        items = manifest["items"]
        freeze_counts[name] = len(items)
        for item in items:
            source_path = "美甲图片素材/" + str(item["sourceFile"]).replace("\\", "/")
            digest = str(item["sha256"]).lower()
            if by_path.get(source_path) != digest or digest not in by_hash:
                raise ValueError(f"冻结副本原图身份不符：{name}/{source_path}")
            groups_by_hash[digest].add(str(item["sourceGroup"]))
            lineage_by_hash[digest].add(name)
    if freeze_counts != {"freezeV3": 30, "freezeV4": 54, "freezeV5": 689}:
        raise ValueError("历史冻结清单计数漂移")

    records: list[dict[str, Any]] = []
    decision_counts: Counter[str] = Counter()
    original_count = protected_exact = protected_group = 0
    for digest in sorted(by_hash):
        paths = sorted(by_hash[digest])
        groups = sorted(groups_by_hash[digest])
        exact_roles = sorted(role for role, values in roles.items() if digest in values["hashes"])
        group_roles = sorted(role for role, values in roles.items() if set(groups) & values["sourceGroups"])
        originals = [path for path in paths if path.startswith("美甲图片素材/1/") or
                     path.startswith("美甲图片素材/2/") or path.startswith("美甲图片素材/3/")]
        protected_by_exact = bool(set(exact_roles) & PROTECTED_ROLES)
        protected_by_group = bool(set(group_roles) & PROTECTED_ROLES)
        if protected_by_exact:
            decision = "protected_exact_identity"
            protected_exact += 1
        elif protected_by_group:
            decision = "protected_source_group"
            protected_group += 1
        elif digest in excluded_hashes:
            decision = "source_quality_excluded"
        elif len(groups) > 1:
            decision = "conflicting_source_groups"
        elif "developmentTrain" in exact_roles or "developmentTrain" in group_roles:
            decision = "existing_development_train_role_review_required"
        elif groups:
            decision = "known_lineage_pending_role_and_truth_review"
        else:
            decision = "unresolved_lineage_pending_review"
        decision_counts[decision] += 1
        original_count += len(originals)
        records.append({"sha256": digest, "paths": paths, "originalPaths": originals,
                        "sourceGroups": groups, "lineageEvidence": sorted(lineage_by_hash[digest]),
                        "exactRoleMatches": exact_roles, "sourceGroupRoleMatches": group_roles,
                        "decision": decision, "trainingUse": "prohibited_pending_full_role_and_visual_truth_review"})
    if original_count != 1223:
        raise ValueError("原图目录文件计数漂移")
    return {"schemaVersion": 1, "ok": True, "decision": "conservative_source_role_overlap_ledger",
            "analysisKind": "metadata_only_no_pixel_read_no_training_promotion", "inputs": inputs,
            "summary": {"files": len(files), "byteIdentities": len(records), "originalFiles": original_count,
                        "freezeCounts": freeze_counts, "roleLedger": role_summary,
                        "protectedExactIdentities": protected_exact, "protectedSourceGroupOnlyIdentities": protected_group,
                        "decisionCounts": dict(sorted(decision_counts.items()))},
            "records": records, "trainingUse": "prohibited_pending_full_role_and_visual_truth_review"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--source-supply", type=Path)
    parser.add_argument("--intake-audit", type=Path)
    parser.add_argument("--freeze-v3", type=Path)
    parser.add_argument("--freeze-v4", type=Path)
    parser.add_argument("--freeze-v5", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        recorded = json.loads(args.verify_report.read_text(encoding="utf-8"))
        current = build_report(recorded["inputs"])
        ok = current == recorded
        print(json.dumps({"ok": ok, "decision": "verified_source_role_ledger" if ok else "reconstruction_mismatch",
                          "summary": current["summary"]}, ensure_ascii=False))
        if not ok:
            raise SystemExit(1)
        return
    required = (args.inventory, args.source_supply, args.intake_audit, args.freeze_v3,
                args.freeze_v4, args.freeze_v5, args.output)
    if any(path is None for path in required):
        parser.error("all inputs and --output are required")
    if args.output.exists():
        raise FileExistsError(args.output)
    inputs = {name: bound(path) for name, path in (("inventory", args.inventory),
              ("sourceSupply", args.source_supply), ("intakeAudit", args.intake_audit),
              ("freezeV3", args.freeze_v3), ("freezeV4", args.freeze_v4), ("freezeV5", args.freeze_v5))}
    result = build_report(inputs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["ok"], "decision": result["decision"], "summary": result["summary"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
