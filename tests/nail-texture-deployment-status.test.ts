import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtemp, writeFile, readFile, access, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

test("undeployed assets cannot pass audit, register, or replace the active manifest", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "undeployed-model-"));
  const manifestPath = path.join(root, "manifest.json"), registryPath = path.join(root, "registry.json");
  const model = Buffer.alloc(300 * 1024, 1);
  const manifest = { version: "planned", deploymentStatus: "not-deployed", inputSize: 640, task: "segment",
    backendPreferences: ["wasm"], modelFile: "fixture.onnx", labels: ["nail_texture"] };
  const run = (script: string, args: string[]) => spawnSync(process.execPath,
    ["--no-warnings", "--experimental-strip-types", `scripts/${script}.ts`, ...args], { encoding: "utf8" });
  try {
    await writeFile(manifestPath, JSON.stringify(manifest));
    await writeFile(path.join(root, "fixture.onnx"), model);
    const audit = run("verify-model-artifact", [manifestPath]);
    assert.equal(audit.error, undefined);
    assert.equal(audit.status, 1, audit.stderr);
    assert.match(audit.stdout, /deploymentStatus/);
    const register = run("register-model-release", ["--manifest", manifestPath, "--registry", registryPath]);
    assert.equal(register.error, undefined);
    assert.equal(register.status, 1);
    assert.match(register.stderr, /model_not_deployed/);
    await assert.rejects(access(registryPath));
    await assert.rejects(access(path.join(root, "manifest.planned.json")));
    const destination = path.join(root, "active.json");
    await writeFile(destination, "original active manifest");
    await writeFile(registryPath, JSON.stringify({ currentVersion: null, releases: [{
      version: "planned", manifestSnapshotPath: manifestPath, modelPath: path.join(root, "fixture.onnx"),
      modelSizeBytes: model.length, sha256: createHash("sha256").update(model).digest("hex"),
    }] }));
    const switchResult = run("switch-model-release", ["--version", "planned", "--registry", registryPath, "--manifest", destination]);
    assert.equal(switchResult.error, undefined);
    assert.equal(switchResult.status, 1);
    assert.match(switchResult.stderr, /model_not_deployed/);
    assert.equal(await readFile(destination, "utf8"), "original active manifest");
    assert.equal(JSON.parse(await readFile(registryPath, "utf8")).currentVersion, null);
  } finally { await rm(root, { recursive: true, force: true }); }
});
