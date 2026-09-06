import { createHash } from "node:crypto";
import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import { compareReleaseIdentity, validateReleaseIdentity } from "./nail-texture-release-identity.ts";

export const IDENTITY_BOUND_REPORTS = [
  "calibration", "positiveHoldoutSnapshot", "positiveRecognitionQuality", "hardNegativeAudit",
  "onnxParity", "browser", "desktopPerformance", "desktopMemory", "androidPhone", "androidTablet",
  "iphone", "ipad", "beta", "productQuality", "releaseRegistry", "rollback",
] as const;

type FileBinding = { path: string; sha256: string };
type ModelBinding = FileBinding & { role: string };
const hex = (value: unknown): value is string => typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
const sha = (bytes: Buffer) => createHash("sha256").update(bytes).digest("hex");

function exactKeys(value: Record<string, unknown>, expected: string[], label: string, errors: string[]) {
  const actual = Object.keys(value).sort(); const wanted = [...expected].sort();
  if (actual.length !== wanted.length || actual.some((key, index) => key !== wanted[index]))
    errors.push(`${label} must contain exactly: ${expected.join(", ")}`);
}

async function load(binding: FileBinding, label: string, errors: string[]) {
  if (!binding || typeof binding !== "object" || Array.isArray(binding)) { errors.push(`${label} binding is invalid`); return null; }
  exactKeys(binding as unknown as Record<string, unknown>, ["path", "sha256"], label, errors);
  if (typeof binding.path !== "string" || !path.isAbsolute(binding.path)) { errors.push(`${label}.path must be absolute`); return null; }
  if (!hex(binding.sha256)) { errors.push(`${label}.sha256 must be lowercase SHA-256`); return null; }
  try {
    const info = await stat(binding.path); if (!info.isFile()) throw new Error("not a file");
    const bytes = await readFile(binding.path);
    if (sha(bytes) !== binding.sha256) errors.push(`${label} hash drift`);
    return bytes;
  } catch { errors.push(`${label} cannot be read`); return null; }
}

export async function verifyReleaseIdentityProfile(profilePath: string) {
  const errors: string[] = [];
  let raw: Buffer;
  try { raw = await readFile(profilePath); } catch {
    return { ok: false, status: "no_approved_release_candidate", profilePath, releaseIdentity: null, errors: ["release identity profile is missing"] };
  }
  let profile: any;
  try { profile = JSON.parse(raw.toString("utf8")); } catch {
    return { ok: false, status: "invalid_release_identity_profile", profilePath, releaseIdentity: null, errors: ["release identity profile is invalid JSON"] };
  }
  if (!profile || typeof profile !== "object" || Array.isArray(profile)) errors.push("profile must be an object");
  else exactKeys(profile, ["schemaVersion", "decision", "releaseIdentity", "artifacts", "reports"], "profile", errors);
  if (profile?.schemaVersion !== 1 || profile?.decision !== "approved_nail_texture_release_identity_profile")
    errors.push("profile schemaVersion or decision is invalid");
  const identityCheck = validateReleaseIdentity(profile?.releaseIdentity);
  errors.push(...identityCheck.errors);
  const identity = identityCheck.identity;
  const artifacts = profile?.artifacts;
  if (!artifacts || typeof artifacts !== "object" || Array.isArray(artifacts)) errors.push("artifacts must be an object");
  else exactKeys(artifacts, ["runtimeSelectionLock", "models", "productionManifest"], "artifacts", errors);
  if (identity && artifacts) {
    const lockBytes = await load(artifacts.runtimeSelectionLock, "runtimeSelectionLock", errors);
    if (lockBytes && sha(lockBytes) !== identity.core.runtimeSelectionLockSha256) errors.push("runtime selection lock does not match release identity");
    if (lockBytes && /manifestSha256|releaseIdentityCoreSha256/.test(lockBytes.toString("utf8"))) errors.push("runtime selection lock contains a forbidden manifest identity reference");
    if (!Array.isArray(artifacts.models)) errors.push("artifacts.models must be an array");
    else {
      const expected = new Map(identity.core.modelFiles.map((item) => [item.role, item.sha256]));
      const found = new Map<string, string>();
      for (const [index, model] of (artifacts.models as ModelBinding[]).entries()) {
        if (!model || typeof model !== "object") { errors.push(`models[${index}] binding is invalid`); continue; }
        exactKeys(model as unknown as Record<string, unknown>, ["role", "path", "sha256"], `models[${index}]`, errors);
        const bytes = await load({ path: model.path, sha256: model.sha256 }, `models[${index}]`, errors);
        if (found.has(model.role)) errors.push(`duplicate artifact model role: ${model.role}`);
        found.set(model.role, model.sha256);
        if (bytes && expected.get(model.role) !== sha(bytes)) errors.push(`model artifact identity mismatch: ${model.role}`);
      }
      if (found.size !== expected.size || [...expected].some(([role, hash]) => found.get(role) !== hash)) errors.push("model artifact set does not match release identity");
    }
    const manifestBytes = await load(artifacts.productionManifest, "productionManifest", errors);
    if (manifestBytes) {
      if (sha(manifestBytes) !== identity.manifestSha256) errors.push("production manifest does not match release identity");
      try {
        const manifest = JSON.parse(manifestBytes.toString("utf8"));
        if (manifest.releaseIdentityCoreSha256 !== identity.coreSha256) errors.push("production manifest core identity mismatch");
      } catch { errors.push("production manifest is invalid JSON"); }
    }
  }
  const reports = profile?.reports;
  if (!reports || typeof reports !== "object" || Array.isArray(reports)) errors.push("reports must be an object");
  else {
    exactKeys(reports, [...IDENTITY_BOUND_REPORTS], "reports", errors);
    if (identity) for (const key of IDENTITY_BOUND_REPORTS) {
      const bytes = await load(reports[key], `reports.${key}`, errors);
      if (!bytes) continue;
      try { errors.push(...compareReleaseIdentity(identity, JSON.parse(bytes.toString("utf8")).releaseIdentity, `reports.${key}`)); }
      catch { errors.push(`reports.${key} is invalid JSON`); }
    }
  }
  return { ok: errors.length === 0, status: errors.length === 0 ? "approved_release_identity" : "invalid_release_identity_profile",
    profilePath, profileSha256: sha(raw), releaseIdentity: identity, errors };
}
