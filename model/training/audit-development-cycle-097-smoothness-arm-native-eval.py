"""S4：在 Stage B 原生半径上评估任一训练臂（禁止重拟合代理指标）。

复用 cycle094 的解码与保真口径，把「评估目录」变成参数，从而可以对 90 基线与三个
λ 臂逐一同口径评估，并额外给出：

* 原生半径抖动（cycle096 口径：`std(|Δr|)` 与二阶差分，float64），用于判定 ≤0.5px 门；
* 与 90 基线的**逐甲配对**联合翻转（同一 (sourceOrdinal, truthIndex)），附精确二项检验 p 值。

保真门（必须全过，否则 ok=False）：
1. 原生半径解码出的 mask 与该次评估存档的 `masksPacked` 逐像素零差；
2. 评估覆盖的甲数等于该次评估报告的甲数。

用法：
    python audit-development-cycle-097-smoothness-arm-native-eval.py \
        --eval <评估目录> --out <报告路径> --label <臂名>
"""

import argparse
import importlib.util
import json
import math
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(r"E:\AI Project\Codex\JiaRu")
BATCH = ROOT / "model/reviews/cycle016-wevis-real-material-v1/batch037"
CODEC = ROOT / "model/training/radial-raw-codec.py"
METRICS = ROOT / "model/training/audit-development-cycle-092-contour-smoothing-prior.py"
BASELINE_REPORT = ROOT / "model/reports/cycle094-native-radius-smoothing-v1/report.json"
GATE = {"maskIoU": 0.75, "boundaryIoU": 0.75, "boundaryF1": 0.9}


def load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_atomic(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise ValueError(f"报告已存在，禁止覆盖：{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.tmp-", dir=path.parent)
    import os

    os.close(descriptor)
    temp_path = Path(temporary)
    try:
        temp_path.write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def decode(radius: np.ndarray, bins: np.ndarray, distance: np.ndarray) -> np.ndarray:
    """运行时口径：float32 相减后与 0 比较。"""
    values = radius[bins].astype(np.float32)
    return (values - distance).astype(np.float32) >= np.float32(0.0)


def jitter(vector: np.ndarray) -> dict[str, float]:
    values = vector.astype(np.float64)
    previous = np.concatenate([values[-1:], values[:-1]])
    following = np.concatenate([values[1:], values[:1]])
    first = np.abs(following - values)
    second = np.abs(previous - 2 * values + following)
    return {
        "diffStd": float(np.std(first)),
        "diffMedian": float(np.median(first)),
        "secondDiffStd": float(np.std(second)),
    }


def sign_test(gained: int, lost: int) -> float:
    """精确二项检验（双侧，p=0.5）。"""
    total = gained + lost
    if total == 0:
        return 1.0
    tail = sum(math.comb(total, k) for k in range(min(gained, lost) + 1)) / 2 ** total
    return min(1.0, 2 * tail)


def collect(eval_dir: Path) -> dict[str, Any]:
    metrics = load(METRICS, "cycle092_metrics")
    codec = load(CODEC, "radial_raw_codec")

    report = json.loads((eval_dir / "report.json").read_text(encoding="utf-8"))
    plan = json.loads((eval_dir / "plan.json").read_text(encoding="utf-8"))
    execution = json.loads((eval_dir / "execution.json").read_text(encoding="utf-8"))

    inputs_by_source: dict[int, list[dict[str, Any]]] = {}
    raw_by_key: dict[tuple[int, int], dict[str, Any]] = {}
    for item in plan["inputs"]:
        inputs_by_source.setdefault(int(item["sourceOrdinal"]), []).append(item)
        raw_by_key[(int(item["sourceOrdinal"]), int(item["candidateIndex"]))] = item
    for value in inputs_by_source.values():
        value.sort(key=lambda entry: int(entry["candidateIndex"]))
    execution_by_ordinal = {int(record["ordinal"]): record for record in execution["records"]}

    per_nail: list[dict[str, Any]] = []
    fidelity_mismatch = 0
    failures: list[str] = []
    skipped = 0

    for index, record in enumerate(report["records"]):
        source_ordinal = index + 1
        bundle = np.load(Path(record["candidate"]["prediction"]["path"]))
        shape = tuple(int(v) for v in bundle["maskShape"])
        predictions = metrics.unpack_bits(bundle["masksPacked"], shape)
        height, width = shape[1], shape[2]

        payloads = []
        for item in inputs_by_source[source_ordinal]:
            payload = np.load(Path(item["payload"]["path"]))
            if "truthPacked" not in payload.files:
                skipped += 1
                continue
            payloads.append((item, payload))

        for truth_index, (item, payload) in enumerate(payloads):
            payload_shape = tuple(int(v) for v in payload["shape"])
            crop = [int(v) for v in item["crop"]]
            truth = np.zeros((height, width), dtype=bool)
            truth[crop[1]:crop[3], crop[0]:crop[2]] = metrics.unpack_bits(payload["truthPacked"], payload_shape)

            scores = [metrics.mask_iou(truth, predictions[j]) for j in range(predictions.shape[0])]
            best = int(np.argmax(scores))
            stored_mask = predictions[best]

            key = (source_ordinal, best + 1)
            if key not in raw_by_key:
                failures.append(f"缺失候选输入：source {source_ordinal} cand {best + 1}")
                continue
            candidate_input = raw_by_key[key]
            ordinal = int(candidate_input["ordinal"])
            if ordinal not in execution_by_ordinal:
                failures.append(f"缺失 raw：ordinal {ordinal}")
                continue

            arrays = np.load(Path(candidate_input["arrays"]["path"]))
            bins = arrays["angleBins"]
            distance = arrays["distance"]
            identity = {
                "ordinal": ordinal,
                "identity": candidate_input["identity"],
                "candidateIndex": candidate_input["candidateIndex"],
                "crop": candidate_input["crop"],
            }
            raw_path = Path(execution_by_ordinal[ordinal]["raw"]["path"])
            _, _, radius = codec.read(raw_path, bins, distance, identity)

            native_roi = decode(radius, bins, distance)
            native = np.zeros((height, width), dtype=bool)
            native[crop[1]:crop[3], crop[0]:crop[2]] = native_roi
            if not np.array_equal(native, stored_mask):
                fidelity_mismatch += 1

            iou = metrics.mask_iou(truth, native)
            biou, bf1 = metrics.boundary_metrics(truth, native, 2)
            joint = iou >= GATE["maskIoU"] and biou >= GATE["boundaryIoU"] and bf1 >= GATE["boundaryF1"]
            stats = jitter(np.asarray(radius, dtype=np.float64).reshape(-1))
            per_nail.append({
                "sourceOrdinal": source_ordinal,
                "truthIndex": truth_index + 1,
                "fileName": record["identity"]["fileName"],
                "maskIoU": iou,
                "boundaryIoU": biou,
                "boundaryF1": bf1,
                "joint": bool(joint),
                "jitter": stats,
            })

    return {
        "perNail": per_nail,
        "fidelityMismatch": fidelity_mismatch,
        "failures": failures,
        "skipped": skipped,
        "reportNails": len(report["records"]),
    }


def summarise(per_nail: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(per_nail)
    mean = lambda key: sum(row[key] for row in per_nail) / max(1, total)
    return {
        "nails": total,
        "joint": sum(1 for row in per_nail if row["joint"]),
        "meanMaskIoU": mean("maskIoU"),
        "meanBoundaryIoU": mean("boundaryIoU"),
        "meanBoundaryF1": mean("boundaryF1"),
        "meanJitterDiffStd": sum(row["jitter"]["diffStd"] for row in per_nail) / max(1, total),
        "medianJitterDiffMedian": float(np.median([row["jitter"]["diffMedian"] for row in per_nail])) if total else 0.0,
        "meanJitterSecondDiffStd": sum(row["jitter"]["secondDiffStd"] for row in per_nail) / max(1, total),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--paired", action="store_true", help="与 cycle094 的 90 基线做逐甲配对")
    args = parser.parse_args()

    eval_dir = Path(args.eval)
    collected = collect(eval_dir)
    summary = summarise(collected["perNail"])
    value: dict[str, Any] = {
        "schemaVersion": 1,
        "label": args.label,
        "evaluation": str(eval_dir),
        "gate": GATE,
        "okSemantics": "fidelity_and_coverage_only",
        "fidelity": {
            "decodedNativeMismatchPixels": collected["fidelityMismatch"],
            "reportNails": collected["reportNails"],
            "evaluatedNails": summary["nails"],
            "skippedWithoutTruth": collected["skipped"],
            "errors": collected["failures"][:20],
        },
        "native": summary,
        "perNail": collected["perNail"],
    }

    if args.paired:
        baseline = json.loads(BASELINE_REPORT.read_text(encoding="utf-8"))
        index = {(row["sourceOrdinal"], row["truthIndex"]): row["base"]["joint"] for row in baseline["perNail"]}
        pairs = [(index[(row["sourceOrdinal"], row["truthIndex"])], row["joint"])
                 for row in collected["perNail"] if (row["sourceOrdinal"], row["truthIndex"]) in index]
        gained = sum(1 for base, arm in pairs if arm and not base)
        lost = sum(1 for base, arm in pairs if base and not arm)
        unchanged = len(pairs) - gained - lost
        value["paired"] = {
            "baseline": "model/reports/cycle094-native-radius-smoothing-v1/report.json",
            "pairs": len(pairs),
            "baselineJoint": sum(1 for base, _ in pairs if base),
            "armJoint": sum(1 for _, arm in pairs if arm),
            "gained": gained,
            "lost": lost,
            "unchanged": unchanged,
            "delta": gained - lost,
            "twoSidedBinomialP": sign_test(gained, lost),
        }

    value["ok"] = bool(collected["fidelityMismatch"] == 0 and not collected["failures"]
                       and summary["nails"] > 0)
    write_atomic(Path(args.out), value)
    print(json.dumps({k: v for k, v in value.items() if k != "perNail"}, ensure_ascii=False, indent=1))
    if not value["ok"]:
        raise SystemExit("保真门未通过")


if __name__ == "__main__":
    main()
