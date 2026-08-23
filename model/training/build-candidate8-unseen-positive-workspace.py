#!/usr/bin/env python3
"""从已通过源图门但未入任何受保护角色的图片构建candidate8标注工作区。"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


DECISION = "candidate8_annotation_workspace_ready_candidate_only"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"{label}不存在：{path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label}不是JSON对象：{path}")
    return value


def require_sha256(value: Any, label: str) -> str:
    text = str(value or "")
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ValueError(f"{label}不是小写SHA-256")
    return text


def verify_source_workspace(path: Path) -> dict[str, Any]:
    script = Path(__file__).with_name("build-candidate7-annotation-workspace.py")
    result = subprocess.run(
        [sys.executable, str(script), "--verify-workspace", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"上游源图工作区深验失败：{detail}")
    document = load_json(path, "上游源图工作区")
    if (
        document.get("ok") is not True
        or document.get("decision")
        != "candidate7_annotation_workspace_ready_candidate_only"
        or document.get("trainingUse") != "prohibited"
    ):
        raise ValueError("上游源图工作区状态不安全")
    return document


def validate_standing_authorization(path: Path) -> dict[str, Any]:
    document = load_json(path, "standing商业授权")
    scope = document.get("scope") or {}
    if (
        document.get("decision")
        != "standing_project_commercial_resource_authorization_granted"
        or document.get("authorizedBy") != "user"
        or scope.get("projectScopedImageResources") != "commercial-use-permitted"
        or scope.get("itemizedTrainingAuthorizationRequired") is not False
    ):
        raise ValueError("standing商业授权无效")
    return document


def load_current_sources(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise ValueError(f"当前角色清单不存在：{path}")
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = [dict(row) for row in csv.DictReader(stream)]
    required = {"fileName", "role", "split", "sourceGroup", "imageSha256"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError("当前角色清单缺少规范字段")
    for index, row in enumerate(rows, start=1):
        if row["split"] not in {"train", "val"}:
            raise ValueError(f"当前角色清单第{index}行split无效")
        require_sha256(row["imageSha256"], f"当前角色清单第{index}行图片")
    return rows


def load_protected_negative_identities(path: Path) -> tuple[set[str], set[str], set[str]]:
    registry = load_json(path, "困难负样本保护登记表")
    entries = registry.get("entries")
    if (
        registry.get("ok") is not True
        or registry.get("decision") != "protected_hard_negative_registry"
        or not isinstance(entries, list)
        or not entries
    ):
        raise ValueError("困难负样本保护登记表无效")
    names: set[str] = set()
    hashes: set[str] = set()
    groups: set[str] = set()
    for number, entry in enumerate(entries, start=1):
        manifest_path = Path(str(entry.get("path") or "")).resolve()
        expected = require_sha256(entry.get("sha256"), f"保护登记第{number}项")
        if not manifest_path.is_file() or sha256_file(manifest_path) != expected:
            raise ValueError(f"保护登记manifest漂移：{manifest_path}")
        manifest = load_json(manifest_path, "受保护困难负样本manifest")
        items = manifest.get("items")
        if not isinstance(items, list):
            raise ValueError(f"受保护manifest没有items：{manifest_path}")
        for item in items:
            names.add(str(item.get("fileName") or "").casefold())
            hashes.add(require_sha256(item.get("imageSha256"), "受保护困难负样本图片"))
            group = str(item.get("sourceGroup") or "").strip()
            if group:
                groups.add(group)
    return names, hashes, groups


def select_items(
    source: dict[str, Any],
    truth_index: dict[str, Any],
    role_rows: list[dict[str, str]],
    frozen: dict[str, Any],
    protected_names: set[str],
    protected_hashes: set[str],
    protected_groups: set[str],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    truths = truth_index.get("canonicalTruths")
    if (
        truth_index.get("ok") is not True
        or truth_index.get("decision") != "approved_unique_training_truth_index"
        or not isinstance(truths, list)
    ):
        raise ValueError("candidate7组合训练真值索引无效")
    trained_names = {str(item["fileName"]).casefold() for item in truths}
    trained_hashes = {require_sha256(item["imageSha256"], "训练真值图片") for item in truths}

    val_rows = [row for row in role_rows if row["split"] == "val"]
    val_names = {row["fileName"].casefold() for row in val_rows}
    val_hashes = {row["imageSha256"] for row in val_rows}
    val_groups = {row["sourceGroup"] for row in val_rows}

    frozen_items = frozen.get("items")
    if (
        frozen.get("schemaVersion") != 2
        or frozen.get("trainingUse") != "prohibited"
        or not isinstance(frozen_items, list)
        or len(frozen_items) < 100
    ):
        raise ValueError("冻结test100 manifest无效")
    frozen_names = {str(item["fileName"]).casefold() for item in frozen_items}
    frozen_hashes = {
        require_sha256(item["imageSha256"], "冻结test100图片") for item in frozen_items
    }
    frozen_groups = {
        str(value)
        for item in frozen_items
        for value in (item.get("sourceGroup"), item.get("parentSourceGroup"))
        if str(value or "").strip()
    }

    selected: list[dict[str, Any]] = []
    excluded_trained = 0
    for item in source.get("items") or []:
        file_name = str(item.get("fileName") or "")
        image_hash = require_sha256(item.get("imageSha256"), f"源图{file_name}")
        source_group = str(item.get("sourceGroup") or "").strip()
        if file_name.casefold() in trained_names or image_hash in trained_hashes:
            excluded_trained += 1
            continue
        if (
            file_name.casefold() in val_names
            or image_hash in val_hashes
            or source_group in val_groups
        ):
            raise ValueError(f"candidate8源图与val角色冲突：{file_name}")
        if (
            file_name.casefold() in frozen_names
            or image_hash in frozen_hashes
            or source_group in frozen_groups
        ):
            raise ValueError(f"candidate8源图与冻结test100冲突：{file_name}")
        if (
            file_name.casefold() in protected_names
            or image_hash in protected_hashes
            or source_group in protected_groups
        ):
            raise ValueError(f"candidate8源图与受保护困难负样本冲突：{file_name}")
        if (
            item.get("sourceQualityReview") != "passed-for-complete-mask-rereview"
            or item.get("completeMaskReview") != "not-started"
            or item.get("annotationTruthStatus") != "not-started"
            or item.get("trainingUse") != "prohibited"
        ):
            raise ValueError(f"candidate8源图候选状态不安全：{file_name}")
        selected.append(item)
    selected.sort(key=lambda item: str(item["fileName"]))
    if not selected:
        raise ValueError("没有可用于candidate8的新源图候选")
    return selected, {
        "sourceImages": len(source.get("items") or []),
        "excludedExistingTrainingTruth": excluded_trained,
        "selectedImages": len(selected),
        "selectedExpectedNails": sum(
            int(item["expectedFullyVisibleNails"]) for item in selected
        ),
        "selectedSourceGroups": len({item["sourceGroup"] for item in selected}),
    }


def build(args: argparse.Namespace) -> Path:
    output = Path(args.output_dir).resolve()
    if output.exists():
        raise ValueError(f"输出目录已存在：{output}")
    source_path = Path(args.source_workspace_manifest).resolve()
    truth_path = Path(args.current_training_truth_index).resolve()
    sources_path = Path(args.current_sources).resolve()
    frozen_path = Path(args.frozen_test_manifest).resolve()
    registry_path = Path(args.protected_registry).resolve()
    authorization_path = Path(args.standing_authorization).resolve()
    source = verify_source_workspace(source_path)
    validate_standing_authorization(authorization_path)
    truth = load_json(truth_path, "candidate7组合训练真值索引")
    rows = load_current_sources(sources_path)
    frozen = load_json(frozen_path, "冻结test100 manifest")
    protected = load_protected_negative_identities(registry_path)
    selected, counts = select_items(source, truth, rows, frozen, *protected)

    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    try:
        image_dir = staging / "images"
        image_dir.mkdir()
        records: list[dict[str, Any]] = []
        methods: dict[str, int] = {}
        source_image_dir = Path(str(source["imageDir"])).resolve()
        for item in selected:
            source_image = (source_image_dir / str(item["fileName"])).resolve()
            if source_image.parent != source_image_dir or not source_image.is_file():
                raise ValueError(f"源图路径不安全或不存在：{source_image}")
            if sha256_file(source_image) != item["imageSha256"]:
                raise ValueError(f"源图字节漂移：{source_image}")
            target = image_dir / source_image.name
            method = "hardlink"
            try:
                os.link(source_image, target)
            except OSError:
                shutil.copy2(source_image, target)
                method = "copy"
            methods[method] = methods.get(method, 0) + 1
            record = dict(item)
            record.update(
                {
                    "sourcePath": str(source_image),
                    "workspacePath": str(output / "images" / source_image.name),
                    "assignedRole": "candidate8-train-positive-candidate",
                    "materializationMethod": method,
                    "standingCommercialAuthorization": "granted",
                }
            )
            records.append(record)

        manifest = {
            "schemaVersion": 1,
            "ok": True,
            "decision": DECISION,
            "inputs": {
                "sourceWorkspaceManifest": {
                    "path": str(source_path),
                    "sha256": sha256_file(source_path),
                },
                "currentTrainingTruthIndex": {
                    "path": str(truth_path),
                    "sha256": sha256_file(truth_path),
                },
                "currentSources": {
                    "path": str(sources_path),
                    "sha256": sha256_file(sources_path),
                },
                "frozenTestManifest": {
                    "path": str(frozen_path),
                    "sha256": sha256_file(frozen_path),
                },
                "protectedRegistry": {
                    "path": str(registry_path),
                    "sha256": sha256_file(registry_path),
                },
                "standingCommercialAuthorization": {
                    "path": str(authorization_path),
                    "sha256": sha256_file(authorization_path),
                },
            },
            "policy": {
                "onlySourceReviewedImages": True,
                "existingTrainingTruthExcluded": True,
                "validationFrozenTestAndProtectedNegativeOverlapForbidden": True,
                "sameTrainRoleSourceGroupAllowed": True,
                "modelOutputIsReviewOnly": True,
                "originalResolutionCompleteMaskReviewRequired": True,
                "watermarksAllowedButShortcutAuditStillRequired": True,
                "trainingUse": "prohibited-until-complete-mask-finalization-and-input-audit",
            },
            "imageDir": str(output / "images"),
            "counts": {**counts, "materializationMethods": methods},
            "itemsSha256": canonical_sha256(records),
            "items": records,
            "trainingUse": "prohibited",
            "errors": [],
        }
        manifest_path = staging / "annotation-workspace-manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(staging, output)
        final_manifest = output / manifest_path.name
        verify_workspace(final_manifest)
        return final_manifest
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        if output.exists():
            shutil.rmtree(output, ignore_errors=True)
        raise


def verify_workspace(manifest_path: Path) -> dict[str, Any]:
    manifest = load_json(manifest_path, "candidate8标注工作区")
    if (
        manifest.get("schemaVersion") != 1
        or manifest.get("ok") is not True
        or manifest.get("decision") != DECISION
    ):
        raise ValueError("candidate8工作区schema、状态或decision无效")
    if manifest.get("trainingUse") != "prohibited":
        raise ValueError("candidate8工作区必须保持training prohibited")

    inputs = manifest.get("inputs") or {}
    required_inputs = {
        "sourceWorkspaceManifest": "上游源图工作区",
        "currentTrainingTruthIndex": "candidate7组合训练真值索引",
        "currentSources": "当前角色清单",
        "frozenTestManifest": "冻结test100 manifest",
        "protectedRegistry": "困难负样本保护登记表",
        "standingCommercialAuthorization": "standing商业授权",
    }
    paths: dict[str, Path] = {}
    for key, label in required_inputs.items():
        record = inputs.get(key) or {}
        path = Path(str(record.get("path") or "")).resolve()
        if not path.is_file() or sha256_file(path) != record.get("sha256"):
            raise ValueError(f"candidate8工作区输入缺失或字节漂移：{label}")
        paths[key] = path

    source = verify_source_workspace(paths["sourceWorkspaceManifest"])
    validate_standing_authorization(paths["standingCommercialAuthorization"])
    truth = load_json(paths["currentTrainingTruthIndex"], "candidate7组合训练真值索引")
    rows = load_current_sources(paths["currentSources"])
    frozen = load_json(paths["frozenTestManifest"], "冻结test100 manifest")
    protected = load_protected_negative_identities(paths["protectedRegistry"])
    selected, expected_counts = select_items(source, truth, rows, frozen, *protected)

    items = manifest.get("items")
    if not isinstance(items, list) or canonical_sha256(items) != manifest.get("itemsSha256"):
        raise ValueError("candidate8工作区items或聚合哈希无效")
    selected_by_name = {str(item["fileName"]): item for item in selected}
    item_by_name = {str(item.get("fileName") or ""): item for item in items}
    if len(item_by_name) != len(items) or set(item_by_name) != set(selected_by_name):
        raise ValueError("candidate8工作区未精确覆盖当前可选源图")

    counts = manifest.get("counts") or {}
    for key, expected in expected_counts.items():
        if counts.get(key) != expected:
            raise ValueError(f"candidate8工作区计数不一致：{key}")
    methods: dict[str, int] = {}
    for file_name, item in item_by_name.items():
        selected_item = selected_by_name[file_name]
        if (
            item.get("imageSha256") != selected_item.get("imageSha256")
            or item.get("sourceGroup") != selected_item.get("sourceGroup")
            or item.get("expectedFullyVisibleNails")
            != selected_item.get("expectedFullyVisibleNails")
        ):
            raise ValueError(f"candidate8工作区身份字段漂移：{file_name}")
        if (
            item.get("trainingUse") != "prohibited"
            or item.get("annotationTruthStatus") != "not-started"
            or item.get("assignedRole") != "candidate8-train-positive-candidate"
        ):
            raise ValueError(f"candidate8工作区候选状态不安全：{file_name}")
        expected_hash = require_sha256(item.get("imageSha256"), f"candidate8图片{file_name}")
        for field in ("sourcePath", "workspacePath"):
            image_path = Path(str(item.get(field) or "")).resolve()
            if not image_path.is_file() or sha256_file(image_path) != expected_hash:
                raise ValueError(f"candidate8图片缺失或字节漂移：{file_name}/{field}")
        method = str(item.get("materializationMethod") or "")
        if method not in {"hardlink", "copy"}:
            raise ValueError(f"candidate8物化方式无效：{file_name}")
        methods[method] = methods.get(method, 0) + 1
    if counts.get("materializationMethods") != methods:
        raise ValueError("candidate8工作区物化计数不一致")
    return manifest


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--source-workspace-manifest")
    value.add_argument("--current-training-truth-index")
    value.add_argument("--current-sources")
    value.add_argument("--frozen-test-manifest")
    value.add_argument("--protected-registry")
    value.add_argument("--standing-authorization")
    value.add_argument("--output-dir")
    value.add_argument("--verify-workspace")
    return value


def main() -> int:
    try:
        args = parser().parse_args()
        if args.verify_workspace:
            manifest_path = Path(args.verify_workspace).resolve()
            report = verify_workspace(manifest_path)
            print(
                json.dumps(
                    {"ok": True, "decision": "verified", "counts": report["counts"]},
                    ensure_ascii=False,
                )
            )
            return 0
        required = (
            "source_workspace_manifest",
            "current_training_truth_index",
            "current_sources",
            "frozen_test_manifest",
            "protected_registry",
            "standing_authorization",
            "output_dir",
        )
        missing = [name for name in required if not getattr(args, name)]
        if missing:
            parser().error("构建工作区缺少参数：" + ", ".join(missing))
        output = build(args)
        report = load_json(output, "candidate8标注工作区")
        print(
            json.dumps(
                {"ok": True, "decision": report["decision"], "counts": report["counts"]},
                ensure_ascii=False,
            )
        )
        return 0
    except Exception as error:  # pragma: no cover - CLI boundary
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
