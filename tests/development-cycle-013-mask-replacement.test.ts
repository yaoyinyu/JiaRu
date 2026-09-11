import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import test from "node:test";

function run(code: string): string {
  return execFileSync("python", ["-c", code], { encoding: "utf8" }).trim();
}

const contract = "{'minimumStage2Score':0.25,'maskThreshold':0.5,'minimumAreaRatioToStage1':0.25,'maximumAreaRatioToStage1':3.0,'minimumMaskIouWithStage1':0.05,'maximumCenterShiftToStage1Diagonal':1.0}";

test("cycle013 maps a stage2 pixel mask back and replaces the stage1 polygon", () => {
  const output = run([
    "import json,numpy as np",
    "from model.training.nail_texture_cycle013_mask_replacement import replace_masks_one_to_one",
    "mask=np.zeros((32,32),dtype=np.float32); mask[7:25,9:23]=1",
    `contract=${contract}`,
    "stage1=[{'proposalIndex':0,'score':0.71,'cropBox':[20,10,84,74],'polygon':[[0.25,0.2],[0.55,0.2],[0.55,0.65],[0.25,0.65]]}]",
    "stage2=[{'proposalIndex':0,'score':0.9,'mask':mask}]",
    "result=replace_masks_one_to_one(stage1,stage2,100,100,contract)[0]",
    "print(json.dumps({'source':result['maskSource'],'accepted':result['stage2Accepted'],'status':result['refinementStatus'],'score':result['score'],'pixels':int(result['mask'].sum()),'polygon':result['polygon']}))",
  ].join("; "));
  const result = JSON.parse(output);
  assert.equal(result.source, "stage2-replacement");
  assert.equal(result.accepted, true);
  assert.equal(result.status, "replaced-with-stage2-pixel-mask");
  assert.equal(result.score, 0.71);
  assert.ok(result.pixels > 0);
  assert.ok(result.polygon.every(([x, y]: number[]) => x >= 0 && x <= 1 && y >= 0 && y <= 1));
});

test("cycle013 falls back for empty, boundary-touching, and failed stage2 masks", () => {
  const output = run([
    "import json,numpy as np",
    "from model.training.nail_texture_cycle013_mask_replacement import replace_masks_one_to_one",
    `contract=${contract}`,
    "poly=[[0.2,0.2],[0.4,0.2],[0.4,0.5],[0.2,0.5]]",
    "stage1=[{'proposalIndex':i,'score':0.6,'cropBox':[10,10,60,60],'polygon':poly} for i in range(3)]",
    "empty=np.zeros((16,16),dtype=np.float32)",
    "edge=np.zeros((16,16),dtype=np.float32); edge[0:8,3:10]=1",
    "stage2=[{'proposalIndex':0,'score':0.9,'mask':empty},{'proposalIndex':1,'score':0.9,'mask':edge},{'proposalIndex':2,'score':0.9,'error':'inference'}]",
    "result=replace_masks_one_to_one(stage1,stage2,100,100,contract)",
    "print(json.dumps([item['refinementStatus'] for item in result]))",
  ].join("; "));
  assert.deepEqual(JSON.parse(output), [
    "fallback-stage2-mask-empty",
    "fallback-stage2-mask-touches-roi-boundary",
    "fallback-stage2-inference-error",
  ]);
});

test("cycle013 rejects out-of-bounds crops and mismatched proposal identities", () => {
  const output = run([
    "import json,numpy as np",
    "from model.training.nail_texture_cycle013_mask_replacement import map_roi_binary_mask",
    "mask=np.zeros((16,16),dtype=np.float32); mask[3:12,3:12]=1",
    "_,_,reason,_=map_roi_binary_mask(mask,(-1,0,20,20),100,100)",
    "print(json.dumps({'reason':reason}))",
  ].join("; "));
  assert.deepEqual(JSON.parse(output), { reason: "crop-out-of-bounds" });
  const rejected = spawnSync("python", ["-c", [
    "import numpy as np",
    "from model.training.nail_texture_cycle013_mask_replacement import replace_masks_one_to_one",
    `contract=${contract}`,
    "mask=np.zeros((16,16),dtype=np.float32); mask[3:12,3:12]=1",
    "replace_masks_one_to_one([{'proposalIndex':0,'score':0.6,'cropBox':[0,0,20,20],'polygon':[[0.1,0.1],[0.2,0.1],[0.2,0.2]]}],[{'proposalIndex':1,'score':0.9,'mask':mask}],100,100,contract)",
  ].join("; ")], { encoding: "utf8" });
  assert.notEqual(rejected.status, 0);
});

test("cycle013 square crop is deterministic for edge and small targets", () => {
  const output = run([
    "import json",
    "from model.training.nail_texture_cycle013_mask_replacement import square_crop",
    "print(json.dumps([square_crop((0,2,8,12),100,80,0.5),square_crop((90,65,99,79),100,80,0.5),square_crop((40,30,41,31),100,80,0.5)]))",
  ].join("; "));
  assert.deepEqual(JSON.parse(output), [[0, 0, 20, 20], [72, 52, 100, 80], [32, 22, 48, 38]]);
});

test("cycle013 plan contract locks true mask replacement and one execution", () => {
  const validPlan = {
    schemaVersion: 1,
    cycleId: "nail-texture-development-cycle-013",
    decision: "pre_registered_high_resolution_roi_pixel_mask_replacement",
    releaseState: "hold",
    hypothesis: { onlyVariable: "highResolutionSingleNailPixelMaskReplacement", oldScoreOnlyStage2RemainsClosed: true },
    stage1: { role: "frozen_full_image_recall_and_candidate_generator", inputSize: 512, scoreThreshold: 0.25, maximumCandidatesPerImage: 10, productDeduplicationUnchanged: true },
    stage2: {
      role: "single_nail_high_resolution_pixel_mask_replacement",
      inputSize: 384,
      cropContextRatio: 0.65,
      maximumInstancesPerRoi: 1,
      outputSemantics: "two_dimensional_binary_mask_mapped_to_full_image_then_replaces_stage1_mask",
      failureSemantics: "fallback_to_same_stage1_candidate_and_record_reason",
      geometryAcceptance: { minimumStage2Score: 0.25, maskThreshold: 0.5, minimumAreaRatioToStage1: 0.25, maximumAreaRatioToStage1: 3, minimumMaskIouWithStage1: 0.05, maximumCenterShiftToStage1Diagonal: 1 },
    },
    stage2TrainingData: { parentRole: "train-only", proposalSource: "frozen-stage1-on-train-images-only", labelSource: "original-resolution-reviewed-parent-ground-truth", sourceGroupAtomicSplit: true, validationSourceGroups: 18, splitSeed: 20260910, trainVariants: ["base", "shift_x_neg06", "shift_x_pos06"], minimumUniqueAssociatedTruths: 1400, formalVal30Test100OrHoldoutUsed: false },
    training: { architecture: "yolo11n-seg", initialization: "frozen-cycle011-stage1-weights", epochs: 12, patience: 4, batch: 4, optimizer: "AdamW", lr0: 0.0002, workers: 0, mosaic: 0, maskRatio: 1, overlapMask: false, distillation: false },
    executionLock: { maximumProposalMaterializationRuns: 1, maximumStage2TrainingRuns: 1, maximumClean98InferenceRuns: 1, allOutputRootsMustBeNew: true, implementationHashesLockedBeforeFirstInference: true },
    signalJudgement: {
      relativeToCycle011Clean98: { maximumMissingImages: 10, maximumMissingInstances: 16, minimumInstanceRecall: 0.94067797, minimumCompleteMaskRatio: 0.85, maximumWeightedSpuriousRate: 0.0960452, minimumDirectlyExtractableRate: 0.5 },
      developmentAbsoluteFloor: { minimumInstanceRecall: 0.9, minimumCompleteMaskRatio: 0.85, maximumMissingImageRate: 0.1, maximumWeightedSpuriousRate: 0.02 },
      allRelativeAndAbsoluteRequired: true,
      failureClosesBranchWithoutParameterScan: true,
    },
    prohibited: ["reuse_old_score_only_stage2", "read_or_infer_old_val30_test100_or_release_holdout", "train_on_clean98", "scan_stage2_score_mask_threshold_roi_size_context_loss_seed_or_epochs", "describe_fallback_stage1_mask_as_stage2_success", "promote_before_all_relative_and_absolute_gates_pass"],
  };
  const verifier = [
    "import importlib.util,json,pathlib,sys",
    "p=pathlib.Path('model/training/verify-development-cycle-013-plan.py')",
    "s=importlib.util.spec_from_file_location('cycle013_plan',p)",
    "m=importlib.util.module_from_spec(s); s.loader.exec_module(m)",
    "m.validate_contract(json.loads(sys.argv[1]))",
  ].join("; ");
  assert.doesNotThrow(() => execFileSync("python", ["-c", verifier, JSON.stringify(validPlan)], { encoding: "utf8" }));
  const drifted = structuredClone(validPlan);
  drifted.stage2.outputSemantics = "score_only_keep_stage1_polygon";
  const result = spawnSync("python", ["-c", verifier, JSON.stringify(drifted)], { encoding: "utf8" });
  assert.notEqual(result.status, 0);
});
