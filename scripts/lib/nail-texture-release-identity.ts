import { createHash } from "node:crypto";

const HEX = /^[a-f0-9]{64}$/;

export interface NailTextureReleaseIdentityCore {
  candidateId: string;
  runtimeSelectionLockSha256: string;
  modelFiles: Array<{ role: string; sha256: string }>;
  inputSize: number;
  scoreThreshold: number;
  combinationRulesSha256: string;
  preprocessSha256: string;
  postprocessSha256: string;
}

export interface NailTextureReleaseIdentity {
  core: NailTextureReleaseIdentityCore;
  coreSha256: string;
  manifestSha256: string;
}

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => left.localeCompare(right, "en-US"))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

export function releaseIdentityCoreSha256(core: NailTextureReleaseIdentityCore): string {
  return createHash("sha256").update(canonical(core), "utf8").digest("hex");
}

function exactKeys(value: Record<string, unknown>, expected: string[], label: string, errors: string[]) {
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  if (actual.length !== wanted.length || actual.some((key, index) => key !== wanted[index])) {
    errors.push(`${label} must contain exactly: ${expected.join(", ")}`);
  }
}

export function validateReleaseIdentity(value: unknown) {
  const errors: string[] = [];
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return { ok: false, errors: ["releaseIdentity must be an object"], identity: null };
  }
  const identity = value as unknown as NailTextureReleaseIdentity;
  exactKeys(value as Record<string, unknown>, ["core", "coreSha256", "manifestSha256"], "releaseIdentity", errors);
  const core = identity.core;
  if (!core || typeof core !== "object" || Array.isArray(core)) {
    errors.push("releaseIdentity.core must be an object");
  } else {
    exactKeys(core as unknown as Record<string, unknown>, [
      "candidateId", "runtimeSelectionLockSha256", "modelFiles", "inputSize", "scoreThreshold",
      "combinationRulesSha256", "preprocessSha256", "postprocessSha256",
    ], "releaseIdentity.core", errors);
    if (!/^[a-z0-9][a-z0-9._-]{2,79}$/i.test(core.candidateId ?? "")) errors.push("candidateId is invalid");
    for (const [name, hash] of Object.entries({
      runtimeSelectionLockSha256: core.runtimeSelectionLockSha256,
      combinationRulesSha256: core.combinationRulesSha256,
      preprocessSha256: core.preprocessSha256,
      postprocessSha256: core.postprocessSha256,
    })) if (!HEX.test(hash ?? "")) errors.push(`${name} must be lowercase SHA-256`);
    if (core.inputSize !== 512) errors.push("inputSize must be 512");
    if (!Number.isFinite(core.scoreThreshold) || core.scoreThreshold <= 0 || core.scoreThreshold >= 1) {
      errors.push("scoreThreshold must be finite and between 0 and 1");
    }
    if (!Array.isArray(core.modelFiles) || core.modelFiles.length === 0) errors.push("modelFiles must not be empty");
    else {
      const roles = new Set<string>();
      for (const [index, model] of core.modelFiles.entries()) {
        if (!model || typeof model !== "object" || Array.isArray(model)) {
          errors.push(`modelFiles[${index}] is invalid`); continue;
        }
        exactKeys(model as unknown as Record<string, unknown>, ["role", "sha256"], `modelFiles[${index}]`, errors);
        if (!/^[a-z][a-z0-9._-]{1,39}$/i.test(model.role ?? "")) errors.push(`modelFiles[${index}].role is invalid`);
        if (roles.has(model.role)) errors.push(`duplicate model role: ${model.role}`);
        roles.add(model.role);
        if (!HEX.test(model.sha256 ?? "")) errors.push(`modelFiles[${index}].sha256 must be lowercase SHA-256`);
      }
    }
  }
  if (!HEX.test(identity.coreSha256 ?? "")) errors.push("coreSha256 must be lowercase SHA-256");
  if (!HEX.test(identity.manifestSha256 ?? "")) errors.push("manifestSha256 must be lowercase SHA-256");
  if (core && releaseIdentityCoreSha256(core) !== identity.coreSha256) errors.push("releaseIdentity core hash mismatch");
  return { ok: errors.length === 0, errors, identity: errors.length === 0 ? identity : null };
}

export function compareReleaseIdentity(expected: NailTextureReleaseIdentity, actual: unknown, label: string): string[] {
  const checked = validateReleaseIdentity(actual);
  if (!checked.ok || !checked.identity) return checked.errors.map((error) => `${label}: ${error}`);
  return canonical(checked.identity) === canonical(expected) ? [] : [`${label}: releaseIdentity mismatch`];
}
