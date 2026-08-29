from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType

from _training_common import (
    count_files,
    ensure_python_dependency,
    load_dataset_config,
    resolve_best_weights_path,
    resolve_training_run_dir,
    write_json,
    write_resolved_dataset_yaml,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train the nail texture YOLO segmentation model.")
    parser.add_argument("--dataset", default="model/training/dataset.yaml", help="Path to dataset.yaml")
    parser.add_argument("--output-dir", default="model/exports/nail-texture-seg-v1", help="Directory for training outputs")
    parser.add_argument("--model", default="yolo11n-seg.pt", help="Ultralytics segmentation checkpoint to fine-tune")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", default="auto")
    parser.add_argument("--patience", type=int, default=20)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--optimizer", default="auto")
    parser.add_argument("--lr0", type=float, default=None)
    parser.add_argument("--freeze", type=int, default=None)
    parser.add_argument(
        "--mosaic",
        type=float,
        default=1.0,
        help="Ultralytics mosaic augmentation probability; use 0 for boundary-preserving fine-tuning",
    )
    parser.add_argument(
        "--close-mosaic",
        type=int,
        default=10,
        help="Disable mosaic for the final N epochs; use 0 when mosaic is already disabled",
    )
    parser.add_argument(
        "--mask-ratio",
        type=int,
        default=4,
        help="Segmentation mask downsample ratio; use 1 for full-resolution boundary supervision",
    )
    parser.add_argument(
        "--overlap-mask",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Whether overlapping instance masks are merged during training; use --no-overlap-mask to preserve per-nail boundaries",
    )
    parser.add_argument("--distill-model", default="", help="Local larger YOLO segmentation teacher checkpoint")
    parser.add_argument("--distill-weight", type=float, default=1.0, help="Teacher-score-weighted neck feature loss weight")
    parser.add_argument("--distill-temperature", type=float, default=2.0)
    parser.add_argument("--distill-soft-score-weight", type=float, default=0.25)
    parser.add_argument("--distill-box-weight", type=float, default=0.25)
    parser.add_argument("--distill-mask-weight", type=float, default=0.50)
    parser.add_argument("--distill-boundary-weight", type=float, default=0.25)
    parser.add_argument("--distill-topk", type=int, default=24)
    parser.add_argument("--run-name", default="nail-texture-seg-v1")
    parser.add_argument("--candidate-mode", action="store_true", help="Require a deeply replayed candidate-input audit and mark this run as a release-candidate training attempt")
    parser.add_argument("--candidate-input-report", default="", help="Approved report from audit-candidate-training-input.py")
    parser.add_argument("--candidate-validation-report", default="", help="Deprecated legacy evidence; use --candidate-input-report")
    parser.add_argument("--finalize-existing-run", action="store_true", help="Finalize an already completed run after replaying its current evidence")
    parser.add_argument("--dry-run", action="store_true", help="Validate config and print the resolved training plan")
    return parser


def parse_batch(value: str) -> int | float:
    normalized = value.strip().lower()
    if normalized == "auto":
        return -1
    try:
        numeric = float(normalized)
    except ValueError as error:
        raise ValueError("--batch must be auto, an integer, or a GPU-memory fraction") from error
    if numeric.is_integer():
        return int(numeric)
    if 0 < numeric < 1:
        return numeric
    raise ValueError("fractional --batch must be between 0 and 1")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_distillation_evidence(args: argparse.Namespace) -> dict[str, object] | None:
    """验证教师/学生身份并冻结多信号蒸馏合同。"""

    if not args.distill_model:
        return None
    teacher = Path(args.distill_model).resolve()
    student = Path(args.model).resolve()
    if not teacher.is_file():
        raise ValueError("--distill-model must be an existing local checkpoint")
    if not student.is_file():
        raise ValueError("distillation requires --model to be an existing local student checkpoint")
    teacher_sha = sha256(teacher)
    student_sha = sha256(student)
    if teacher_sha == student_sha:
        raise ValueError("distillation teacher and student checkpoints must differ")
    from nail_texture_distillation import DistillationConfig, current_distillation_contract, configure_distillation

    config = DistillationConfig(
        temperature=args.distill_temperature,
        feature_weight=args.distill_weight,
        soft_score_weight=args.distill_soft_score_weight,
        box_distribution_weight=args.distill_box_weight,
        soft_mask_weight=args.distill_mask_weight,
        boundary_weight=args.distill_boundary_weight,
        topk_anchors=args.distill_topk,
    )
    configure_distillation(config)
    return {
        "teacher": {"path": str(teacher), "sha256": teacher_sha, "bytes": teacher.stat().st_size},
        "studentBase": {"path": str(student), "sha256": student_sha, "bytes": student.stat().st_size},
        "contract": current_distillation_contract(),
        "teacherMustPassIsolatedValidationBeforeCandidateUse": True,
    }


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def load_candidate_input_auditor() -> ModuleType:
    script_path = Path(__file__).with_name("audit-candidate-training-input.py")
    spec = importlib.util.spec_from_file_location(
        "audit_candidate_training_input", script_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load candidate training input auditor")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_hand_roi_input_auditor() -> ModuleType:
    script_path = Path(__file__).with_name("audit-hand-roi-boundary-dataset.py")
    spec = importlib.util.spec_from_file_location(
        "audit_hand_roi_boundary_dataset", script_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load hand-ROI candidate training input auditor")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def candidate_input_validation(
    args: argparse.Namespace, dataset_yaml: Path, output_dir: Path
) -> dict[str, object] | None:
    if not args.candidate_mode:
        if args.candidate_input_report or args.candidate_validation_report:
            raise ValueError("candidate evidence requires --candidate-mode")
        return None
    if args.candidate_validation_report:
        raise ValueError(
            "--candidate-validation-report is legacy and cannot authorize candidate training; "
            "use --candidate-input-report"
        )
    if not args.candidate_input_report:
        raise ValueError("--candidate-mode requires --candidate-input-report")
    path = Path(args.candidate_input_report).resolve()
    shallow = json.loads(path.read_text(encoding="utf-8"))
    auditor = (
        load_hand_roi_input_auditor()
        if shallow.get("decision") == "approved_hand_roi_candidate_training_input"
        else load_candidate_input_auditor()
    )
    report = auditor.verify_approved_report(path, dataset_yaml)
    counts = report.get("counts", {})
    if (
        int(counts.get("trainPositiveImages", -1)) < 100
        or int(counts.get("hardNegativeImages", -1)) < 100
        or int(counts.get("validationImages", -1)) < 30
        or int(counts.get("testImages", -1)) != 0
        or int(counts.get("orphanFiles", -1)) != 0
    ):
        raise ValueError("candidate training input count gate is not satisfied")
    dataset_root = Path(str(report.get("outputDir", ""))).resolve()
    if dataset_root != dataset_yaml.parent.resolve():
        raise ValueError("candidate training input dataset root does not match")
    if is_within(output_dir, dataset_root):
        raise ValueError("candidate training output must be outside the dataset root")
    inputs = report.get("inputs", {})
    validation_evidence = (
        inputs.get("validationDatasetYaml") if isinstance(inputs, dict) else None
    )
    if isinstance(validation_evidence, dict):
        validation_dataset = Path(str(validation_evidence.get("path", ""))).resolve()
        if is_within(output_dir, validation_dataset.parent):
            raise ValueError(
                "candidate training output must be outside the canonical validation dataset"
            )
    return {
        "path": str(path),
        "sha256": sha256(path),
        "decision": report["decision"],
        "materialization_report": inputs["materializationReport"],
        "dataset_files_sha256": report["datasetFilesSha256"],
        "all_roles_sha256": report["allRolesSha256"],
        "counts": counts,
    }


def remove_ultralytics_label_caches(dataset_root: Path) -> list[str]:
    """Remove only Ultralytics' known, reproducible label-cache side effects."""

    removed: list[str] = []
    for split in ("train", "val", "test"):
        cache = (dataset_root / "labels" / f"{split}.cache").resolve()
        if not is_within(cache, dataset_root):
            raise ValueError("resolved Ultralytics cache path escapes dataset root")
        if cache.is_file():
            cache.unlink()
            removed.append(cache.relative_to(dataset_root).as_posix())
    return removed


def install_read_only_ultralytics_image_check() -> None:
    """阻止Ultralytics在扫描时原地重编码已哈希绑定的JPEG。

    Pillow能够完整解码但缺少EOI字节的历史JPEG会被Ultralytics默认的
    ``check_image``自动另存为quality=100。候选数据集是可重放证据，训练器
    只能读取它；是否可解码已由输入深审负责，扫描阶段不得改变任何图片字节。
    """

    from PIL import Image
    from ultralytics.data import utils as data_utils

    def check_image_read_only(im_file: str) -> tuple[str, tuple[int, int]]:
        with Image.open(im_file) as image:
            image.verify()
        with Image.open(im_file) as image:
            image.load()
            shape = (int(image.height), int(image.width))
            image_format = str(image.format or "").lower()
        if shape[0] <= 9 or shape[1] <= 9:
            raise AssertionError(f"image size {shape} <10 pixels")
        if image_format not in data_utils.IMG_FORMATS:
            raise AssertionError(f"Invalid image format {image_format}")
        return "", shape

    data_utils.check_image = check_image_read_only
    # verify_image通过其定义模块的globals查找check_image；显式断言避免未来
    # Ultralytics版本改变导入方式后静默恢复成写入行为。
    if data_utils.verify_image.__globals__.get("check_image") is not check_image_read_only:
        raise RuntimeError("failed to install read-only Ultralytics image verifier")


def main() -> None:
    args = build_parser().parse_args()
    if not 0.0 <= args.mosaic <= 1.0:
        raise ValueError("--mosaic must be between 0 and 1")
    if args.close_mosaic < 0:
        raise ValueError("--close-mosaic must be non-negative")
    if args.mask_ratio < 1:
        raise ValueError("--mask-ratio must be at least 1")
    batch = parse_batch(args.batch)
    dataset_yaml = Path(args.dataset).resolve()
    output_dir = Path(args.output_dir).resolve()
    config = load_dataset_config(dataset_yaml)
    preflight_removed_caches = (
        remove_ultralytics_label_caches(config.dataset_root)
        if args.finalize_existing_run
        else []
    )
    candidate_input_evidence = candidate_input_validation(
        args, dataset_yaml, output_dir
    )
    distillation_evidence = resolve_distillation_evidence(args)
    runtime_dataset_yaml = output_dir / "resolved-dataset.yaml"

    summary = {
        "dataset_yaml": str(dataset_yaml),
        "dataset_yaml_sha256": sha256(dataset_yaml),
        "dataset_root": str(config.dataset_root),
        "runtime_dataset_yaml": str(runtime_dataset_yaml),
        "train_images": count_files(config.dataset_root / config.train, (".jpg", ".jpeg", ".png", ".webp")),
        "val_images": count_files(config.dataset_root / config.val, (".jpg", ".jpeg", ".png", ".webp")),
        "test_images": count_files(config.dataset_root / config.test, (".jpg", ".jpeg", ".png", ".webp")),
        "task": config.task,
        "class_count": config.class_count,
        "names": config.names,
        "model": args.model,
        "epochs": args.epochs,
        "imgsz": args.imgsz,
        "batch": batch,
        "patience": args.patience,
        "device": args.device,
        "workers": args.workers,
        "optimizer": args.optimizer,
        "lr0": args.lr0,
        "freeze": args.freeze,
        "mosaic": args.mosaic,
        "close_mosaic": args.close_mosaic,
        "mask_ratio": args.mask_ratio,
        "overlap_mask": args.overlap_mask,
        "distillation": distillation_evidence,
        "run_name": args.run_name,
        "output_dir": str(output_dir),
        "run_dir": str(resolve_training_run_dir(output_dir, args.run_name)),
        "best_weights_path": str(resolve_best_weights_path(output_dir, args.run_name)),
        "training_intent": "candidate" if args.candidate_mode else "experiment",
        "candidate_input_evidence": candidate_input_evidence,
        "candidate_validation_evidence": None,
        "dry_run": args.dry_run,
    }

    if args.dry_run:
        print(__import__("json").dumps(summary, indent=2))
        return

    if args.finalize_existing_run:
        results_dir = resolve_training_run_dir(output_dir, args.run_name)
        actual_best_weights_path = results_dir / "weights" / "best.pt"
        args_yaml = results_dir / "args.yaml"
        results_csv = results_dir / "results.csv"
        for artifact in (actual_best_weights_path, args_yaml, results_csv):
            if not artifact.is_file():
                raise ValueError(f"completed training artifact is missing: {artifact}")
        removed_caches = [
            *preflight_removed_caches,
            *remove_ultralytics_label_caches(config.dataset_root),
        ]
        candidate_input_validation(args, dataset_yaml, output_dir)
        write_json(
            output_dir / "train-summary.json",
            {
                **summary,
                "results_dir": str(results_dir),
                "best_weights_path": str(actual_best_weights_path),
                "best_weights_sha256": sha256(actual_best_weights_path),
                "completed_run_evidence": {
                    "args_yaml": {"path": str(args_yaml), "sha256": sha256(args_yaml)},
                    "results_csv": {
                        "path": str(results_csv),
                        "sha256": sha256(results_csv),
                    },
                },
                "removed_ultralytics_label_caches": removed_caches,
                "finalized_existing_run": True,
            },
        )
        print(
            f"Existing training run finalized. Summary written to "
            f"{output_dir / 'train-summary.json'}"
        )
        return

    ultralytics = ensure_python_dependency("ultralytics", "pip install ultralytics")
    install_read_only_ultralytics_image_check()
    if distillation_evidence is not None:
        import ultralytics.engine.trainer as ultralytics_trainer
        from nail_texture_distillation import JiaRuSegmentationDistillationModel

        # Trainer通过该符号构造包装模型；子类仍可被Ultralytics的保存/解包逻辑识别。
        ultralytics_trainer.DistillationModel = JiaRuSegmentationDistillationModel
    write_resolved_dataset_yaml(runtime_dataset_yaml, config)
    model = ultralytics.YOLO(args.model)
    output_dir.mkdir(parents=True, exist_ok=True)
    train_options = {
        "optimizer": args.optimizer,
        "mosaic": args.mosaic,
        "close_mosaic": args.close_mosaic,
        "mask_ratio": args.mask_ratio,
        "overlap_mask": args.overlap_mask,
    }
    if args.lr0 is not None:
        train_options["lr0"] = args.lr0
    if args.freeze is not None:
        train_options["freeze"] = args.freeze
    if distillation_evidence is not None:
        train_options["distill_model"] = distillation_evidence["teacher"]["path"]
        train_options["dis"] = args.distill_weight
    results = model.train(
        data=str(runtime_dataset_yaml),
        task="segment",
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=batch,
        patience=args.patience,
        device=args.device,
        workers=args.workers,
        project=str(output_dir),
        name=args.run_name,
        **train_options,
    )
    results_dir = Path(getattr(results, "save_dir", output_dir)).resolve()
    actual_best_weights_path = results_dir / "weights" / "best.pt"
    if args.candidate_mode:
        # Re-run the full evidence chain after training so a dataset or upstream
        # mutation during the run cannot produce an eligible candidate summary.
        remove_ultralytics_label_caches(config.dataset_root)
        candidate_input_validation(args, dataset_yaml, output_dir)
    write_json(
        output_dir / "train-summary.json",
        {
            **summary,
            "results_dir": str(results_dir),
            "best_weights_path": str(actual_best_weights_path),
            "best_weights_sha256": (
                sha256(actual_best_weights_path)
                if actual_best_weights_path.is_file()
                else None
            ),
        },
    )
    print(f"Training finished. Summary written to {output_dir / 'train-summary.json'}")


if __name__ == "__main__":
    main()
