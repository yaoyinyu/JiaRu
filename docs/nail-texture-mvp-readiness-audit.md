# Nail texture recognition MVP readiness audit

Version: v1.3  
Date: 2026-07-04

This gate maps to the MVP acceptance checklist in `docs/nail-texture-recognition-model-plan.md` section 14. It does not replace training, browser testing, or manual review. Its job is to make the current MVP gaps explicit and repeatable.

## Command

```bash
npm.cmd run audit:mvp-readiness
```

To refresh all authoritative dataset evidence first and persist both the MVP report and an orchestration report, run:

```bash
npm.cmd run audit:mvp-readiness:refresh
```

The refresh command always executes the final MVP audit, even when source, authorization, or Phase 1 gates fail. This creates useful failure evidence instead of stopping after the first missing prerequisite.

Default persisted artifacts:

- `model/datasets/nail-texture-v1/metadata/training-dataset-readiness-release.json`
- `model/exports/nail-texture-mvp-readiness.json`
- `model/exports/nail-texture-mvp-readiness-refresh.json`

The refresh command exits non-zero until every gate passes. A non-zero result with all three reports written is expected while the authorized dataset or real ONNX model is still missing.

You can also pass explicit paths:

```bash
node --no-warnings --experimental-strip-types scripts/audit-nail-texture-mvp-readiness.ts --dataset-root model/datasets/nail-texture-v1 --manifest public/models/nail-texture-seg/manifest.json --output model/exports/mvp-readiness.json
```

## Checks

The script writes a JSON report with ten checks:

- `phase1_dataset`: reads `metadata/phase1-readiness.json` and requires at least 200 images, 800 valid nail masks, a passing label audit, a test split, negative samples, and complex-background test samples.
- `training_source_authorization`: reads `metadata/training-dataset-readiness-release.json` and requires release-mode source authorization to pass. This prevents a dataset from passing MVP readiness with enough masks but unclear training rights.
  If `sources.csv` is absent, the authorization audit persists a structured `missing_sources_csv` error report instead of terminating with an unhandled filesystem exception.
  A present but empty inventory is also rejected by both source integrity and authorization gates with `empty_sources_csv`; a header-only file is not valid training provenance.
- `training_toolchain`: verifies that training, evaluation, export, annotation conversion, label audit, and release orchestration scripts exist.
- `baseline_fixture_toolchain`: verifies that the reusable green-circle fixture parser, the 5188 reference fixture, single-image verification, batch fallback overlay verification, fallback annotation export, and related docs are present. This is a non-training completeness check; it does not import or train on real images.
- `browser_model_asset`: verifies that the browser model manifest is valid, that the referenced ONNX model file exists, that it is not a placeholder-sized file below 256KB, and that it stays within the 15MB MVP browser budget. Files at or below the 8MB ideal target are reported as `sizeTier: "ideal"`; files between 8MB and 15MB can pass as `sizeTier: "mvp"` with an optimization warning.
- `browser_integration`: verifies model runtime, worker, fallback adapter, and `NailArtPicker` recognition wiring markers.
- `feedback_loop_toolchain`: verifies that user correction/debug sample export support, debug-sample import, active-learning prioritization, active-learning trace handoff, reviewed-batch import, and reviewed-batch release handoff scripts/docs are present. This is a non-training completeness check; it does not import real user images or create real training data.
- `quality_performance_gates`: verifies that Phase 3/4 browser integration, recognition performance, texture quality, real-model readiness, and model-output fixture verification scripts/docs are present. This is a non-training completeness check; it does not require real model metrics or release-test-split evidence to pass.
- `release_governance_toolchain`: verifies that Phase 5 release governance, rollback, trace/history, A/B comparison, and failure-taxonomy scripts/docs are present. This is a non-training completeness check; it does not require real model metrics or real release data.
- `validation_commands`: verifies that `package.json` defines `test`, `lint`, `build`, `audit:encoding`, `audit:mvp-readiness`, and `audit:mvp-readiness:refresh`, and declares the browser runtime dependency `onnxruntime-web`.

## Baseline fixture and fallback overlay completeness

The `baseline_fixture_toolchain` check maps to the plan's early “green-circle truth to reusable fixture” requirement. It verifies that the repository keeps the non-training tools needed to turn a manually circled reference image into repeatable detection evidence:

- green-circle component parsing and fixture comparison helpers;
- the 5188 reference fixture used by regression tests;
- single-image detection verification;
- batch fallback overlay precheck for seed batches;
- fallback annotation export for later human review.

This check proves the baseline fixture workflow exists. It does not claim that new web images are authorized, reviewed, or ready for training.
## Expected state before real data and model assets exist

Before the authorized dataset and real ONNX model are available, this audit should return `ok: false`. That is intentional: it prevents us from treating engineering scaffolding as a completed MVP.

The current expected remaining failures are:

- Real Phase 1 dataset evidence is missing: the project still needs 200 images, 800 valid masks, and covered test split evidence.
- Release-mode source authorization evidence is missing: run `model/training/verify-training-dataset-readiness.ts` after `sources.csv` is populated and fix authorization issues before release training.
- Real browser model asset is missing or not credible: `public/models/nail-texture-seg/manifest.json` exists, but the referenced ONNX file has not been generated yet. If a tiny placeholder file is present, the gate reports `sizeTier: "placeholder"` and remains failed.

The Phase 3 runtime dependency is now declared in `package.json` and `package-lock.json` through `onnxruntime-web`. Once the real model exists, rerun this audit together with `verify-model-artifact`, `verify-browser-integration`, browser manual testing, `npm.cmd test`, `npm.cmd run lint`, and `npm.cmd run build`.
## Actionable commands

Every check now includes a `commands` array. Passing checks return an empty array. Failed checks return commands that directly advance the missing evidence.

The report also includes a top-level deduplicated `nextCommands` array. For the current repository state, it includes commands for:

- regenerating Phase 1 readiness and collection planning;
- generating the first-batch execution checklist;
- running release-mode dataset/source authorization readiness;
- running the training release pipeline;
- verifying the exported model artifact;
- verifying browser integration after the ONNX file exists.

These commands are recommendations, not proof of completion. Each command still needs to run successfully and produce the required evidence before the corresponding readiness check can pass.

## Model artifact integrity metadata

`model/training/export-onnx.py` writes two integrity fields into `manifest.json` after copying the exported ONNX file:

- `modelSizeBytes`: exact byte size of the referenced ONNX file.
- `sha256`: SHA-256 digest of the referenced ONNX file.

`verify-model-artifact.ts` verifies these fields whenever they are present. `verify-training-release.ts` runs artifact verification with `--require-integrity`, so release candidates must include both fields and they must match the ONNX file on disk. This prevents a model file from being replaced without updating the manifest evidence.

## Phase 5 governance completeness check

The `release_governance_toolchain` check keeps the readiness audit aligned with the plan's Phase 5 requirements before real training resumes. It verifies that the repository still contains the scripts and docs needed for:

- model A/B comparison;
- release decision reporting;
- promotion and rollback verification;
- release trace and history registration;
- model registry switching;
- failure classification auditing and summary generation.

This check can pass even while `phase1_dataset`, `training_source_authorization`, or `browser_model_asset` are still red, because those remaining gates depend on real authorized data and a real exported model.
## Phase 3/4 quality and performance gate completeness

The `quality_performance_gates` check verifies that the project still has the non-training validation tools needed before a browser model is trusted:

- browser integration contract verification;
- recognition performance budget verification;
- texture quality gate verification;
- real-model readiness verification;
- model-output fixture verification.

This check proves the validation entry points exist, not that a real model has passed them. Real model artifacts, release-test-split texture quality evidence, and performance sample reports are still validated by their dedicated gates when those artifacts exist.
## User correction and active-learning feedback-loop completeness

The `feedback_loop_toolchain` check maps to the plan's user-correction feedback-loop requirement. It verifies that the repository keeps the non-training tools needed to move from a corrected browser sample toward future training evidence:

- local debug sample creation and comparison helpers;
- debug sample import into dataset annotations;
- active-learning prioritization and pipeline orchestration;
- active-learning release trace draft and handoff generation;
- reviewed-batch preparation, import, and release handoff.

This check proves the feedback-loop entry points exist. It does not claim that user images are authorized, reviewed, imported, or ready for real training.