import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { link, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import {
  INSTANCE_REVIEW_HEADER,
  REQUIRED_SCENARIO_DIMENSIONS,
  SCENARIO_REGRESSION_HEADER,
  verifyApprovedReleaseProductQualityReport,
} from "../scripts/lib/nail-texture-release-product-quality.ts";

const SCRIPT = "scripts/build-nail-texture-release-product-quality.ts";

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.entries(value as Record<string, unknown>).sort(([left], [right]) => left < right ? -1 : left > right ? 1 : 0).map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function hash(value: unknown): string {
  return createHash("sha256").update(canonical(value), "utf8").digest("hex");
}

function run(args: string[]) {
  return spawnSync("node", ["--no-warnings", "--experimental-strip-types", SCRIPT, ...args], { encoding: "utf8" });
}

interface Fixture {
  root: string;
  snapshot: string;
  instances: string;
  scenarios: string;
  output: string;
  instanceRows: string[];
  scenarioRows: string[];
}

async function fixture(imageCount = 100): Promise<Fixture> {
  const root = await mkdtemp(path.join(tmpdir(), "release-product-quality-"));
  const snapshot = path.join(root, "snapshot.json");
  const instances = path.join(root, "instances.csv");
  const scenarios = path.join(root, "scenarios.csv");
  const output = path.join(root, "report.json");
  const items = Array.from({ length: imageCount }, (_, index) => ({
    fileName: `sample-${String(index + 1).padStart(3, "0")}.jpg`,
    sourceGroup: `source-${String(index + 1).padStart(3, "0")}`,
    imageSha256: createHash("sha256").update(`image-${index + 1}`).digest("hex"),
    maskCount: 1,
    trainingUse: "prohibited",
  }));
  await writeFile(snapshot, JSON.stringify({
    schemaVersion: "frozen-reviewed-release-test-candidate/v1",
    decision: "frozen_reviewed_candidate_not_release_ready",
    trainingUse: "prohibited",
    itemsSha256: hash(items),
    counts: { images: imageCount, masks: imageCount },
    representativeReleaseGate: { ok: imageCount >= 100, actual: imageCount, required: 100, shortfall: Math.max(0, 100 - imageCount) },
    items,
  }, null, 2), "utf8");
  const instanceRows = [
    [...INSTANCE_REVIEW_HEADER].join(","),
    ...items.map((item) => `${item.fileName},${item.sourceGroup},${item.imageSha256},1,directly_usable,false,false,100,2,100,5`),
  ];
  const scenarioRows = [
    [...SCENARIO_REGRESSION_HEADER].join(","),
    ...REQUIRED_SCENARIO_DIMENSIONS.map((dimension) => `${dimension},${dimension}-coverage,10,0.90,0.89,0.90,0.88`),
  ];
  await writeFile(instances, `${instanceRows.join("\n")}\n`, "utf8");
  await writeFile(scenarios, `${scenarioRows.join("\n")}\n`, "utf8");
  return { root, snapshot, instances, scenarios, output, instanceRows, scenarioRows };
}

function build(item: Fixture, output = item.output) {
  return run([
    "--snapshot", item.snapshot,
    "--instances-csv", item.instances,
    "--scenarios-csv", item.scenarios,
    "--reviewer", "product-owner",
    "--output", output,
  ]);
}

test("builds and deeply verifies passing raw product-quality evidence", async () => {
  const item = await fixture();
  const result = build(item);
  assert.equal(result.status, 0, result.stderr);
  const report = JSON.parse(await readFile(item.output, "utf8"));
  assert.equal(report.ok, true);
  assert.equal(report.trainingUse, "prohibited");
  assert.equal(report.sampleImages, 100);
  assert.equal(report.sampleInstances, 100);
  assert.equal(report.directlyUsableRate, 1);
  assert.equal(report.contaminationInstanceRate, 0);
  assert.equal(report.roughRectangleRate, 0);
  assert.equal(report.pixelLeakageRate, 0.02);
  assert.equal(report.missingRate, 0.05);
  assert.equal(report.scenarioGroups.length, 8);
  assert.match(report.snapshot.sha256, /^[a-f0-9]{64}$/);
  assert.match(report.rawEvidence.instances.sha256, /^[a-f0-9]{64}$/);
  const verification = await verifyApprovedReleaseProductQualityReport(item.output, item.snapshot);
  assert.equal(verification.ok, true, verification.errors.join("\n"));
});

test("rejects missing and duplicate snapshot instances", async (t) => {
  await t.test("missing instance", async () => {
    const item = await fixture();
    await writeFile(item.instances, `${item.instanceRows.slice(0, -1).join("\n")}\n`, "utf8");
    assert.equal(build(item).status, 1);
    const report = JSON.parse(await readFile(item.output, "utf8"));
    assert.match(report.errors.join("\n"), /missing sample-100\.jpg instanceIndex 1/);
  });
  await t.test("duplicate instance", async () => {
    const item = await fixture();
    item.instanceRows.push(item.instanceRows[1]!);
    await writeFile(item.instances, `${item.instanceRows.join("\n")}\n`, "utf8");
    assert.equal(build(item).status, 1);
    const report = JSON.parse(await readFile(item.output, "utf8"));
    assert.match(report.errors.join("\n"), /duplicate fileName and instanceIndex/);
  });
});

test("rejects instance identity drift from the frozen snapshot", async () => {
  const item = await fixture();
  item.instanceRows[1] = item.instanceRows[1]!.replace("source-001", "source-drift");
  await writeFile(item.instances, `${item.instanceRows.join("\n")}\n`, "utf8");
  assert.equal(build(item).status, 1);
  const report = JSON.parse(await readFile(item.output, "utf8"));
  assert.match(report.errors.join("\n"), /sourceGroup does not match snapshot/);
});

test("rejects pixel numerators greater than their denominators", async () => {
  const item = await fixture();
  const cells = item.instanceRows[1]!.split(",");
  item.instanceRows[1] = `${cells[0]},${cells[1]},${cells[2]},1,directly_usable,false,false,100,101,100,101`;
  await writeFile(item.instances, `${item.instanceRows.join("\n")}\n`, "utf8");
  assert.equal(build(item).status, 1);
  const report = JSON.parse(await readFile(item.output, "utf8"));
  assert.match(report.errors.join("\n"), /outsideGtPixels must not exceed predictedPixels/);
  assert.match(report.errors.join("\n"), /missedGtPixels must not exceed gtPixels/);
});

test("rejects a recomputed fixed-threshold failure", async () => {
  const item = await fixture();
  for (let index = 1; index <= 16; index += 1) {
    item.instanceRows[index] = item.instanceRows[index]!.replace("directly_usable", "needs_fix");
  }
  await writeFile(item.instances, `${item.instanceRows.join("\n")}\n`, "utf8");
  assert.equal(build(item).status, 1);
  const report = JSON.parse(await readFile(item.output, "utf8"));
  assert.equal(report.directlyUsableRate, 0.84);
  assert.match(report.errors.join("\n"), /directly usable rate must be at least 0\.85/);
});

test("rejects forged canonical items hash", async () => {
  const item = await fixture();
  const snapshot = JSON.parse(await readFile(item.snapshot, "utf8"));
  snapshot.itemsSha256 = "f".repeat(64);
  await writeFile(item.snapshot, JSON.stringify(snapshot), "utf8");
  assert.equal(build(item).status, 1);
  const report = JSON.parse(await readFile(item.output, "utf8"));
  assert.match(report.errors.join("\n"), /itemsSha256 does not match canonical items/);
});

test("rejects duplicate image SHA even when itemsSha256 is recomputed", async () => {
  const item = await fixture();
  const snapshot = JSON.parse(await readFile(item.snapshot, "utf8"));
  snapshot.items[1].imageSha256 = snapshot.items[0].imageSha256;
  snapshot.itemsSha256 = hash(snapshot.items);
  await writeFile(item.snapshot, JSON.stringify(snapshot), "utf8");
  const secondRow = item.instanceRows[2]!.split(",");
  secondRow[2] = snapshot.items[0].imageSha256;
  item.instanceRows[2] = secondRow.join(",");
  await writeFile(item.instances, `${item.instanceRows.join("\n")}\n`, "utf8");
  assert.equal(build(item).status, 1);
  const report = JSON.parse(await readFile(item.output, "utf8"));
  assert.match(report.errors.join("\n"), /duplicate imageSha256/);
});

test("keeps a 67-image frozen snapshot on HOLD even when aggregates pass", async () => {
  const item = await fixture(67);
  assert.equal(build(item).status, 1);
  const report = JSON.parse(await readFile(item.output, "utf8"));
  assert.equal(report.sampleImages, 67);
  assert.match(report.errors.join("\n"), /below representative minimum 100/);
  assert.match(report.errors.join("\n"), /representativeReleaseGate/);
});

test("rejects a scenario sample count above the frozen image count", async () => {
  const item = await fixture();
  item.scenarioRows[1] = item.scenarioRows[1]!.replace(",10,", ",101,");
  await writeFile(item.scenarios, `${item.scenarioRows.join("\n")}\n`, "utf8");
  assert.equal(build(item).status, 1);
  const report = JSON.parse(await readFile(item.output, "utf8"));
  assert.match(report.errors.join("\n"), /sampleCount exceeds snapshot image count/);
});

test("rejects scenario evidence missing any required dimension", async () => {
  const item = await fixture();
  item.scenarioRows = item.scenarioRows.filter((row) => !row.startsWith("device-backend,"));
  await writeFile(item.scenarios, `${item.scenarioRows.join("\n")}\n`, "utf8");
  assert.equal(build(item).status, 1);
  const report = JSON.parse(await readFile(item.output, "utf8"));
  assert.match(report.errors.join("\n"), /missing required dimension device-backend/);
});

test("deep verification rejects instance CSV and snapshot drift after report creation", async (t) => {
  await t.test("CSV drift", async () => {
    const item = await fixture();
    assert.equal(build(item).status, 0);
    item.instanceRows[1] = item.instanceRows[1]!.replace(",100,2,100,5", ",100,3,100,5");
    await writeFile(item.instances, `${item.instanceRows.join("\n")}\n`, "utf8");
    const verification = await verifyApprovedReleaseProductQualityReport(item.output, item.snapshot);
    assert.equal(verification.ok, false);
    assert.ok(verification.errors.some((error) => /rawEvidence|pixelLeakageRate/.test(error)));
  });
  await t.test("snapshot drift", async () => {
    const item = await fixture();
    assert.equal(build(item).status, 0);
    const snapshot = JSON.parse(await readFile(item.snapshot, "utf8"));
    snapshot.snapshotId = "drifted-after-report";
    await writeFile(item.snapshot, JSON.stringify(snapshot), "utf8");
    const verification = await verifyApprovedReleaseProductQualityReport(item.output, item.snapshot);
    assert.equal(verification.ok, false);
    assert.ok(verification.errors.some((error) => /snapshot/.test(error)));
  });
});

test("deep verification rejects a handwritten aggregate PASS without raw evidence", async () => {
  const item = await fixture();
  await writeFile(item.output, JSON.stringify({
    version: "nail-texture-release-product-quality/v1",
    ok: true,
    decision: "pass",
    reviewedByUser: true,
    reviewer: "product-owner",
    trainingUse: "prohibited",
    directlyUsableRate: 1,
    contaminationInstanceRate: 0,
    roughRectangleRate: 0,
    pixelLeakageRate: 0,
    missingRate: 0,
    frozenMaximumMissingRate: 0.1,
    minimumAllowedDelta: -0.02,
    errors: [],
  }), "utf8");
  const verification = await verifyApprovedReleaseProductQualityReport(item.output, item.snapshot);
  assert.equal(verification.ok, false);
  assert.match(verification.errors.join("\n"), /missing snapshot\.path|missing rawEvidence/);
});

test("CLI protects every input evidence file from output overwrite", async () => {
  const item = await fixture();
  for (const evidencePath of [item.snapshot, item.instances, item.scenarios]) {
    const before = await readFile(evidencePath);
    const result = build(item, evidencePath);
    assert.equal(result.status, 1);
    assert.match(result.stderr, /must not overwrite an input evidence file/);
    assert.deepEqual(await readFile(evidencePath), before);
  }

  const hardLinkAlias = path.join(item.root, "scenario-hard-link-output.json");
  await link(item.scenarios, hardLinkAlias);
  const before = await readFile(item.scenarios);
  const aliasResult = build(item, hardLinkAlias);
  assert.equal(aliasResult.status, 1);
  assert.match(aliasResult.stderr, /must not overwrite an input evidence file alias/);
  assert.deepEqual(await readFile(item.scenarios), before);
});
