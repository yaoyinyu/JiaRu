# AI-generated nail image intake

Date: 2026-07-04

This document records how local AI-generated nail images are brought into the Phase 1 nail-texture dataset pipeline. These images can be used as internal training candidates after review, but fallback-generated masks are only bootstrap labels; they still need human inspection before real model training.

## Current local batch

Source directory:

```text
E:/AI Project/Codex/JiaRu/image
```

Generated manifest:

```text
E:/AI Project/Codex/JiaRu/model/datasets/nail-texture-v1/metadata/ai-nail-2026-07-04.manifest.json
```

Validation report:

```text
E:/AI Project/Codex/JiaRu/model/datasets/nail-texture-v1/metadata/ai-nail-2026-07-04.manifest.report.json
```

Intake report:

```text
E:/AI Project/Codex/JiaRu/model/datasets/nail-texture-v1/metadata/phase1-intake-ai-nail-2026-07-04.report.json
```

## Commands used

Create a recursive intake manifest from the local `image` directory:

```bash
node --no-warnings --experimental-strip-types model/training/init-intake-batch.ts \
  --image-dir image \
  --output model/datasets/nail-texture-v1/metadata/ai-nail-2026-07-04.manifest.json \
  --source-group ai-nail-2026-07-04 \
  --origin-type other \
  --license ai-generated-internal-training-candidate \
  --default-origin-ref "local AI generation batch in E:/AI Project/Codex/JiaRu/image on 2026-07-04" \
  --recursive
```

Validate that every manifest entry is a safe relative path and a decodable image:

```bash
node --no-warnings --experimental-strip-types model/training/validate-intake-batch.ts \
  --manifest model/datasets/nail-texture-v1/metadata/ai-nail-2026-07-04.manifest.json \
  --image-dir image
```

Run the Phase 1 intake pipeline:

```bash
node --no-warnings --experimental-strip-types model/training/run-phase1-intake-pipeline.ts \
  --manifest model/datasets/nail-texture-v1/metadata/ai-nail-2026-07-04.manifest.json \
  --image-dir image
```

After changing split logic or labels, refresh split/conversion/readiness:

```bash
node --no-warnings --experimental-strip-types model/training/split-dataset.ts
node --no-warnings --experimental-strip-types model/training/audit-labels.ts
node --no-warnings --experimental-strip-types model/training/convert-annotations.ts
node --no-warnings --experimental-strip-types model/training/audit-phase1-readiness.ts
```

Refresh release-mode dataset authorization evidence:

```bash
node --no-warnings --experimental-strip-types model/training/verify-training-dataset-readiness.ts \
  --dataset-root model/datasets/nail-texture-v1 \
  --authorization-mode release
```

## Current acceptance evidence

- 300 local AI-generated images were discovered recursively.
- 300/300 images decoded successfully; all reported as 1024x1024.
- Phase 1 intake pipeline completed with `ok=true`.
- Dataset now has 300 annotation JSON files and 1411 fallback-generated nail polygons.
- Dataset split is now 210 train / 45 val / 45 test after the single-source split fix.
- `audit-labels.ts` reports 300 files, 0 errors, 0 warnings.
- `convert-annotations.ts` converted 300 YOLO segmentation label files.

## Remaining manual/model work

- The 1411 masks are fallback bootstrap labels, not final reviewed masks. Human review should correct obvious false positives, missing nails, and edge shapes before training.
- Phase 1 readiness is still not fully green because the test split does not yet contain explicit negative samples or complex-background samples.
- MVP readiness still fails until a real ONNX segmentation model is trained/exported and placed under `public/models/nail-texture-seg/` with `modelSizeBytes` and `sha256` manifest integrity fields.
## Mark reviewed Phase 1 coverage samples

After human review, use `mark-phase1-samples.ts` to explicitly mark special coverage samples. This tool updates the annotation JSON, `metadata/sources.csv`, `metadata/split.json`, and writes `metadata/phase1-sample-marking-report.json`.

Mark a reviewed complex-background sample and force it into the test split:

```bash
node --no-warnings --experimental-strip-types model/training/mark-phase1-samples.ts \
  --file reviewed-complex-background.jpg \
  --background mixed \
  --reason complex_background \
  --sample ai_generated \
  --ensure-test
```

Mark a reviewed negative sample only after confirming the image has no nail-texture target. If the annotation file still contains polygons, pass `--clear-annotations` intentionally:

```bash
node --no-warnings --experimental-strip-types model/training/mark-phase1-samples.ts \
  --file reviewed-negative.jpg \
  --negative true \
  --clear-annotations \
  --ensure-test
```

Safety notes:

- The tool refuses `--negative true` when annotations still exist unless `--clear-annotations` is provided.
- The tool requires the file to already exist in `metadata/sources.csv`, because readiness gates depend on source metadata.
- Do not infer negative samples from names such as "negative space"; a negative sample means there is no valid nail-texture region to segment.
## Generate a Phase 1 review candidate list

Use `plan-phase1-review-candidates.ts` before manually marking coverage samples. It reads the current dataset, ranks likely complex-background samples, lists weak possible-negative candidates, and writes both JSON and CSV review artifacts:

```bash
node --no-warnings --experimental-strip-types model/training/plan-phase1-review-candidates.ts --top 10
```

Generated artifacts:

```text
model/datasets/nail-texture-v1/metadata/phase1-review-candidates.json
model/datasets/nail-texture-v1/metadata/phase1-review-candidates.csv
```

Current generated report summary:

- 28 complex-background review candidates found.
- 9 possible negative review candidates found, all high-risk and requiring visual confirmation.
- Several complex-background candidates are already in the test split and only need a confirmed `mark-phase1-samples.ts` command.
- No safe automatic negative sample was found; if none of the candidates is truly non-target, add dedicated no-nail/non-target negative images instead of relabeling nail-art images.