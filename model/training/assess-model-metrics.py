from __future__ import annotations

import argparse
import json
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare candidate segmentation metrics with a baseline and apply regression gates."
    )
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidate", action="append", required=True, help="label=metrics.json")
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-box-map50-drop", type=float, default=0.02)
    parser.add_argument("--max-mask-map50-drop", type=float, default=0.02)
    parser.add_argument("--min-box-map50", type=float)
    parser.add_argument("--min-mask-map50", type=float)
    return parser


def load_metrics(path: Path) -> dict[str, float]:
    document = json.loads(path.read_text(encoding="utf-8"))
    return {
        "boxMap50": float(document["box_map50"]),
        "maskMap50": float(document["seg_map50"]),
        "boxMap50To95": float(document["box_map"]),
        "maskMap50To95": float(document["seg_map"]),
    }


def main() -> None:
    args = build_parser().parse_args()
    baseline_path = Path(args.baseline).resolve()
    baseline = load_metrics(baseline_path)
    candidates = []
    for declaration in args.candidate:
        label, separator, raw_path = declaration.partition("=")
        if not separator or not label or not raw_path:
            raise ValueError("--candidate must use label=metrics.json")
        candidate_path = Path(raw_path).resolve()
        metrics = load_metrics(candidate_path)
        box_drop = baseline["boxMap50"] - metrics["boxMap50"]
        mask_drop = baseline["maskMap50"] - metrics["maskMap50"]
        errors = []
        if args.min_box_map50 is not None and metrics["boxMap50"] < args.min_box_map50:
            errors.append(
                f'box mAP50 {metrics["boxMap50"]:.6f} is below {args.min_box_map50:.6f}'
            )
        if args.min_mask_map50 is not None and metrics["maskMap50"] < args.min_mask_map50:
            errors.append(
                f'mask mAP50 {metrics["maskMap50"]:.6f} is below {args.min_mask_map50:.6f}'
            )
        if box_drop > args.max_box_map50_drop:
            errors.append(
                f"box mAP50 drop {box_drop:.6f} exceeds {args.max_box_map50_drop:.6f}"
            )
        if mask_drop > args.max_mask_map50_drop:
            errors.append(
                f"mask mAP50 drop {mask_drop:.6f} exceeds {args.max_mask_map50_drop:.6f}"
            )
        candidates.append(
            {
                "label": label,
                "metricsPath": str(candidate_path),
                "metrics": metrics,
                "deltaFromBaseline": {
                    "boxMap50": round(metrics["boxMap50"] - baseline["boxMap50"], 8),
                    "maskMap50": round(metrics["maskMap50"] - baseline["maskMap50"], 8),
                },
                "qualityGatePassed": not errors,
                "errors": errors,
            }
        )

    report = {
        "ok": all(candidate["qualityGatePassed"] for candidate in candidates),
        "baseline": {"metricsPath": str(baseline_path), "metrics": baseline},
        "thresholds": {
            "maxBoxMap50Drop": args.max_box_map50_drop,
            "maxMaskMap50Drop": args.max_mask_map50_drop,
            "minBoxMap50": args.min_box_map50,
            "minMaskMap50": args.min_mask_map50,
        },
        "candidates": candidates,
    }
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
