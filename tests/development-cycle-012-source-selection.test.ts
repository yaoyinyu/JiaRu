import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import path from "node:path";
import test from "node:test";

test("循环012源图审计锁定13图13来源组并拒绝受保护角色交叠", () => {
  const script = path.resolve("model/training/audit-development-cycle-012-source-selection.py");
  const code = [
    "import argparse, hashlib, importlib.util, json, pathlib, tempfile",
    "from PIL import Image",
    `p=pathlib.Path(${JSON.stringify(script)})`,
    "s=importlib.util.spec_from_file_location('cycle012_source_test', p)",
    "m=importlib.util.module_from_spec(s); s.loader.exec_module(m)",
    "root=pathlib.Path(tempfile.mkdtemp()); images=root/'images'; images.mkdir()",
    "write=lambda name,value: (root/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\\n',encoding='utf-8')",
    "bind=lambda name: {'path':str((root/name).resolve()),'sha256':m.sha256_file(root/name)}",
    "coverage=sorted(m.REQUIRED_COVERAGE)",
    "plan={'cycleId':'nail-texture-development-cycle-012','decision':'pre_registered_pending_targeted_positive_truth_materialization','releaseState':'hold','targetedPositiveSelectionContract':{'images':13,'masks':65,'sourceGroups':13,'exactlyFiveFullyVisibleNailsPerImage':True,'requiredMorphologyCoverage':coverage}}",
    "write('plan.json',plan)",
    "items=[]",
    "for i in range(13):",
    " image=images/f'image-{i:02d}.png'; Image.new('RGB',(12+i,14+i),(i,i,i)).save(image)",
    " items.append({'fileName':image.name,'sha256':m.sha256_file(image),'width':12+i,'height':14+i,'sourceGroup':f'new-group-{i:02d}','expectedFullyVisibleNails':5,'coverageIntents':[coverage[i%len(coverage)]]})",
    "inventory={'decision':'development_cycle_012_unused_real_positive_inventory','trainingUse':'prohibited','items':[dict(x,candidateStatus='unused_source_candidate',trainingUse='prohibited',sourcePath=str((images/x['fileName']).resolve()),sourceSha256=x['sha256'],derivation='original') for x in items]}  # extra fields are allowed",
    "write('inventory.json',inventory)",
    "spec={'decision':'development_cycle_012_positive_source_candidates_pending_audit','sourceRoot':str(images.resolve()),'cyclePlan':bind('plan.json'),'sourceInventory':bind('inventory.json'),'items':items}",
    "write('spec.json',spec)",
    "review_items=[dict(x,reviewScale='original-resolution',reviewDecision='pass_source_only_pending_complete_mask_review',fullyVisibleNails=5,allVisibleNailsComplete=True,croppedOrPartialNails=0,blurredOrUnreviewableNails=0,watermarkOutsideNailSurfaces=True) for x in items]",
    "review={'decision':'development_cycle_012_original_resolution_source_review_pass_candidate_only','sourceSelectionSpec':bind('spec.json'),'policy':{'trainingUse':'prohibited','completeMaskReviewStillRequired':True},'items':review_items}",
    "write('review.json',review)",
    "training={'ok':True,'decision':'approved_train_internal_development_dataset_materialization','outputDir':str((root/'train').resolve()),'records':[]}",
    "evaluation={'ok':True,'decision':'approved_read_only_clean_development_evaluation','trainingUse':'prohibited','outputDir':str((root/'eval').resolve()),'records':[]}",
    "validation={'ok':True,'decision':'approved_unique_validation_truth_index','canonicalTruths':[]}",
    "frozen={'trainingUse':'prohibited','items':[]}",
    "registry={'ok':True,'decision':'protected_hard_negative_registry','entries':[]}",
    "authorization={'decision':'standing_project_commercial_resource_authorization_granted','scope':{'itemizedTrainingAuthorizationRequired':False}}",
    "corpus={'ok':True,'root':str(images.resolve()),'totals':{'files':13,'validImages':13,'invalidImages':0,'exactDuplicateGroups':0,'exactDuplicateFiles':0,'nearDuplicatePairs':0},'comparisons':{'roots':[str((root/'train/images/train').resolve()),str((root/'eval/images/val').resolve())],'referenceImages':0,'invalidReferences':[],'exactMatches':[],'nearMatches':[]}}",
    "for name,value in [('training.json',training),('evaluation.json',evaluation),('validation.json',validation),('frozen.json',frozen),('registry.json',registry),('authorization.json',authorization),('corpus.json',corpus)]: write(name,value)",
    "args=argparse.Namespace(plan=root/'plan.json',spec=root/'spec.json',source_review_evidence=root/'review.json',source_inventory=root/'inventory.json',training_materialization=root/'training.json',development_evaluation=root/'evaluation.json',validation_truth_index=root/'validation.json',frozen_test_manifest=root/'frozen.json',protected_registry=root/'registry.json',standing_authorization=root/'authorization.json',corpus_audit=root/'corpus.json')",
    "report=m.build(args)",
    "training['records']=[{'fileName':items[0]['fileName'],'imageSha256':items[0]['sha256'],'sourceGroup':items[0]['sourceGroup']}]; write('training.json',training)",
    "rejected=False",
    "try: m.build(args)",
    "except ValueError as error: rejected='受保护角色身份交叠' in str(error)",
    "print(json.dumps({'decision':report['decision'],'counts':report['counts'],'trainingUse':report['trainingUse'],'protectedOverlapRejected':rejected}))",
  ].join("\n");
  const result = JSON.parse(execFileSync("python", ["-c", code], { encoding: "utf8" }));
  assert.deepEqual(result, {
    decision: "development_cycle_012_source_selection_pass_candidate_only",
    counts: { images: 13, sourceGroups: 13, expectedFullyVisibleNails: 65 },
    trainingUse: "prohibited",
    protectedOverlapRejected: true,
  });
});
