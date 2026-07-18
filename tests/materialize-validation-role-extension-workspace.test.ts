import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/materialize-validation-role-extension-workspace.py");
const sha = (value: Buffer | string) => createHash("sha256").update(value).digest("hex");

function fixture() {
  const root = mkdtempSync(path.join(tmpdir(), "val-extension-materialize-"));
  const source = path.join(root, "source");
  mkdirSync(source);
  const identities = [
    { fileName: "a.jpg", bytes: Buffer.from("a"), sourceGroup: "group-a" },
    { fileName: "b.jpg", bytes: Buffer.from("b"), sourceGroup: "group-b" },
    { fileName: "c.jpg", bytes: Buffer.from("c"), sourceGroup: "group-b" },
  ];
  for (const item of identities) writeFileSync(path.join(source, item.fileName), item.bytes);
  const items = identities.map((item) => ({
    fileName: item.fileName,
    sourcePath: path.join(source, item.fileName),
    workspacePath: path.join(source, item.fileName),
    sha256: sha(item.bytes),
    sourceGroup: item.sourceGroup,
    assignedRole: "val",
    originalAssignedRole: "train",
    expectedFullyVisibleNails: 5,
    materializationMethod: "authorized-source-reference",
    trainingUse: "prohibited",
    annotationTruthStatus: "not-started",
  }));
  const role = {
    ok: true,
    decision: "annotation_workspace_ready_candidate_only",
    extensionDecision: "validation_role_extension_ready_candidate_only",
    policy: {
      selectionMode: "val",
      assignedRole: "val",
      sourceGroupsRemainAtomicAcrossRoleExtension: true,
      approvedTrainTruthGroupsExcluded: true,
      independentReleaseTestGroupsExcluded: true,
    },
    counts: { addedImages: 3 },
    extension: {
      sourceGroupReassignments: [
        {
          sourceGroup: "group-a",
          allPlanItemsCovered: true,
          approvedTrainTruthMatches: [],
          firstAnnotationBatchMatches: [],
          reassignment: "whole-plan-source-group-to-val",
        },
        {
          sourceGroup: "group-b",
          allPlanItemsCovered: true,
          approvedTrainTruthMatches: [],
          firstAnnotationBatchMatches: [],
          reassignment: "whole-plan-source-group-to-val",
        },
      ],
      replacements: identities.map(({ fileName }) => ({ fileName })),
    },
    items,
  };
  const rolePath = path.join(root, "role.json");
  writeFileSync(rolePath, `${JSON.stringify(role, null, 2)}\n`, "utf8");
  return { root, rolePath, role };
}

test("materializes reviewed val additions while keeping source groups atomic", () => {
  const { root, rolePath } = fixture();
  const output = path.join(root, "workspace");
  execFileSync("python", [
    script,
    "--role-extension-manifest", rolePath,
    "--output-dir", output,
    "--target-shard-size", "2",
  ]);
  const manifest = JSON.parse(readFileSync(path.join(output, "annotation-workspace-manifest.json"), "utf8"));
  assert.equal(manifest.ok, true);
  assert.equal(manifest.policy.extensionOnly, true);
  assert.deepEqual(manifest.counts, {
    images: 3,
    sourceGroups: 2,
    shards: 2,
    expectedFullyVisibleNails: 15,
    materializationMethods: { hardlink: 3 },
  });
  assert.equal(manifest.items.filter((item: { sourceGroup: string }) => item.sourceGroup === "group-b").length, 2);
  assert.equal(manifest.items.every((item: { trainingUse: string }) => item.trainingUse === "prohibited"), true);
});

test("rejects a reassignment that overlaps the first train annotation batch", () => {
  const { root, rolePath, role } = fixture();
  role.extension.sourceGroupReassignments[0].firstAnnotationBatchMatches = ["a.jpg"];
  writeFileSync(rolePath, `${JSON.stringify(role, null, 2)}\n`, "utf8");
  const result = spawnSync("python", [
    script,
    "--role-extension-manifest", rolePath,
    "--output-dir", path.join(root, "workspace"),
  ], { encoding: "utf8" });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /unsafe source-group reassignment/);
});

test("rejects source image hash drift", () => {
  const { root, rolePath, role } = fixture();
  writeFileSync(role.items[0].sourcePath, "changed", "utf8");
  const result = spawnSync("python", [
    script,
    "--role-extension-manifest", rolePath,
    "--output-dir", path.join(root, "workspace"),
  ], { encoding: "utf8" });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /missing or changed/);
});
