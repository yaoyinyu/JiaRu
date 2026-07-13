from __future__ import annotations

import argparse
import json
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Aggregate core and stress-derived review decisions back to release-test parents."
    )
    parser.add_argument("--parent-intake", required=True)
    parser.add_argument("--core-review", required=True)
    parser.add_argument("--stress-intake", required=True)
    parser.add_argument("--stress-review", required=True)
    parser.add_argument("--output", required=True)
    return parser


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def require_partition(review: dict, expected: set[str], label: str) -> dict[str, str]:
    decisions: dict[str, str] = {}
    for status, key in (("pass", "passFiles"), ("rework", "reworkFiles"), ("exclude", "excludeFiles")):
        for file_name in review.get(key, []):
            if file_name in decisions:
                raise ValueError(f"{label} has duplicate decision for {file_name}")
            decisions[file_name] = status
    missing = sorted(expected - set(decisions))
    extra = sorted(set(decisions) - expected)
    if missing or extra:
        raise ValueError(f"{label} review coverage mismatch; missing={missing}, extra={extra}")
    return decisions


def build_summary(parent_intake: dict, core_review: dict, stress_intake: dict, stress_review: dict) -> dict:
    if not core_review.get("ok") or not stress_review.get("ok"):
        raise ValueError("all input review reports must be ok")
    authorization = parent_intake.get("authorization", {})
    if authorization.get("trainingUse") != "prohibited":
        raise ValueError("parent release-test intake must prohibit training")
    required_uses = {"independent-release-test", "long-term-regression"}
    if not required_uses.issubset(set(authorization.get("authorizedUses", []))):
        raise ValueError("parent intake is missing release-test or long-term-regression authorization")

    parent_entries = {item["fileName"]: item for item in parent_intake.get("entries", [])}
    core_entries = {name: item for name, item in parent_entries.items() if item.get("decision") == "core"}
    stress_parents = {name: item for name, item in parent_entries.items() if item.get("decision") == "stress"}
    review_parent_entries = {**core_entries, **stress_parents}
    upstream_excluded = sorted(
        name for name, item in parent_entries.items() if item.get("decision") == "exclude"
    )
    core_decisions = require_partition(core_review, set(core_entries), "core")

    derived_entries = {item["fileName"]: item for item in stress_intake.get("entries", [])}
    if len(derived_entries) != len(stress_parents):
        raise ValueError("stress intake must contain exactly one derived region per stress parent")
    parent_by_derived: dict[str, str] = {}
    for derived_name, item in derived_entries.items():
        parent_name = item.get("parentFileName")
        if parent_name not in stress_parents:
            raise ValueError(f"derived region parent is not a stress parent: {derived_name}")
        if item.get("trainingUse") != "prohibited":
            raise ValueError(f"derived region permits training: {derived_name}")
        if parent_name in parent_by_derived.values():
            raise ValueError(f"stress parent has multiple derived regions: {parent_name}")
        parent_by_derived[derived_name] = parent_name
    stress_decisions = require_partition(stress_review, set(derived_entries), "stress")

    parent_decisions = dict(core_decisions)
    derived_trace = []
    for derived_name, status in stress_decisions.items():
        parent_name = parent_by_derived[derived_name]
        parent_decisions[parent_name] = status
        derived_trace.append(
            {
                "parentFileName": parent_name,
                "derivedFileName": derived_name,
                "decision": status,
                "sourceGroup": derived_entries[derived_name]["sourceGroup"],
            }
        )
    if set(parent_decisions) != set(review_parent_entries):
        raise ValueError("aggregated decisions do not cover every release-test parent")

    files_by_status = {
        status: sorted(name for name, value in parent_decisions.items() if value == status)
        for status in ("pass", "rework", "exclude")
    }
    accepted_source_groups = {
        review_parent_entries[name]["sourceGroup"] for name in files_by_status["pass"]
    }
    return {
        "schemaVersion": 1,
        "batchId": parent_intake["batchId"],
        "decision": "human_reviewed_candidates_not_frozen_test_truth",
        "ok": True,
        "counts": {
            "parents": len(review_parent_entries),
            "pass": len(files_by_status["pass"]),
            "rework": len(files_by_status["rework"]),
            "excluded": len(files_by_status["exclude"]),
            "acceptedMasks": core_review["counts"]["acceptedMasks"]
            + stress_review["counts"]["acceptedMasks"],
            "acceptedSourceGroups": len(accepted_source_groups),
            "upstreamExcluded": len(upstream_excluded),
        },
        "passParentFiles": files_by_status["pass"],
        "reworkParentFiles": files_by_status["rework"],
        "excludeParentFiles": files_by_status["exclude"],
        "upstreamExcludeFiles": upstream_excluded,
        "stressDerivedTrace": sorted(derived_trace, key=lambda item: item["parentFileName"]),
        "authorization": {
            "authorizedUses": sorted(required_uses),
            "trainingUse": "prohibited",
        },
    }


def main() -> None:
    args = build_parser().parse_args()
    output = Path(args.output).resolve()
    try:
        summary = build_summary(
            load(Path(args.parent_intake).resolve()),
            load(Path(args.core_review).resolve()),
            load(Path(args.stress_intake).resolve()),
            load(Path(args.stress_review).resolve()),
        )
    except Exception as error:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps({"ok": False, "errors": [str(error)]}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        raise
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), **summary["counts"], "ok": True}, ensure_ascii=True))


if __name__ == "__main__":
    main()
