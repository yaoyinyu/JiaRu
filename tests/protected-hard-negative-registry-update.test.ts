import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  appendFileSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  symlinkSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { writePatternTestPng } from "./helpers/hard-negative-evidence.ts";

const updater = path.resolve(
  "model/training/update-protected-hard-negative-registry.py",
);
const recorder = path.resolve(
  "model/training/record-training-hard-negative-authorization.py",
);
const python = process.env.PYTHON ?? "python";

type RegistryRole = "training" | "holdout";
type RegistryEntry = { path: string; sha256: string; role: RegistryRole };

const canonical = (value: unknown): string => {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
};

const canonicalSha = (value: unknown) =>
  createHash("sha256").update(canonical(value)).digest("hex");

const shaFile = (file: string) =>
  createHash("sha256").update(readFileSync(file)).digest("hex");

function writeJson(file: string, value: unknown) {
  mkdirSync(path.dirname(file), { recursive: true });
  writeFileSync(file, `${JSON.stringify(value, null, 2)}\n`);
}

function makeManifest(
  root: string,
  label: string,
  role: RegistryRole,
  seed: number,
  imagePathOverride?: string,
) {
  const imagePath =
    imagePathOverride ?? path.join(root, "images", `${label}.png`);
  if (!imagePathOverride) writePatternTestPng(imagePath, seed, 320, 320);
  const fileName = `${label}.png`;
  const training = role === "training";
  const items = [
    {
      fileName,
      sourceFileName: fileName,
      sourceGroup: `ai-hard-negative-${training ? "training" : "independent"}-20260726:${label}`,
      imageSha256: shaFile(imagePath),
      imagePath,
      width: 320,
      height: 320,
      imageFormat: "PNG",
      role: training ? "hard-negative" : "independent-holdout",
      originalResolutionVisualReview: true,
      trainingUse: training ? "permitted" : "prohibited",
    },
  ];
  const manifestPath = path.join(root, "manifests", `${label}.json`);
  writeJson(manifestPath, {
    schemaVersion: 2,
    ok: true,
    status: "PASS",
    decision: training
      ? "approved_hard_negative_manifest"
      : "approved_independent_hard_negative_holdout",
    trainingUse: training ? "permitted" : "prohibited",
    itemsSha256: canonicalSha(items),
    items,
  });
  return manifestPath;
}

function writeRegistry(file: string, entries: RegistryEntry[]) {
  writeJson(file, {
    schemaVersion: 1,
    ok: true,
    decision: "protected_hard_negative_registry",
    summary: {
      manifestCount: entries.length,
      trainingManifestCount: entries.filter((entry) => entry.role === "training")
        .length,
      holdoutManifestCount: entries.filter((entry) => entry.role === "holdout")
        .length,
    },
    entriesSha256: canonicalSha(entries),
    entries,
  });
}

function makeFixture() {
  const root = mkdtempSync(path.join(tmpdir(), "protected-registry-update-"));
  const training = makeManifest(root, "base-training", "training", 4101);
  const holdout = makeManifest(root, "base-holdout", "holdout", 4102);
  const baseRegistry = path.join(root, "base-registry.json");
  const baseEntries: RegistryEntry[] = [
    { path: path.resolve(training), sha256: shaFile(training), role: "training" },
    { path: path.resolve(holdout), sha256: shaFile(holdout), role: "holdout" },
  ];
  writeRegistry(baseRegistry, baseEntries);
  return { root, baseRegistry, baseEntries };
}

function runUpdate(
  fixture: ReturnType<typeof makeFixture>,
  output: string,
  manifests: Array<[RegistryRole | string, string]>,
) {
  return spawnSync(
    python,
    [
      updater,
      "--base-registry",
      fixture.baseRegistry,
      "--output",
      output,
      ...manifests.flatMap(([role, manifest]) => [
        "--manifest",
        role,
        manifest,
      ]),
    ],
    { encoding: "utf8" },
  );
}

function runVerify(registry: string) {
  return spawnSync(python, [updater, "--verify-registry", registry], {
    encoding: "utf8",
  });
}

test("monotonically appends deeply verified manifests and remains recorder-compatible", () => {
  const fixture = makeFixture();
  const training = makeManifest(fixture.root, "new-training-z", "training", 4201);
  const holdout = makeManifest(fixture.root, "new-holdout-a", "holdout", 4202);
  const output = path.join(fixture.root, "registry-v2.json");
  const result = runUpdate(fixture, output, [
    ["training", training],
    ["holdout", holdout],
  ]);
  assert.equal(result.status, 0, result.stderr);
  const response = JSON.parse(result.stdout);
  assert.equal(response.appendedManifestCount, 2);
  assert.equal(response.manifestCount, 4);
  assert.equal(response.trainingManifestCount, 2);
  assert.equal(response.holdoutManifestCount, 2);
  assert.equal(response.lineageDepth, 1);

  const registry = JSON.parse(readFileSync(output, "utf8"));
  assert.deepEqual(registry.entries.slice(0, 2), fixture.baseEntries);
  assert.deepEqual(
    registry.entries.slice(2).map((entry: RegistryEntry) => entry.path),
    [holdout, training].map((item) => path.resolve(item)).sort((left, right) =>
      left.toLocaleLowerCase().localeCompare(right.toLocaleLowerCase()),
    ),
  );
  assert.equal(registry.entriesSha256, canonicalSha(registry.entries));
  assert.equal(
    registry.monotonicAppend.appendedEntriesSha256,
    canonicalSha(registry.entries.slice(2)),
  );

  const ownVerify = runVerify(output);
  assert.equal(ownVerify.status, 0, ownVerify.stderr);
  const recorderVerify = spawnSync(
    python,
    [recorder, "--verify-protected-registry", output],
    { encoding: "utf8" },
  );
  assert.equal(recorderVerify.status, 0, recorderVerify.stderr);

  const secondOutput = path.join(fixture.root, "registry-v2-repeat.json");
  const repeated = runUpdate(fixture, secondOutput, [
    ["training", training],
    ["holdout", holdout],
  ]);
  assert.equal(repeated.status, 0, repeated.stderr);
  assert.deepEqual(readFileSync(secondOutput), readFileSync(output));
});

test("verification rejects deletion of an old registry entry", () => {
  const fixture = makeFixture();
  const added = makeManifest(fixture.root, "added-training", "training", 4301);
  const output = path.join(fixture.root, "registry-v2.json");
  assert.equal(runUpdate(fixture, output, [["training", added]]).status, 0);
  const registry = JSON.parse(readFileSync(output, "utf8"));
  registry.entries.splice(0, 1);
  registry.summary = {
    manifestCount: registry.entries.length,
    trainingManifestCount: registry.entries.filter(
      (entry: RegistryEntry) => entry.role === "training",
    ).length,
    holdoutManifestCount: registry.entries.filter(
      (entry: RegistryEntry) => entry.role === "holdout",
    ).length,
  };
  registry.entriesSha256 = canonicalSha(registry.entries);
  writeJson(output, registry);
  const result = runVerify(output);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /must append at least one|old protected registry entries/i);
});

test("verification rejects reordering or replacing old entries", () => {
  const fixture = makeFixture();
  const added = makeManifest(fixture.root, "added-training", "training", 4401);
  const output = path.join(fixture.root, "registry-v2.json");
  assert.equal(runUpdate(fixture, output, [["training", added]]).status, 0);
  const registry = JSON.parse(readFileSync(output, "utf8"));
  [registry.entries[0], registry.entries[1]] = [
    registry.entries[1],
    registry.entries[0],
  ];
  registry.entriesSha256 = canonicalSha(registry.entries);
  writeJson(output, registry);
  const result = runVerify(output);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /deleted, replaced, reordered/i);
});

test("rejects an explicit role inconsistent with manifest decision and trainingUse", () => {
  const fixture = makeFixture();
  const training = makeManifest(fixture.root, "wrong-role", "training", 4501);
  const result = runUpdate(
    fixture,
    path.join(fixture.root, "wrong-role-registry.json"),
    [["holdout", training]],
  );
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /role differs from manifest decision/i);
});

test("verification rejects manifest SHA drift after publication", () => {
  const fixture = makeFixture();
  const added = makeManifest(fixture.root, "drifting-training", "training", 4601);
  const output = path.join(fixture.root, "registry-v2.json");
  const created = runUpdate(fixture, output, [["training", added]]);
  assert.equal(created.status, 0, created.stderr);
  appendFileSync(added, " \n");
  const result = runVerify(output);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /manifest SHA-256 drift/i);
});

test("rejects duplicate paths, aliases, and conflicting duplicate identities", () => {
  const fixture = makeFixture();
  const added = makeManifest(fixture.root, "duplicate-training", "training", 4701);
  const alias = path.join(path.dirname(added), ".", path.basename(added));
  const duplicatePath = runUpdate(
    fixture,
    path.join(fixture.root, "duplicate-path-registry.json"),
    [
      ["training", added],
      ["training", alias],
    ],
  );
  assert.notEqual(duplicatePath.status, 0);
  assert.match(duplicatePath.stderr, /duplicate protected registry manifest path/i);

  const sharedImage = path.join(fixture.root, "images", "shared.png");
  writePatternTestPng(sharedImage, 4702, 320, 320);
  const left = makeManifest(
    fixture.root,
    "conflict-left",
    "training",
    0,
    sharedImage,
  );
  const right = makeManifest(
    fixture.root,
    "conflict-right",
    "training",
    0,
    sharedImage,
  );
  const conflict = runUpdate(
    fixture,
    path.join(fixture.root, "conflict-registry.json"),
    [
      ["training", left],
      ["training", right],
    ],
  );
  assert.notEqual(conflict.status, 0);
  assert.match(conflict.stderr, /duplicate evidence conflicts|conflicting protected/i);
});

test("refuses output overwrite without changing existing bytes", () => {
  const fixture = makeFixture();
  const added = makeManifest(fixture.root, "overwrite-training", "training", 4801);
  const output = path.join(fixture.root, "already-exists.json");
  const sentinel = Buffer.from("do-not-overwrite\n");
  writeFileSync(output, sentinel);
  const result = runUpdate(fixture, output, [["training", added]]);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /refusing to overwrite existing output/i);
  assert.deepEqual(readFileSync(output), sentinel);
});

test("rejects linked manifest paths when the platform permits symlink creation", (t) => {
  const fixture = makeFixture();
  const added = makeManifest(fixture.root, "linked-training", "training", 4901);
  const linked = path.join(fixture.root, "linked-manifest.json");
  try {
    symlinkSync(added, linked, "file");
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    if (code === "EPERM" || code === "EACCES" || code === "ENOTSUP") {
      t.skip(`symlink creation unavailable: ${code}`);
      return;
    }
    throw error;
  }
  const result = runUpdate(
    fixture,
    path.join(fixture.root, "linked-registry.json"),
    [["training", linked]],
  );
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /symbolic link, junction, or reparse point/i);
});
