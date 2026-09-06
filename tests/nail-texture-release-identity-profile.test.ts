import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { IDENTITY_BOUND_REPORTS, verifyReleaseIdentityProfile } from "../scripts/lib/nail-texture-release-identity-profile.ts";
import { releaseIdentityCoreSha256 } from "../scripts/lib/nail-texture-release-identity.ts";

const sha = (bytes: Buffer | string) => createHash("sha256").update(bytes).digest("hex");
async function buildProfile() {
  const root = await mkdtemp(path.join(tmpdir(), "release-identity-"));
  const lock = path.join(root, "lock.json"); await writeFile(lock, '{"locked":true}\n');
  const model = path.join(root, "model.onnx"); await writeFile(model, "model-v1");
  const core = { candidateId: "candidate-58", runtimeSelectionLockSha256: sha(await import("node:fs/promises").then(m => m.readFile(lock))),
    modelFiles: [{ role: "segment", sha256: sha("model-v1") }], inputSize: 512, scoreThreshold: 0.42,
    combinationRulesSha256: sha("single-stage"), preprocessSha256: sha("letterbox-v1"), postprocessSha256: sha("dedupe-v1") };
  const coreSha256 = releaseIdentityCoreSha256(core);
  const manifest = path.join(root, "manifest.json");
  await writeFile(manifest, JSON.stringify({ releaseIdentityCoreSha256: coreSha256 }) + "\n");
  const identity = { core, coreSha256, manifestSha256: sha(await import("node:fs/promises").then(m => m.readFile(manifest))) };
  const bind = async (file: string) => ({ path: file, sha256: sha(await import("node:fs/promises").then(m => m.readFile(file))) });
  const reports: Record<string, Awaited<ReturnType<typeof bind>>> = {};
  for (const key of IDENTITY_BOUND_REPORTS) {
    const file = path.join(root, `${key}.json`); await writeFile(file, JSON.stringify({ releaseIdentity: identity }) + "\n");
    reports[key] = await bind(file);
  }
  const profile = { schemaVersion: 1, decision: "approved_nail_texture_release_identity_profile", releaseIdentity: identity,
    artifacts: { runtimeSelectionLock: await bind(lock), models: [{ role: "segment", ...(await bind(model)) }], productionManifest: await bind(manifest) }, reports };
  const profilePath = path.join(root, "profile.json"); await writeFile(profilePath, JSON.stringify(profile, null, 2) + "\n");
  return { root, profilePath, profile, identity };
}

test("完整同一身份profile通过深度文件和报告绑定", async () => {
  const value = await buildProfile(); const result = await verifyReleaseIdentityProfile(value.profilePath);
  assert.equal(result.ok, true, result.errors.join("\n"));
});

test("缺少profile明确表示无批准候选", async () => {
  const result = await verifyReleaseIdentityProfile(path.join(tmpdir(), `missing-${Date.now()}.json`));
  assert.equal(result.status, "no_approved_release_candidate"); assert.equal(result.ok, false);
});

test("跨候选报告、模型字节和manifest漂移均拒绝", async () => {
  const crossed = await buildProfile(); const report = crossed.profile.reports.beta.path;
  await writeFile(report, JSON.stringify({ releaseIdentity: { ...crossed.identity, manifestSha256: "0".repeat(64) } }) + "\n");
  crossed.profile.reports.beta.sha256 = sha(await import("node:fs/promises").then(m => m.readFile(report)));
  await writeFile(crossed.profilePath, JSON.stringify(crossed.profile) + "\n");
  assert.equal((await verifyReleaseIdentityProfile(crossed.profilePath)).ok, false);
  const modelDrift = await buildProfile(); await writeFile(modelDrift.profile.artifacts.models[0].path, "changed");
  assert.equal((await verifyReleaseIdentityProfile(modelDrift.profilePath)).ok, false);
  const manifestDrift = await buildProfile(); await writeFile(manifestDrift.profile.artifacts.productionManifest.path, "{}\n");
  assert.equal((await verifyReleaseIdentityProfile(manifestDrift.profilePath)).ok, false);
});
