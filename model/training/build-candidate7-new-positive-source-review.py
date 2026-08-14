#!/usr/bin/env python3
"""构建 candidate7 新增正样本源图审核报告。

该工具只物化原分辨率源图审核结果，不授予训练权限，也不生成 mask。
它会绑定代表图清单、授权 A 清单、candidate6 已授权清单和人工审核声明的
SHA-256，并逐文件复算源图哈希。
"""

from __future__ import annotations

import argparse
import hashlib
import json
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
    parser.add_argument("--representatives", required=True, type=Path)
    parser.add_argument("--authorized-intake", required=True, type=Path)
    parser.add_argument("--candidate6-authorization", required=True, type=Path)
    parser.add_argument("--assessment", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    representatives = load_json(args.representatives)
    authorized = load_json(args.authorized_intake)
    candidate6 = load_json(args.candidate6_authorization)
    assessment = load_json(args.assessment)

    errors: list[str] = []
    rep_items = representatives.get("representatives", [])
    auth_by_name = {item["fileName"]: item for item in authorized.get("entries", [])}
    c6_items = candidate6.get("authorizedItems", [])
    c6_groups = {item["sourceGroup"] for item in c6_items}
    c6_hashes = {item["imageSha256"] for item in c6_items}
    decisions = assessment.get("decisions", [])
    decision_by_name = {item["fileName"]: item for item in decisions}

    if len(decisions) != len(decision_by_name):
        errors.append("assessment contains duplicate fileName entries")
    rep_names = {item["fileName"] for item in rep_items}
    if set(decision_by_name) != rep_names:
        errors.append("assessment file list does not exactly match representatives")

    reviewed: list[dict] = []
    for index, item in enumerate(rep_items, start=1):
        file_name = item["fileName"]
        decision = decision_by_name.get(file_name)
        auth_item = auth_by_name.get(file_name)
        if auth_item is None:
            errors.append(f"{file_name}: missing from authorized intake")
            continue
        if auth_item.get("sha256") != item.get("imageSha256"):
            errors.append(f"{file_name}: authorized intake hash mismatch")
        if auth_item.get("sourceGroup") != item.get("sourceGroup"):
            errors.append(f"{file_name}: authorized intake sourceGroup mismatch")

        image_path = Path(item["imagePath"])
        if not image_path.is_file():
            errors.append(f"{file_name}: source image missing")
            actual_hash = None
        else:
            actual_hash = sha256_file(image_path)
            if actual_hash != item.get("imageSha256"):
                errors.append(f"{file_name}: source image hash mismatch")

        if decision is None:
            continue
        status = decision.get("decision")
        if status not in {"keep-for-annotation", "exclude-source"}:
            errors.append(f"{file_name}: unsupported decision {status!r}")
        if status == "exclude-source" and not decision.get("reasonCodes"):
            errors.append(f"{file_name}: excluded source requires reasonCodes")

        reviewed.append(
            {
                "reviewIndex": index,
                "fileName": file_name,
                "imagePath": str(image_path),
                "imageSha256": actual_hash or item.get("imageSha256"),
                "width": item.get("width"),
                "height": item.get("height"),
                "sourceGroup": item.get("sourceGroup"),
                "fullyVisibleNails": item.get("fullyVisibleNails"),
                "decision": status,
                "reasonCodes": decision.get("reasonCodes", []),
                "reviewNote": decision.get("reviewNote", ""),
                "authorizationBasis": "authorized-intake-A-v2-commercial-training-after-review-and-isolation",
                "candidate6Role": (
                    "same-training-source-group-new-image"
                    if item.get("sourceGroup") in c6_groups
                    else "new-training-source-group"
                ),
                "exactImagePreviouslyAuthorizedForCandidate6": item.get("imageSha256") in c6_hashes,
                "completeMaskReview": "not-started",
                "exactCandidate7TrainingAuthorization": "missing",
                "trainingUse": "prohibited",
            }
        )

    kept = [item for item in reviewed if item["decision"] == "keep-for-annotation"]
    excluded = [item for item in reviewed if item["decision"] == "exclude-source"]
    output = {
        "schemaVersion": 1,
        "ok": not errors,
        "decision": "candidate7_source_review_complete_mask_review_and_exact_training_authorization_pending",
        "inputs": {
            "representatives": str(args.representatives),
            "representativesSha256": sha256_file(args.representatives),
            "authorizedIntake": str(args.authorized_intake),
            "authorizedIntakeSha256": sha256_file(args.authorized_intake),
            "candidate6Authorization": str(args.candidate6_authorization),
            "candidate6AuthorizationSha256": sha256_file(args.candidate6_authorization),
            "assessment": str(args.assessment),
            "assessmentSha256": sha256_file(args.assessment),
        },
        "policy": {
            "originalResolutionVisualReviewRequired": True,
            "sourceGroupAtomicAcrossTrainValTest": True,
            "sameExistingTrainingSourceGroupAllowedOnlyForTraining": True,
            "completeMaskReviewRequired": True,
            "exactCandidate7TrainingAuthorizationRequired": True,
            "trainingUse": "prohibited",
        },
        "counts": {
            "reviewed": len(reviewed),
            "keptForAnnotation": len(kept),
            "excludedSource": len(excluded),
            "sameCandidate6TrainingSourceGroups": sum(
                item["candidate6Role"] == "same-training-source-group-new-image" for item in reviewed
            ),
            "newTrainingSourceGroups": sum(
                item["candidate6Role"] == "new-training-source-group" for item in reviewed
            ),
            "exactImagesPreviouslyAuthorizedForCandidate6": sum(
                item["exactImagePreviouslyAuthorizedForCandidate6"] for item in reviewed
            ),
            "keptExpectedNails": sum(int(item.get("fullyVisibleNails") or 0) for item in kept),
        },
        "keptItemsSha256": canonical_sha256(kept),
        "reviewedItemsSha256": canonical_sha256(reviewed),
        "reviewedItems": reviewed,
        "errors": errors,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": output["ok"], "counts": output["counts"], "errors": errors}, ensure_ascii=False))
    return 0 if output["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
