import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import path from "node:path";
import test from "node:test";

const SCRIPT = path.join(process.cwd(), "model", "training", "build-development-cycle-015-generated-annotation-workspace.py");

function evaluate(lines: string[]): Record<string, unknown> {
  const code = [
    "import importlib.util, json, sys",
    `spec=importlib.util.spec_from_file_location('workspace',r'${SCRIPT}')`,
    "m=importlib.util.module_from_spec(spec)",
    "sys.modules['workspace']=m",
    "spec.loader.exec_module(m)",
    ...lines,
  ].join("\n");
  return JSON.parse(execFileSync("python", ["-c", code], { encoding: "utf8" }).trim()) as Record<string, unknown>;
}

test("循环015工作区合同强制隔离复制且不授权训练", () => {
  const result = evaluate([
    "print(json.dumps({'decision':m.WORKSPACE_DECISION,'copyOnly':True,'trainingUse':'prohibited'}))",
  ]);
  assert.equal(result.decision, "development_cycle_015_generated_annotation_workspace_ready_candidate_only");
  assert.equal(result.copyOnly, true);
  assert.equal(result.trainingUse, "prohibited");
});

test("权威真值查重覆盖文件名图片哈希和来源组", () => {
  const result = evaluate([
    "docs=[{'canonicalTruths':[{'fileName':'Known.PNG','imageSha256':'a'*64,'sourceGroup':'g-known'}]}]",
    "ids=m.truth_identities(docs)",
    "print(json.dumps({k:sorted(v) for k,v in ids.items()}))",
  ]);
  assert.deepEqual(result, {
    fileName: ["known.png"],
    imageSha256: ["a".repeat(64)],
    sourceGroup: ["g-known"],
  });
});

test("命中既有规范文件名时在物化前拒绝", () => {
  const result = evaluate([
    "ids={'fileName':{'known.png'},'imageSha256':set(),'sourceGroup':set()}",
    "item={'fileName':'KNOWN.PNG','imageSha256':'b'*64,'sourceGroup':'g-new'}",
    "try:",
    " m.assert_no_truth_duplicates([item],ids); out={'rejected':False}",
    "except ValueError as e:",
    " out={'rejected':True,'message':str(e)}",
    "print(json.dumps(out,ensure_ascii=False))",
  ]);
  assert.equal(result.rejected, true);
  assert.match(String(result.message), /fileName/);
});

test("累计来源只物化尚未完成开发评估真值的增量", () => {
  const result = evaluate([
    "items=[{'fileName':'done.png','imageSha256':'a'*64,'sourceGroup':'g-done'},{'fileName':'new.png','imageSha256':'b'*64,'sourceGroup':'g-new'}]",
    "truth={'ok':True,'decision':m.DEVELOPMENT_TRUTH_DECISION,'inputs':{'truthRole':'development-evaluation'},'policy':{'trainingUse':'prohibited'},'summary':{'uniqueImageCount':1,'conflictingImageCount':0},'canonicalTruths':[{'fileName':'done.png','imageSha256':'a'*64,'sourceGroup':'g-done'}]}",
    "pending,count=m.select_pending_items(items,truth)",
    "print(json.dumps({'files':[x['fileName'] for x in pending],'existingCount':count}))",
  ]);
  assert.deepEqual(result, { files: ["new.png"], existingCount: 1 });
});

test("既有开发评估真值身份冲突时拒绝增量物化", () => {
  const result = evaluate([
    "items=[{'fileName':'done.png','imageSha256':'a'*64,'sourceGroup':'g-done'}]",
    "truth={'ok':True,'decision':m.DEVELOPMENT_TRUTH_DECISION,'inputs':{'truthRole':'development-evaluation'},'policy':{'trainingUse':'prohibited'},'summary':{'uniqueImageCount':1,'conflictingImageCount':0},'canonicalTruths':[{'fileName':'done.png','imageSha256':'c'*64,'sourceGroup':'g-done'}]}",
    "try:",
    " m.select_pending_items(items,truth); out={'rejected':False}",
    "except ValueError as e:",
    " out={'rejected':True,'message':str(e)}",
    "print(json.dumps(out,ensure_ascii=False))",
  ]);
  assert.equal(result.rejected, true);
  assert.match(String(result.message), /done\.png/);
});
