#!/usr/bin/env python3
"""Audit source-group isolation across train, validation, and test splits."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from _training_common import load_dataset_config, write_json


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def build(args: argparse.Namespace) -> dict[str, Any]:
    dataset_path = Path(args.dataset).resolve()
    dataset = load_dataset_config(dataset_path)
    sources_path = Path(args.sources_csv).resolve()
    split_path = Path(args.split_json).resolve()
    split = read_json(split_path)
    errors: list[str] = []
    file_splits: dict[str, str] = {}
    split_counts: dict[str, int] = {}
    for name in ("train", "val", "test"):
        files = split.get(name)
        if not isinstance(files, list):
            errors.append(f"split {name} must be an array")
            files = []
        split_counts[name] = len(files)
        for file_name in files:
            normalized = str(file_name)
            if normalized in file_splits:
                errors.append(f"file appears in multiple splits: {normalized}")
            file_splits[normalized] = name

    groups: dict[str, Counter[str]] = defaultdict(Counter)
    source_files: set[str] = set()
    with sources_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row_number, row in enumerate(csv.DictReader(handle), start=2):
            file_name = str(row.get("fileName", "")).strip()
            group = str(row.get("sourceGroup", "")).strip()
            if not file_name or not group:
                errors.append(f"sources.csv row {row_number} is missing fileName or sourceGroup")
                continue
            if file_name in source_files:
                errors.append(f"duplicate source file record: {file_name}")
                continue
            source_files.add(file_name)
            assigned = file_splits.get(file_name)
            if not assigned:
                errors.append(f"source file is absent from split.json: {file_name}")
                continue
            groups[group][assigned] += 1
    unknown_split_files = sorted(set(file_splits) - source_files)
    if unknown_split_files:
        errors.append(f"split.json contains files absent from sources.csv: {unknown_split_files}")

    group_counts = {
        group: {name: int(counts.get(name, 0)) for name in ("train", "val", "test")}
        for group, counts in sorted(groups.items())
    }
    leaking = []
    for group, counts in group_counts.items():
        active = [name for name, count in counts.items() if count > 0]
        if len(active) > 1:
            leaking.append({"sourceGroup": group, "splits": active, "counts": counts})
    if leaking:
        errors.append(f"{len(leaking)} source groups cross split boundaries")
    approved = not errors
    return {
        "ok": approved,
        "schemaVersion": 1,
        "decision": (
            "approved_dataset_source_isolation"
            if approved
            else "rejected_dataset_source_isolation"
        ),
        "outputDir": str(dataset.dataset_root),
        "inputs": {
            "datasetYaml": str(dataset_path),
            "datasetYamlSha256": sha256(dataset_path),
            "sourcesCsv": str(sources_path),
            "sourcesCsvSha256": sha256(sources_path),
            "splitJson": str(split_path),
            "splitJsonSha256": sha256(split_path),
        },
        "splitCounts": split_counts,
        "sourceRecordCount": len(source_files),
        "groupCounts": group_counts,
        "leakingGroups": leaking,
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit dataset source-group isolation.")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--sources-csv", required=True)
    parser.add_argument("--split-json", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = build(args)
    output = Path(args.output).resolve()
    write_json(output, report)
    print(json.dumps({"ok": report["ok"], "decision": report["decision"], "splitCounts": report["splitCounts"], "leakingGroups": report["leakingGroups"], "errors": report["errors"], "output": str(output)}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
