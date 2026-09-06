import assert from "node:assert/strict";
import test from "node:test";
import { compareReleaseIdentity, releaseIdentityCoreSha256, validateReleaseIdentity } from "../scripts/lib/nail-texture-release-identity.ts";

const h = (character: string) => character.repeat(64);
function fixture() {
  const core = { candidateId: "candidate-58", runtimeSelectionLockSha256: h("a"),
    modelFiles: [{ role: "segment", sha256: h("b") }], inputSize: 512, scoreThreshold: 0.42,
    combinationRulesSha256: h("c"), preprocessSha256: h("d"), postprocessSha256: h("e") };
  return { core, coreSha256: releaseIdentityCoreSha256(core), manifestSha256: h("f") };
}

test("规范身份可重放并允许字段顺序不同", () => {
  const identity = fixture();
  assert.equal(validateReleaseIdentity(identity).ok, true);
  const reordered = { manifestSha256: identity.manifestSha256, coreSha256: identity.coreSha256, core: identity.core };
  assert.deepEqual(compareReleaseIdentity(identity, reordered, "report"), []);
});

test("候选、权重、输入、阈值、组合和实现漂移全部拒绝", () => {
  for (const mutate of [
    (v: ReturnType<typeof fixture>) => { v.core.candidateId = "candidate-59"; },
    (v: ReturnType<typeof fixture>) => { v.core.modelFiles[0]!.sha256 = h("1"); },
    (v: ReturnType<typeof fixture>) => { v.core.inputSize = 640; },
    (v: ReturnType<typeof fixture>) => { v.core.scoreThreshold = 0.43; },
    (v: ReturnType<typeof fixture>) => { v.core.combinationRulesSha256 = h("2"); },
    (v: ReturnType<typeof fixture>) => { v.core.preprocessSha256 = h("3"); },
    (v: ReturnType<typeof fixture>) => { v.core.postprocessSha256 = h("4"); },
  ]) {
    const value = fixture(); mutate(value);
    assert.equal(validateReleaseIdentity(value).ok, false);
  }
});

test("多模型角色重复、额外字段、非小写哈希和跨报告身份拼接拒绝", () => {
  const duplicate = fixture(); duplicate.core.modelFiles.push({ role: "segment", sha256: h("7") });
  duplicate.coreSha256 = releaseIdentityCoreSha256(duplicate.core);
  assert.equal(validateReleaseIdentity(duplicate).ok, false);
  const extra = { ...fixture(), note: "not allowed" };
  assert.equal(validateReleaseIdentity(extra).ok, false);
  const uppercase = fixture(); uppercase.manifestSha256 = h("A");
  assert.equal(validateReleaseIdentity(uppercase).ok, false);
  const other = fixture(); other.manifestSha256 = h("0");
  assert.match(compareReleaseIdentity(fixture(), other, "beta")[0]!, /mismatch/);
});
