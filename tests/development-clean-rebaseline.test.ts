import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import path from "node:path";
import test from "node:test";

test("干净开发评估物化器冻结58正图、354 mask和40负图", () => {
  const script = path.resolve("model/training/materialize-clean-development-evaluation.py");
  const code = [
    "import hashlib, importlib.util, json, pathlib, tempfile",
    `p=pathlib.Path(${JSON.stringify(script)})`,
    "s=importlib.util.spec_from_file_location('clean_materializer_test', p)",
    "m=importlib.util.module_from_spec(s); s.loader.exec_module(m)",
    "root=pathlib.Path(tempfile.mkdtemp()); positive=root/'positive'; legacy=root/'legacy'",
    "(positive/'images/val').mkdir(parents=True); (positive/'labels/val').mkdir(parents=True); (positive/'metadata').mkdir()",
    "(legacy/'images/val').mkdir(parents=True); (legacy/'labels/val').mkdir(parents=True); (legacy/'images/train').mkdir(parents=True); (legacy/'labels/train').mkdir(parents=True)",
    "sha=lambda value: hashlib.sha256(value.read_bytes()).hexdigest()",
    "positive_records=[]",
    "for i in range(58):",
    " image=positive/'images/val'/f'p{i:02d}.jpg'; image.write_bytes(f'positive-{i}'.encode())",
    " label=positive/'labels/val'/f'p{i:02d}.txt'; count=7 if i < 6 else 6; label.write_text(('0 0.1 0.1 0.2 0.1 0.2 0.2\\n')*count, encoding='utf-8')",
    " positive_records.append({'fileName':image.name,'sourceGroup':f'positive-{i}','maskCount':count,'imageSha256':sha(image),'label':f'labels/val/{label.name}','labelSha256':sha(label)})",
    "positive_index={'schemaVersion':1,'ok':True,'decision':'development_positive_truth_v2_final_review_pass','trainingUse':'development-experiment-only','formalCalibrationTestOrHoldoutEligible':False,'counts':{'images':58,'masks':354},'recordsSha256':m.canonical_sha256(positive_records),'records':positive_records}",
    "positive_path=positive/'metadata/index.json'; positive_path.write_text(json.dumps(positive_index), encoding='utf-8')",
    "train_image=legacy/'images/train/train.jpg'; train_image.write_bytes(b'train'); train_label=legacy/'labels/train/train.txt'; train_label.write_text('x', encoding='utf-8')",
    "legacy_records=[{'fileName':'train.jpg','role':'train-positive','sourceGroup':'train','developmentSplit':'train','maskCount':1,'image':'images/train/train.jpg','imageSha256':sha(train_image),'label':'labels/train/train.txt','labelSha256':sha(train_label)}]",
    "for i in range(40):",
    " image=legacy/'images/val'/f'n{i:02d}.jpg'; image.write_bytes(f'negative-{i}'.encode()); label=legacy/'labels/val'/f'n{i:02d}.txt'; label.write_bytes(b'')",
    " legacy_records.append({'fileName':image.name,'role':'hard-negative','sourceGroup':f'negative-{i}','developmentSplit':'val','maskCount':0,'image':f'images/val/{image.name}','imageSha256':sha(image),'label':f'labels/val/{label.name}','labelSha256':sha(label)})",
    "legacy_report={'schemaVersion':1,'ok':True,'status':'PASS','decision':'approved_train_internal_development_dataset_materialization','outputDir':str(legacy),'recordsSha256':m.canonical_sha256(legacy_records),'records':legacy_records}",
    "legacy_path=root/'legacy-report.json'; legacy_path.write_text(json.dumps(legacy_report), encoding='utf-8')",
    "output=root/'output'; report_path=root/'report.json'; report=m.build_report(positive_path, legacy_path, output, report_path); replay=m.verify_report(report_path)",
    "yaml=(output/'dataset.yaml').read_text(encoding='utf-8')",
    "assert report['counts']['evaluationImages']==98 and report['counts']['evaluationPositiveMasks']==354",
    "assert report['counts']['sourceGroupOverlap']==0 and report['counts']['imageSha256Overlap']==0",
    "assert 'test: images/val' in yaml and 'task: segment' in yaml and 'image_size: 512' in yaml",
    "print(json.dumps({'ok':replay['ok'],'records':len(replay['records'])}))",
  ].join("\n");
  const result = JSON.parse(execFileSync("python", ["-c", code], { encoding: "utf8" }));
  assert.deepEqual(result, { ok: true, records: 98 });
});

test("循环012计划锁定唯一变量、样本数量和开发绝对门", async () => {
  const plan = JSON.parse(
    await (await import("node:fs/promises")).readFile(
      "model/training/nail-texture-development-cycle-012-plan-v1.json",
      "utf8",
    ),
  );
  assert.equal(plan.hypothesis.onlyVariable, "targetedSourceIsolatedRealPositiveAugmentation");
  assert.equal(plan.targetedPositiveSelectionContract.images, 13);
  assert.equal(plan.targetedPositiveSelectionContract.masks, 65);
  assert.equal(plan.fixedTrainingContract.maximumExperiments, 1);
  assert.deepEqual(plan.formalFloorForPromotionToFullTrain, {
    minimumInstanceRecall: 0.9,
    minimumCompleteMaskRatio: 0.85,
    maximumMissingImageRate: 0.1,
    maximumWeightedSpuriousRate: 0.02,
    everyEvaluationImageAccountedFor: true,
  });
});
