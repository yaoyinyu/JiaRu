# real-reference-2026-07-12-batch-02

This seed batch was bootstrapped from a real local image directory.

Next commands:

```bash
node --no-warnings --experimental-strip-types scripts/batch-verify-nail-detection.ts --image-dir "E:/AI Project/Codex/JiaRu/辅助材料/real-material-review-2026-07-12/images" --output-dir "E:/AI Project/Codex/JiaRu/辅助材料/real-material-review-2026-07-12/debug" --prefix real-reference-2026-07-12-batch-02 --fixture-dir "E:/AI Project/Codex/JiaRu/辅助材料/real-material-review-2026-07-12/fixtures"
node --no-warnings --experimental-strip-types model/training/audit-screening-review.ts --root-dir "E:/AI Project/Codex/JiaRu/辅助材料/real-material-review-2026-07-12"
node --no-warnings --experimental-strip-types model/training/build-reviewed-intake-batch.ts --root-dir "E:/AI Project/Codex/JiaRu/辅助材料/real-material-review-2026-07-12"
```
