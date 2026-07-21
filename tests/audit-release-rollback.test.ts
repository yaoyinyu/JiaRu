import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { createHash } from "node:crypto";
import { link, mkdtemp, mkdir, readFile, unlink, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import test from "node:test";
import {
  RELEASE_ROLLBACK_AUDIT_VERSION,
  verifyApprovedReleaseRollbackReport,
} from "../scripts/lib/release-rollback-audit.ts";

const execFileAsync = promisify(execFile);

function sha256Buffer(buffer: Buffer): string {
  return createHash("sha256").update(buffer).digest("hex");
}

async function createManifest(modelDir: string, version: string, sizeBytes = 1024) {
  const manifestPath = path.join(modelDir, "manifest.json");
  const modelFile = `${version}.onnx`;
  const modelBuffer = Buffer.alloc(sizeBytes);
  await writeFile(
    manifestPath,
    JSON.stringify(
      {
        version,
        inputSize: 640,
        task: "segment",
        backendPreferences: ["webgpu", "wasm"],
        modelFile,
        modelSizeBytes: sizeBytes,
        sha256: sha256Buffer(modelBuffer),
        labels: ["nail_texture"],
      },
      null,
      2
    ),
    "utf8"
  );
  await writeFile(path.join(modelDir, modelFile), modelBuffer, "binary");
  return { manifestPath, modelPath: path.join(modelDir, modelFile) };
}

async function registerRelease(manifestPath: string, registryPath: string) {
  await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "scripts/register-model-release.ts",
      "--manifest",
      manifestPath,
      "--registry",
      registryPath,
    ],
    { cwd: path.resolve(".") }
  );
}

async function runAudit(registryPath: string, manifestPath: string, outputPath?: string) {
  const args = [
    "--no-warnings",
    "--experimental-strip-types",
    "scripts/audit-release-rollback.ts",
    "--registry",
    registryPath,
    "--manifest",
    manifestPath,
  ];
  if (outputPath) args.push("--output", outputPath);

  return execFileAsync(process.execPath, args, { cwd: path.resolve(".") });
}

test("audit-release-rollback passes when current and rollback releases are complete", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-release-rollback-pass-"));
  const modelDir = path.join(root, "public", "models", "nail-texture-seg");
  await mkdir(modelDir, { recursive: true });
  const registryPath = path.join(modelDir, "release-registry.json");
  const outputPath = path.join(root, "rollback-audit.json");

  await registerRelease((await createManifest(modelDir, "nail-texture-seg-v1")).manifestPath, registryPath);
  const activeManifestPath = (await createManifest(modelDir, "nail-texture-seg-v2", 2048)).manifestPath;
  await registerRelease(activeManifestPath, registryPath);

  const { stdout } = await runAudit(registryPath, activeManifestPath, outputPath);
  const summary = JSON.parse(stdout) as {
    version: string;
    ok: boolean;
    decision: string;
    inputs: {
      registry: { path: string; sha256: string };
      activeManifest: { path: string; sha256: string };
    };
    currentVersion: string;
    releaseCount: number;
    rollbackCandidateCount: number;
    rollbackCandidates: string[];
    errors: string[];
    releases: Array<{ integrityOk: boolean; modelSizeBytes: number; actualModelSizeBytes: number; sha256: string; actualSha256: string }>;
  };

  assert.equal(summary.version, RELEASE_ROLLBACK_AUDIT_VERSION);
  assert.equal(summary.ok, true);
  assert.equal(summary.decision, "approved_release_rollback_audit");
  assert.equal(path.resolve(summary.inputs.registry.path), path.resolve(registryPath));
  assert.match(summary.inputs.registry.sha256, /^[a-f0-9]{64}$/);
  assert.equal(path.resolve(summary.inputs.activeManifest.path), path.resolve(activeManifestPath));
  assert.match(summary.inputs.activeManifest.sha256, /^[a-f0-9]{64}$/);
  assert.equal(summary.currentVersion, "nail-texture-seg-v2");
  assert.equal(summary.releaseCount, 2);
  assert.equal(summary.rollbackCandidateCount, 1);
  assert.deepEqual(summary.rollbackCandidates, ["nail-texture-seg-v1"]);
  assert.deepEqual(summary.errors, []);
  assert.equal(summary.releases.length, 2);
  for (const release of summary.releases) {
    assert.equal(release.integrityOk, true);
    assert.equal(release.modelSizeBytes, release.actualModelSizeBytes);
    assert.equal(release.sha256, release.actualSha256);
  }

  const persisted = JSON.parse(await readFile(outputPath, "utf8")) as { ok: boolean };
  assert.equal(persisted.ok, true);
  const verification = await verifyApprovedReleaseRollbackReport(outputPath, registryPath, activeManifestPath);
  assert.equal(verification.ok, true, verification.errors.join("\n"));
});

test("audit-release-rollback never overwrites registry, manifests, snapshots, models, or hard-link aliases", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-release-rollback-output-protection-"));
  const modelDir = path.join(root, "public", "models", "nail-texture-seg");
  await mkdir(modelDir, { recursive: true });
  const registryPath = path.join(modelDir, "release-registry.json");
  await registerRelease((await createManifest(modelDir, "nail-texture-seg-v1")).manifestPath, registryPath);
  const active = await createManifest(modelDir, "nail-texture-seg-v2", 2048);
  await registerRelease(active.manifestPath, registryPath);
  const registry = JSON.parse(await readFile(registryPath, "utf8")) as {
    releases: Array<{ version: string; manifestSnapshotPath: string; modelPath: string }>;
  };
  const previous = registry.releases.find((release) => release.version === "nail-texture-seg-v1");
  assert.ok(previous);
  const protectedPaths = [
    registryPath,
    active.manifestPath,
    previous.manifestSnapshotPath,
    previous.modelPath,
    active.modelPath,
  ];

  for (const protectedPath of protectedPaths) {
    const before = await readFile(protectedPath);
    await assert.rejects(
      runAudit(registryPath, active.manifestPath, protectedPath),
      (error: Error & { stderr?: string }) => {
        assert.match(error.stderr ?? error.message, /must not overwrite an input evidence file/);
        return true;
      },
    );
    assert.deepEqual(await readFile(protectedPath), before);
  }

  if (process.platform === "win32") {
    const caseAlias = path.join(path.dirname(active.manifestPath), path.basename(active.manifestPath).toUpperCase());
    const before = await readFile(active.manifestPath);
    await assert.rejects(
      runAudit(registryPath, active.manifestPath, caseAlias),
      (error: Error & { stderr?: string }) => {
        assert.match(error.stderr ?? error.message, /must not overwrite an input evidence file/);
        return true;
      },
    );
    assert.deepEqual(await readFile(active.manifestPath), before);
  }

  const hardLinkAlias = path.join(root, "registered-model-hard-link-output.json");
  await link(previous.modelPath, hardLinkAlias);
  const before = await readFile(previous.modelPath);
  await assert.rejects(
    runAudit(registryPath, active.manifestPath, hardLinkAlias),
    (error: Error & { stderr?: string }) => {
      assert.match(error.stderr ?? error.message, /must not overwrite an input evidence file alias/);
      return true;
    },
  );
  assert.deepEqual(await readFile(previous.modelPath), before);
});

test("rollback report verifier rejects a fully hand-written PASS without real registry or model evidence", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-release-rollback-forged-"));
  const registryPath = path.join(root, "missing-release-registry.json");
  const manifestPath = path.join(root, "missing-manifest.json");
  const outputPath = path.join(root, "forged-rollback-audit.json");
  const fakeSha = "a".repeat(64);
  await writeFile(outputPath, JSON.stringify({
    version: RELEASE_ROLLBACK_AUDIT_VERSION,
    ok: true,
    decision: "approved_release_rollback_audit",
    inputs: {
      registry: { path: registryPath, sha256: fakeSha },
      activeManifest: { path: manifestPath, sha256: fakeSha },
      requireRollbackCandidate: true,
    },
    currentVersion: "nail-texture-seg-v2",
    releaseCount: 2,
    rollbackCandidateCount: 1,
    rollbackCandidates: ["nail-texture-seg-v1"],
    releases: [
      { version: "nail-texture-seg-v2", isCurrent: true, ok: true, integrityOk: true, errors: [] },
      { version: "nail-texture-seg-v1", isCurrent: false, ok: true, integrityOk: true, errors: [] },
    ],
    activeRelease: { version: "nail-texture-seg-v2", ok: true, errors: [] },
    errors: [],
    warnings: [],
    nextSteps: ["PASS"],
  }, null, 2), "utf8");

  const verification = await verifyApprovedReleaseRollbackReport(outputPath, registryPath, manifestPath);
  assert.equal(verification.found, true);
  assert.equal(verification.ok, false);
  assert.match(verification.errors.join(" "), /cannot replay rollback evidence/);
});

test("rollback report verifier rejects model drift after a passing report was written", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-release-rollback-drift-"));
  const modelDir = path.join(root, "public", "models", "nail-texture-seg");
  await mkdir(modelDir, { recursive: true });
  const registryPath = path.join(modelDir, "release-registry.json");
  const outputPath = path.join(root, "rollback-audit.json");
  await registerRelease((await createManifest(modelDir, "nail-texture-seg-v1")).manifestPath, registryPath);
  const active = await createManifest(modelDir, "nail-texture-seg-v2", 2048);
  await registerRelease(active.manifestPath, registryPath);
  await runAudit(registryPath, active.manifestPath, outputPath);

  await writeFile(active.modelPath, Buffer.from("model-drift-after-report"), "binary");
  const verification = await verifyApprovedReleaseRollbackReport(outputPath, registryPath, active.manifestPath);
  assert.equal(verification.ok, false);
  assert.match(
    verification.errors.join(" "),
    /modelSizeBytes|sha256|stored rollback audit report differs from current-state replay/,
  );
});

test("audit-release-rollback fails when no rollback candidate exists", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-release-rollback-single-"));
  const modelDir = path.join(root, "public", "models", "nail-texture-seg");
  await mkdir(modelDir, { recursive: true });
  const registryPath = path.join(modelDir, "release-registry.json");
  const manifestPath = (await createManifest(modelDir, "nail-texture-seg-v1")).manifestPath;
  await registerRelease(manifestPath, registryPath);

  await assert.rejects(
    runAudit(registryPath, manifestPath),
    (error: Error & { stdout?: string }) => {
      const summary = JSON.parse(error.stdout ?? "{}") as {
        ok: boolean;
        rollbackCandidateCount: number;
        errors: string[];
      };
      assert.equal(summary.ok, false);
      assert.equal(summary.rollbackCandidateCount, 0);
      assert.ok(summary.errors.some((item) => item.includes("at least one non-current release")));
      return true;
    }
  );
});

test("audit-release-rollback fails when a snapshot or model file is missing", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-release-rollback-missing-"));
  const modelDir = path.join(root, "public", "models", "nail-texture-seg");
  await mkdir(modelDir, { recursive: true });
  const registryPath = path.join(modelDir, "release-registry.json");
  await registerRelease((await createManifest(modelDir, "nail-texture-seg-v1")).manifestPath, registryPath);
  const activeManifestPath = (await createManifest(modelDir, "nail-texture-seg-v2", 2048)).manifestPath;
  await registerRelease(activeManifestPath, registryPath);

  const registry = JSON.parse(await readFile(registryPath, "utf8")) as {
    releases: Array<{ version: string; manifestSnapshotPath: string; modelPath: string }>;
  };
  const oldRelease = registry.releases.find((release) => release.version === "nail-texture-seg-v1");
  assert.ok(oldRelease);
  await unlink(oldRelease.modelPath);

  await assert.rejects(
    runAudit(registryPath, activeManifestPath),
    (error: Error & { stdout?: string }) => {
      const summary = JSON.parse(error.stdout ?? "{}") as {
        ok: boolean;
        errors: string[];
      };
      assert.equal(summary.ok, false);
      assert.ok(summary.errors.some((item) => item.includes("model file is missing")));
      return true;
    }
  );
});

test("audit-release-rollback fails when a registered model file is modified after release", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-release-rollback-corrupt-"));
  const modelDir = path.join(root, "public", "models", "nail-texture-seg");
  await mkdir(modelDir, { recursive: true });
  const registryPath = path.join(modelDir, "release-registry.json");
  const v1 = await createManifest(modelDir, "nail-texture-seg-v1", 1024);
  await registerRelease(v1.manifestPath, registryPath);
  const activeManifestPath = (await createManifest(modelDir, "nail-texture-seg-v2", 2048)).manifestPath;
  await registerRelease(activeManifestPath, registryPath);

  await writeFile(v1.modelPath, Buffer.from("corrupted-model"), "binary");

  await assert.rejects(
    runAudit(registryPath, activeManifestPath),
    (error: Error & { stdout?: string }) => {
      const summary = JSON.parse(error.stdout ?? "{}") as {
        ok: boolean;
        errors: string[];
        releases: Array<{ version: string; integrityOk: boolean }>;
      };
      assert.equal(summary.ok, false);
      assert.ok(summary.errors.some((item) => item.includes("modelSizeBytes") || item.includes("sha256")));
      assert.equal(summary.releases.find((release) => release.version === "nail-texture-seg-v1")?.integrityOk, false);
      return true;
    }
  );
});

test("audit-release-rollback fails when a registered manifest snapshot drifts", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-release-rollback-snapshot-drift-"));
  const modelDir = path.join(root, "public", "models", "nail-texture-seg");
  await mkdir(modelDir, { recursive: true });
  const registryPath = path.join(modelDir, "release-registry.json");
  await registerRelease((await createManifest(modelDir, "nail-texture-seg-v1")).manifestPath, registryPath);
  const activeManifestPath = (await createManifest(modelDir, "nail-texture-seg-v2", 2048)).manifestPath;
  await registerRelease(activeManifestPath, registryPath);
  const registry = JSON.parse(await readFile(registryPath, "utf8")) as {
    releases: Array<{ version: string; manifestSnapshotPath: string }>;
  };
  const snapshotPath = registry.releases.find((release) => release.version === "nail-texture-seg-v1")?.manifestSnapshotPath;
  assert.ok(snapshotPath);
  const snapshot = JSON.parse(await readFile(snapshotPath, "utf8"));
  await writeFile(snapshotPath, JSON.stringify({ ...snapshot, inputSize: 320 }, null, 2), "utf8");

  await assert.rejects(
    runAudit(registryPath, activeManifestPath),
    (error: Error & { stdout?: string }) => {
      const summary = JSON.parse(error.stdout ?? "{}") as { ok: boolean; errors: string[] };
      assert.equal(summary.ok, false);
      assert.ok(summary.errors.some((item) => item.includes("snapshot inputSize")));
      return true;
    },
  );
});

test("audit-release-rollback rejects invalid runtime contracts and active-manifest fields omitted by the registry", async (t) => {
  await t.test("invalid historical runtime contract", async () => {
    const root = await mkdtemp(path.join(os.tmpdir(), "nail-release-rollback-runtime-contract-"));
    const modelDir = path.join(root, "public", "models", "nail-texture-seg");
    await mkdir(modelDir, { recursive: true });
    const registryPath = path.join(modelDir, "release-registry.json");
    await registerRelease((await createManifest(modelDir, "nail-texture-seg-v1")).manifestPath, registryPath);
    const activeManifestPath = (await createManifest(modelDir, "nail-texture-seg-v2", 2048)).manifestPath;
    await registerRelease(activeManifestPath, registryPath);
    const registry = JSON.parse(await readFile(registryPath, "utf8")) as {
      releases: Array<{ version: string; manifestSnapshotPath: string }>;
    };
    const snapshotPath = registry.releases.find((release) => release.version === "nail-texture-seg-v1")?.manifestSnapshotPath;
    assert.ok(snapshotPath);
    const snapshot = JSON.parse(await readFile(snapshotPath, "utf8"));
    await writeFile(snapshotPath, JSON.stringify({ ...snapshot, backendPreferences: ["cuda"] }, null, 2), "utf8");

    await assert.rejects(
      runAudit(registryPath, activeManifestPath),
      (error: Error & { stdout?: string }) => {
        const summary = JSON.parse(error.stdout ?? "{}") as { ok: boolean; errors: string[] };
        assert.equal(summary.ok, false);
        assert.ok(summary.errors.some((item) => item.includes("snapshot runtime contract is invalid")));
        return true;
      },
    );
  });

  await t.test("active optional runtime field drift", async () => {
    const root = await mkdtemp(path.join(os.tmpdir(), "nail-release-rollback-active-contract-"));
    const modelDir = path.join(root, "public", "models", "nail-texture-seg");
    await mkdir(modelDir, { recursive: true });
    const registryPath = path.join(modelDir, "release-registry.json");
    await registerRelease((await createManifest(modelDir, "nail-texture-seg-v1")).manifestPath, registryPath);
    const activeManifestPath = (await createManifest(modelDir, "nail-texture-seg-v2", 2048)).manifestPath;
    await registerRelease(activeManifestPath, registryPath);
    const activeManifest = JSON.parse(await readFile(activeManifestPath, "utf8"));
    await writeFile(activeManifestPath, JSON.stringify({ ...activeManifest, scoreThreshold: 0.4 }, null, 2), "utf8");

    await assert.rejects(
      runAudit(registryPath, activeManifestPath),
      (error: Error & { stdout?: string }) => {
        const summary = JSON.parse(error.stdout ?? "{}") as { ok: boolean; errors: string[] };
        assert.equal(summary.ok, false);
        assert.ok(summary.errors.some((item) => item.includes("does not exactly match")));
        return true;
      },
    );
  });
});
