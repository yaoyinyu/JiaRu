#!/usr/bin/env python3
"""从循环015 batch2真实素材数据集物化报告构建训练折叠源组映射（balanced sampler 输入）。

镜像 cycle012/cycle015 v1 group map 结构：images 按文件名排序，counts 记录 trainImages/sourceGroups。
覆盖全部 developmentSplit=="train" 记录（含 hard-negative），来源组唯一性按组名字符串校验。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import os
from pathlib import Path

ALLOWED_DECISIONS = {
    "development_cycle_015_real_material_batch3_dataset_materialized_for_single_short_experiment",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--materialization-report", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report_path = Path(args.materialization_report).resolve()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("ok") is not True or report.get("decision") not in ALLOWED_DECISIONS:
        raise ValueError("物化报告未通过循环015 batch2门禁")
    train_records = [r for r in report["records"] if r.get("developmentSplit") == "train"]
    images = sorted(
        (
            {
                "fileName": item["fileName"],
                "stem": Path(item["fileName"]).stem,
                "sourceGroup": item["sourceGroup"],
                "role": item["role"],
            }
            for item in train_records
        ),
        key=lambda item: item["fileName"],
    )
    groups = {item["sourceGroup"] for item in images}
    if len(images) != int(report["counts"]["trainImages"]):
        raise ValueError(f"train 图数与物化报告不符：images={len(images)}")
    if not groups or any(not item["sourceGroup"] for item in images):
        raise ValueError("存在空来源组")
    payload = {
        "schemaVersion": 1,
        "mode": "equal-quota-largest-remainder-round-robin-interleave",
        "seed": 20260908,
        "source": {
            "materializationReportPath": str(report_path),
            "materializationReportSha256": sha256_file(report_path),
        },
        "counts": {"trainImages": len(images), "sourceGroups": len(groups)},
        "images": images,
    }
    output = Path(args.output).resolve()
    if output.exists():
        raise ValueError(f"输出已存在，禁止覆盖：{output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{output.name}.tmp-", dir=output.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()
    print(json.dumps({"ok": True, "output": str(output), "counts": payload["counts"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
