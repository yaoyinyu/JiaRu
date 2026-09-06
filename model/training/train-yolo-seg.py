from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import csv
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
    parser.add_argument(
        "--hard-boundary-weight",
        type=float,
        default=0.0,
        help="Additional reviewed-polygon boundary loss weight; 0 keeps native Ultralytics mask loss",
    )
    parser.add_argument(
        "--hard-boundary-kernel",
        type=int,
        default=3,
        help="Odd morphological-gradient kernel used by hard polygon boundary supervision",
    )
    parser.add_argument("--distill-model", default="", help="Local larger YOLO segmentation teacher checkpoint")
    parser.add_argument(
        "--allow-same-checkpoint-self-distillation",
        action="store_true",
        help="Explicitly allow teacher and student to start from the same validated checkpoint",
    )
    parser.add_argument("--distill-weight", type=float, default=1.0, help="Teacher-score-weighted neck feature loss weight")
    parser.add_argument("--distill-temperature", type=float, default=2.0)
    parser.add_argument("--distill-soft-score-weight", type=float, default=0.25)
    parser.add_argument("--distill-box-weight", type=float, default=0.25)
    parser.add_argument("--distill-mask-weight", type=float, default=0.50)
    parser.add_argument("--distill-boundary-weight", type=float, default=0.25)
    parser.add_argument("--distill-topk", type=int, default=24)
    parser.add_argument("--run-name", default="nail-texture-seg-v1")
    parser.add_argument(
        "--resume-from",
        default="",
        help="Resume an interrupted Ultralytics run from its last.pt with the checkpoint-bound optimizer and epoch state",
    )
    parser.add_argument("--candidate-mode", action="store_true", help="Require a deeply replayed candidate-input audit and mark this run as a release-candidate training attempt")
    parser.add_argument("--candidate-input-report", default="", help="Approved report from audit-candidate-training-input.py")
    parser.add_argument("--candidate-validation-report", default="", help="Deprecated legacy evidence; use --candidate-input-report")
    parser.add_argument("--experiment-plan", default="", help="Pre-registered train-internal development experiment plan")
    parser.add_argument("--experiment-id", default="", help="Exact experimentId selected from --experiment-plan")
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
    same_checkpoint = teacher_sha == student_sha
    if same_checkpoint and not args.allow_same_checkpoint_self_distillation:
        raise ValueError(
            "distillation teacher and student checkpoints must differ unless "
            "--allow-same-checkpoint-self-distillation is explicitly set"
        )
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
        "mode": "same-checkpoint-self-distillation" if same_checkpoint else "teacher-student-distillation",
        "sameCheckpointExplicitlyAuthorized": bool(
            same_checkpoint and args.allow_same_checkpoint_self_distillation
        ),
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


def load_single_nail_roi_input_auditor() -> ModuleType:
    script_path = Path(__file__).with_name("audit-candidate53-single-nail-roi-dataset.py")
    spec = importlib.util.spec_from_file_location(
        "audit_candidate53_single_nail_roi_dataset", script_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load candidate53 single-nail ROI input auditor")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_proposal_conditioned_roi_input_auditor() -> ModuleType:
    script_path = Path(__file__).with_name("audit-candidate55-proposal-conditioned-roi-dataset.py")
    spec = importlib.util.spec_from_file_location(
        "audit_candidate55_proposal_conditioned_roi_dataset", script_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load candidate55 proposal-conditioned ROI input auditor")
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
    decision = shallow.get("decision")
    if decision == "approved_hand_roi_candidate_training_input":
        auditor = load_hand_roi_input_auditor()
    elif decision == "approved_candidate53_single_nail_roi_training_input":
        auditor = load_single_nail_roi_input_auditor()
    elif decision == "approved_candidate55_proposal_conditioned_roi_training_input":
        auditor = load_proposal_conditioned_roi_input_auditor()
    else:
        auditor = load_candidate_input_auditor()
    report = auditor.verify_approved_report(path, dataset_yaml)
    counts = report.get("counts", {})
    if decision in {
        "approved_candidate53_single_nail_roi_training_input",
        "approved_candidate55_proposal_conditioned_roi_training_input",
    }:
        count_gate_failed = (
            int(counts.get("trainPositiveRois", -1)) < 100
            or int(counts.get("trainNegativeRois", -1)) < 1
            or int(counts.get("valPositiveRois", -1)) < 30
            or int(counts.get("testImages", -1)) != 0
            or int(counts.get("orphanFiles", -1)) != 0
        )
    else:
        count_gate_failed = (
            int(counts.get("trainPositiveImages", -1)) < 100
            or int(counts.get("hardNegativeImages", -1)) < 100
            or int(counts.get("validationImages", -1)) < 30
            or int(counts.get("testImages", -1)) != 0
            or int(counts.get("orphanFiles", -1)) != 0
        )
    if count_gate_failed:
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


def load_development_materializer() -> ModuleType:
    script_path = Path(__file__).with_name("materialize-source-group-development-dataset.py")
    spec = importlib.util.spec_from_file_location(
        "materialize_source_group_development_dataset_for_training", script_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load sourceGroup development materializer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def experiment_plan_validation(
    args: argparse.Namespace,
    dataset_yaml: Path,
    output_dir: Path,
    batch: int | float,
) -> dict[str, object] | None:
    if bool(args.experiment_plan) != bool(args.experiment_id):
        raise ValueError("--experiment-plan and --experiment-id must be provided together")
    if not args.experiment_plan:
        return None
    if args.candidate_mode or args.candidate_input_report or args.candidate_validation_report:
        raise ValueError("development experiment evidence cannot be combined with candidate mode")
    plan_path = Path(args.experiment_plan).resolve()
    if not plan_path.is_file():
        raise ValueError(f"development experiment plan is missing: {plan_path}")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if (
        not isinstance(plan, dict)
        or plan.get("schemaVersion") != 1
        or plan.get("decision")
        != "pre_registered_two_short_single_variable_experiments"
        or plan.get("releaseState") != "hold"
    ):
        raise ValueError("development experiment plan contract is invalid")
    experiments = plan.get("experiments")
    selected = [
        item
        for item in experiments if isinstance(item, dict) and item.get("experimentId") == args.experiment_id
    ] if isinstance(experiments, list) else []
    if len(selected) != 1:
        raise ValueError("experimentId does not select exactly one pre-registered experiment")
    experiment = selected[0]
    model_path = Path(str(experiment.get("model", ""))).resolve()
    if Path(args.model).resolve() != model_path:
        raise ValueError("training model differs from the pre-registered experiment")
    if not model_path.is_file() or sha256(model_path) != experiment.get("modelSha256"):
        raise ValueError("pre-registered development model is missing or hash-drifted")
    if model_path.stat().st_size != int(experiment.get("modelBytes", -1)):
        raise ValueError("pre-registered development model byte size drifted")
    if output_dir != Path(str(experiment.get("outputDir", ""))).resolve():
        raise ValueError("training output directory differs from the pre-registered experiment")
    if args.run_name != experiment.get("runName"):
        raise ValueError("training run name differs from the pre-registered experiment")

    plan_inputs = plan.get("inputs", {})
    dataset_binding = plan_inputs.get("datasetYaml")
    materialization_binding = plan_inputs.get("developmentMaterializationReport")
    fold_binding = plan_inputs.get("developmentFoldPlan")
    environment_binding = plan_inputs.get("environmentReport")
    if not all(
        isinstance(value, dict)
        for value in (dataset_binding, materialization_binding, fold_binding, environment_binding)
    ):
        raise ValueError("development experiment plan is missing dataset evidence")
    if dataset_yaml != Path(str(dataset_binding.get("path", ""))).resolve():
        raise ValueError("training dataset differs from the pre-registered experiment")
    if sha256(dataset_yaml) != dataset_binding.get("sha256"):
        raise ValueError("pre-registered development dataset YAML hash drifted")
    materialization_path = Path(str(materialization_binding.get("path", ""))).resolve()
    if not materialization_path.is_file() or sha256(materialization_path) != materialization_binding.get("sha256"):
        raise ValueError("development materialization report is missing or hash-drifted")
    materializer = load_development_materializer()
    materialization = materializer.verify_report(materialization_path)
    if materialization.get("datasetFilesSha256") != materialization_binding.get("datasetFilesSha256"):
        raise ValueError("development dataset file-tree identity drifted")
    fold_path = Path(str(fold_binding.get("path", ""))).resolve()
    if not fold_path.is_file() or sha256(fold_path) != fold_binding.get("sha256"):
        raise ValueError("development fold plan is missing or hash-drifted")
    fold_plan = materializer.FOLD_BUILDER.verify_plan(fold_path)
    if fold_plan.get("contentSha256") != fold_binding.get("contentSha256"):
        raise ValueError("development fold plan content identity drifted")
    environment_path = Path(str(environment_binding.get("path", ""))).resolve()
    if not environment_path.is_file() or sha256(environment_path) != environment_binding.get("sha256"):
        raise ValueError("development environment report is missing or hash-drifted")
    environment = json.loads(environment_path.read_text(encoding="utf-8"))
    if not isinstance(environment, dict) or environment.get("ok") is not True:
        raise ValueError("development environment report did not pass")
    revision = plan.get("revision")
    if revision is not None:
        if not isinstance(revision, dict) or revision.get("previousOutputPreserved") is not True:
            raise ValueError("development experiment plan revision contract is invalid")
        for key in ("previousPlan", "failedLaunch"):
            binding = revision.get(key)
            if not isinstance(binding, dict):
                raise ValueError(f"development experiment revision is missing {key}")
            evidence_path = Path(str(binding.get("path", ""))).resolve()
            if not evidence_path.is_file() or sha256(evidence_path) != binding.get("sha256"):
                raise ValueError(f"development experiment revision evidence drifted: {key}")

    contract = plan.get("fixedTrainingContract")
    if not isinstance(contract, dict) or contract.get("onlyVariable") != "modelCapacity":
        raise ValueError("development training contract is missing or not single-variable")
    actual = {
        "task": "segment",
        "singleStage": True,
        "inputSize": args.imgsz,
        "epochs": args.epochs,
        "patience": args.patience,
        "batch": "auto" if batch == -1 else batch,
        "device": int(args.device) if str(args.device).isdigit() else args.device,
        "workers": args.workers,
        "optimizer": args.optimizer,
        "lr0": args.lr0,
        "freeze": args.freeze,
        "mosaic": args.mosaic,
        "closeMosaic": args.close_mosaic,
        "maskRatio": args.mask_ratio,
        "overlapMask": args.overlap_mask,
        "hardBoundaryWeight": args.hard_boundary_weight,
        "distillation": bool(args.distill_model),
        "onlyVariable": "modelCapacity",
    }
    if actual != contract:
        raise ValueError(
            "training arguments differ from the pre-registered fixed contract: "
            f"actual={actual} expected={contract}"
        )
    return {
        "plan": str(plan_path),
        "plan_sha256": sha256(plan_path),
        "cycle_id": plan.get("cycleId"),
        "hypothesis_id": plan.get("hypothesis", {}).get("id"),
        "experiment_id": args.experiment_id,
        "experiment_role": experiment.get("role"),
        "only_variable": contract.get("onlyVariable"),
        "dataset_files_sha256": materialization.get("datasetFilesSha256"),
        "development_materialization_report": str(materialization_path),
        "development_materialization_report_sha256": sha256(materialization_path),
        "formal_calibration_test_or_holdout": False,
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


def validate_resume_contract(
    resume_from: Path,
    args: argparse.Namespace,
    batch: int | float,
    runtime_dataset_yaml: Path,
    output_dir: Path,
) -> dict[str, object]:
    expected_run_dir = resolve_training_run_dir(output_dir, args.run_name).resolve()
    if resume_from.resolve() != expected_run_dir / "weights" / "last.pt":
        raise ValueError("--resume-from must be the canonical last.pt of the requested run")
    args_yaml = expected_run_dir / "args.yaml"
    results_csv = expected_run_dir / "results.csv"
    if not args_yaml.is_file() or not results_csv.is_file():
        raise ValueError("resume requires the original args.yaml and results.csv")
    import yaml

    saved = yaml.safe_load(args_yaml.read_text(encoding="utf-8"))
    expected = {
        "model": str(Path(args.model).resolve()),
        "data": str(runtime_dataset_yaml.resolve()),
        "epochs": args.epochs,
        "patience": args.patience,
        "batch": batch,
        "imgsz": args.imgsz,
        "device": str(args.device),
        "workers": args.workers,
        "project": str(output_dir.resolve()),
        "name": args.run_name,
        "optimizer": args.optimizer,
        "close_mosaic": args.close_mosaic,
        "freeze": args.freeze,
        "overlap_mask": args.overlap_mask,
        "mask_ratio": args.mask_ratio,
        "mosaic": args.mosaic,
        "lr0": args.lr0,
    }
    for key, value in expected.items():
        saved_value = saved.get(key)
        if key in {"model", "data", "project"}:
            matches = Path(str(saved_value)).resolve() == Path(str(value)).resolve()
        elif isinstance(value, float):
            matches = abs(float(saved_value) - value) <= 1e-12
        else:
            matches = saved_value == value
        if not matches:
            raise ValueError(
                f"resume contract drift for {key}: saved={saved_value!r}, requested={value!r}"
            )
    with results_csv.open("r", encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    if not rows:
        raise ValueError("resume results.csv contains no completed epoch")
    completed_epochs = max(int(float(row["epoch"])) for row in rows)
    if completed_epochs >= args.epochs:
        raise ValueError("resume checkpoint has already reached the requested epoch count")
    return {
        "path": str(resume_from),
        "sha256": sha256(resume_from),
        "bytes": resume_from.stat().st_size,
        "args_yaml": {"path": str(args_yaml), "sha256": sha256(args_yaml)},
        "results_csv": {"path": str(results_csv), "sha256": sha256(results_csv)},
        "completed_epochs": completed_epochs,
        "quality_parameters_unchanged": True,
    }


def main() -> None:
    args = build_parser().parse_args()
    if not 0.0 <= args.mosaic <= 1.0:
        raise ValueError("--mosaic must be between 0 and 1")
    if args.close_mosaic < 0:
        raise ValueError("--close-mosaic must be non-negative")
    if args.mask_ratio < 1:
        raise ValueError("--mask-ratio must be at least 1")
    if args.hard_boundary_weight < 0:
        raise ValueError("--hard-boundary-weight must be non-negative")
    if args.hard_boundary_kernel < 3 or args.hard_boundary_kernel % 2 == 0:
        raise ValueError("--hard-boundary-kernel must be an odd integer >= 3")
    batch = parse_batch(args.batch)
    dataset_yaml = Path(args.dataset).resolve()
    output_dir = Path(args.output_dir).resolve()
    resume_from = Path(args.resume_from).resolve() if args.resume_from else None
    if resume_from is not None and not resume_from.is_file():
        raise ValueError("--resume-from must point to an existing last.pt checkpoint")
    if resume_from is not None and args.finalize_existing_run:
        raise ValueError("--resume-from cannot be combined with --finalize-existing-run")
    config = load_dataset_config(dataset_yaml)
    preflight_removed_caches = (
        remove_ultralytics_label_caches(config.dataset_root)
        if args.finalize_existing_run or args.experiment_plan
        else []
    )
    candidate_input_evidence = candidate_input_validation(
        args, dataset_yaml, output_dir
    )
    experiment_evidence = experiment_plan_validation(
        args, dataset_yaml, output_dir, batch
    )
    distillation_evidence = resolve_distillation_evidence(args)
    from nail_texture_boundary_loss import (
        HardBoundaryConfig,
        configure_hard_boundary_loss,
        current_hard_boundary_contract,
    )

    configure_hard_boundary_loss(
        HardBoundaryConfig(
            weight=args.hard_boundary_weight,
            kernel_size=args.hard_boundary_kernel,
        )
    )
    hard_boundary_evidence = current_hard_boundary_contract()
    runtime_dataset_yaml = output_dir / "resolved-dataset.yaml"
    resume_evidence = (
        validate_resume_contract(
            resume_from, args, batch, runtime_dataset_yaml, output_dir
        )
        if resume_from is not None
        else None
    )

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
        "resume_from": resume_evidence,
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
        "hard_boundary": hard_boundary_evidence,
        "distillation": distillation_evidence,
        "run_name": args.run_name,
        "output_dir": str(output_dir),
        "run_dir": str(resolve_training_run_dir(output_dir, args.run_name)),
        "best_weights_path": str(resolve_best_weights_path(output_dir, args.run_name)),
        "training_intent": (
            "candidate" if args.candidate_mode else
            "pre-registered-development-experiment" if experiment_evidence is not None else
            "experiment"
        ),
        "candidate_input_evidence": candidate_input_evidence,
        "candidate_validation_evidence": None,
        "development_experiment_evidence": experiment_evidence,
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
        if experiment_evidence is not None:
            experiment_plan_validation(args, dataset_yaml, output_dir, batch)
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
    if args.hard_boundary_weight > 0:
        from nail_texture_boundary_loss import install_hard_boundary_criterion

        install_hard_boundary_criterion()
    if distillation_evidence is not None:
        import ultralytics.engine.trainer as ultralytics_trainer
        from nail_texture_distillation import JiaRuSegmentationDistillationModel

        # Trainer通过该符号构造包装模型；子类仍可被Ultralytics的保存/解包逻辑识别。
        ultralytics_trainer.DistillationModel = JiaRuSegmentationDistillationModel
    write_resolved_dataset_yaml(runtime_dataset_yaml, config)
    model = ultralytics.YOLO(str(resume_from) if resume_from is not None else args.model)
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
    try:
        if resume_from is not None:
            results = model.train(resume=True)
        else:
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
    except BaseException:
        if experiment_evidence is not None:
            # 失败运行也不能把Ultralytics扫描缓存遗留在哈希绑定的数据副本中。
            remove_ultralytics_label_caches(config.dataset_root)
            experiment_plan_validation(args, dataset_yaml, output_dir, batch)
        raise
    results_dir = Path(getattr(results, "save_dir", output_dir)).resolve()
    actual_best_weights_path = results_dir / "weights" / "best.pt"
    if args.candidate_mode:
        # Re-run the full evidence chain after training so a dataset or upstream
        # mutation during the run cannot produce an eligible candidate summary.
        remove_ultralytics_label_caches(config.dataset_root)
        candidate_input_validation(args, dataset_yaml, output_dir)
    if experiment_evidence is not None:
        # Ultralytics的labels/*.cache是可再生扫描缓存；只清理这两个已知
        # 副作用后重放开发折与完整文件树，证明图片和标签未发生漂移。
        removed_experiment_caches = [
            *preflight_removed_caches,
            *remove_ultralytics_label_caches(config.dataset_root),
        ]
        experiment_plan_validation(args, dataset_yaml, output_dir, batch)
    else:
        removed_experiment_caches = []
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
            "removed_ultralytics_label_caches": removed_experiment_caches,
        },
    )
    print(f"Training finished. Summary written to {output_dir / 'train-summary.json'}")


if __name__ == "__main__":
    main()
