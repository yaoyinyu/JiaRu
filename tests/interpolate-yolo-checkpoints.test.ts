import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

const script = path.resolve(
  "model/training/interpolate-yolo-checkpoints.py",
);
const python = process.env.PYTHON ?? "python";

const hasTorch = (): boolean =>
  spawnSync(python, ["-c", "import torch"], { encoding: "utf8" }).status === 0;

const buildCheckpoint = (
  output: string,
  weight: number,
  batches: number,
): void => {
  const code = [
    "import sys, torch",
    "model=torch.nn.Sequential(torch.nn.Linear(2,2),torch.nn.BatchNorm1d(2))",
    "value=float(sys.argv[2]); batches=int(sys.argv[3])",
    "state=model.state_dict()",
    "[(tensor.fill_(value) if tensor.is_floating_point() else tensor.fill_(batches)) for tensor in state.values()]",
    "model.load_state_dict(state)",
    "torch.save({'model':model,'ema':None,'optimizer':None,'scaler':None,'updates':None,'epoch':3,'best_fitness':0.5},sys.argv[1])",
  ].join(";");
  const result = spawnSync(
    python,
    ["-c", code, output, String(weight), String(batches)],
    { encoding: "utf8" },
  );
  assert.equal(result.status, 0, result.stderr);
};

test("checkpoint interpolation is exact, hash-bound, and deeply replayable", (t) => {
  if (!hasTorch()) {
    t.skip("PyTorch is unavailable in this Python runtime");
    return;
  }

  const root = mkdtempSync(path.join(tmpdir(), "checkpoint-interpolation-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const base = path.join(root, "base.pt");
  const tuned = path.join(root, "tuned.pt");
  const output = path.join(root, "alpha-025.pt");
  const report = path.join(root, "alpha-025.json");
  buildCheckpoint(base, 1, 0);
  buildCheckpoint(tuned, 3, 4);

  const created = spawnSync(
    python,
    [
      script,
      "--base",
      base,
      "--tuned",
      tuned,
      "--alpha",
      "0.25",
      "--output",
      output,
      "--report",
      report,
    ],
    { encoding: "utf8" },
  );
  assert.equal(created.status, 0, created.stderr);
  const document = JSON.parse(readFileSync(report, "utf8"));
  assert.equal(document.decision, "interpolated_candidate_checkpoint");
  assert.equal(document.releaseStatus, "diagnostic-only-pending-validation");
  assert.equal(document.interpolation.baseWeight, 0.75);
  assert.equal(document.interpolation.tunedWeight, 0.25);

  const inspect = spawnSync(
    python,
    [
      "-c",
      [
        "import sys, torch",
        "checkpoint=torch.load(sys.argv[1],map_location='cpu',weights_only=False)",
        "state=checkpoint['model'].state_dict()",
        "floating=[v for v in state.values() if v.is_floating_point()]",
        "integers=[v for v in state.values() if not v.is_floating_point()]",
        "assert all(torch.all(v==1.5) for v in floating)",
        "assert all(torch.all(v==0) for v in integers)",
      ].join(";"),
      output,
    ],
    { encoding: "utf8" },
  );
  assert.equal(inspect.status, 0, inspect.stderr);

  const verified = spawnSync(
    python,
    [script, "--verify-report", report],
    { encoding: "utf8" },
  );
  assert.equal(verified.status, 0, verified.stderr);

  const overwrite = spawnSync(
    python,
    [
      script,
      "--base",
      base,
      "--tuned",
      tuned,
      "--alpha",
      "0.25",
      "--output",
      output,
      "--report",
      path.join(root, "other-report.json"),
    ],
    { encoding: "utf8" },
  );
  assert.notEqual(overwrite.status, 0);
  assert.match(overwrite.stderr, /refusing to overwrite existing output/);
});

test("verification rejects checkpoint drift", (t) => {
  if (!hasTorch()) {
    t.skip("PyTorch is unavailable in this Python runtime");
    return;
  }

  const root = mkdtempSync(path.join(tmpdir(), "checkpoint-drift-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const base = path.join(root, "base.pt");
  const tuned = path.join(root, "tuned.pt");
  const output = path.join(root, "derived.pt");
  const report = path.join(root, "derived.json");
  buildCheckpoint(base, 1, 0);
  buildCheckpoint(tuned, 3, 4);
  const created = spawnSync(
    python,
    [
      script,
      "--base",
      base,
      "--tuned",
      tuned,
      "--alpha",
      "0.5",
      "--output",
      output,
      "--report",
      report,
    ],
    { encoding: "utf8" },
  );
  assert.equal(created.status, 0, created.stderr);

  buildCheckpoint(tuned, 5, 8);
  const verified = spawnSync(
    python,
    [script, "--verify-report", report],
    { encoding: "utf8" },
  );
  assert.notEqual(verified.status, 0);
  assert.match(verified.stderr, /tuned checkpoint SHA-256 drifted/);
});
