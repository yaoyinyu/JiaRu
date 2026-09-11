import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/materialize-development-cycle-012-dataset.py");
const hash = (file: string) => execFileSync("python", ["-c", "import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())", file], { encoding: "utf8" }).trim();
const canonical = (value: unknown) => execFileSync("python", ["-c", "import hashlib,json,sys; print(hashlib.sha256(json.dumps(json.loads(sys.stdin.read()),ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest())"], { input: JSON.stringify(value), encoding: "utf8" }).trim();

test("cycle012 materializer preserves the base split and adds exactly 13 positive images", () => {
  const root = mkdtempSync(path.join(tmpdir(), "cycle012-materialize-"));
  const base = path.join(root, "base");
  for (const item of ["images/train", "labels/train", "images/val", "labels/val", "images/test", "labels/test"]) mkdirSync(path.join(base, item), { recursive: true });
  writeFileSync(path.join(base, "dataset.yaml"), "path: .\ntrain: images/train\nval: images/val\ntest: images/test\nmetadata:\n  dataset_version: train-source-group-development/v1\n");
  execFileSync("python", ["-c", "from PIL import Image; import sys; Image.new('RGB',(50,50),'white').save(sys.argv[1])", path.join(base, "images/train/base.png")]);
  writeFileSync(path.join(base, "labels/train/base.txt"), "0 0.1 0.1 0.2 0.1 0.2 0.2\n");
  const inventory = JSON.parse(execFileSync("python", ["-c", "import hashlib,json,pathlib,sys; r=pathlib.Path(sys.argv[1]); print(json.dumps([{'path':p.relative_to(r).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(x for x in r.rglob('*') if x.is_file())]))", base], { encoding: "utf8" }));
  const baseReport = path.join(root, "base.json");
  writeFileSync(baseReport, JSON.stringify({ ok: true, decision: "approved_train_internal_development_dataset_materialization", trainingUse: "development-experiment-only", outputDir: base, datasetFilesSha256: canonical(inventory), datasetFileCount: inventory.length, counts: { trainImages: 1, trainPositiveImages: 1, trainPositiveMasks: 1, trainHardNegativeImages: 0, evaluationImages: 0, evaluationPositiveImages: 0, evaluationPositiveMasks: 0, evaluationHardNegativeImages: 0, testImages: 0, sourceGroupOverlap: 0 }, records: [{ fileName: "base.png", role: "train-positive", sourceGroup: "base-group", fold: 1, developmentSplit: "train", maskCount: 1, image: "images/train/base.png", imageSha256: hash(path.join(base, "images/train/base.png")), label: "labels/train/base.txt", labelSha256: hash(path.join(base, "labels/train/base.txt")) }] }));
  const truths = [];
  for (let index = 0; index < 13; index += 1) {
    const image = path.join(root, `new-${index}.png`); const annotation = path.join(root, `new-${index}.json`);
    execFileSync("python", ["-c", "from PIL import Image; import sys; Image.new('RGB',(100,100),(int(sys.argv[2]),0,0)).save(sys.argv[1])", image, String(index)]);
    writeFileSync(annotation, JSON.stringify({ image: { width: 100, height: 100 }, annotations: Array.from({ length: 5 }, (_, nail) => ({ polygon: [{ x: nail * 18 + 1, y: 10 }, { x: nail * 18 + 15, y: 10 }, { x: nail * 18 + 15, y: 30 }] })) }));
    truths.push({ fileName: `new-${index}.png`, imagePath: image, imageSha256: hash(image), annotationPath: annotation, annotationSha256: hash(annotation), sourceGroup: `new-group-${index}`, maskCount: 5, trainingUse: "prohibited-until-materialization-audit" });
  }
  const truth = path.join(root, "truth.json"); writeFileSync(truth, JSON.stringify({ ok: true, decision: "development_cycle_012_positive_truth_ready_for_materialization", trainingUse: "prohibited-until-materialization-audit", counts: { images: 13, sourceGroups: 13, masks: 65, invalidPolygons: 0, pairwiseOverlaps: 0 }, canonicalTruths: truths }));
  const output = path.join(root, "output"); const report = path.join(root, "report.json");
  execFileSync("python", [script, "--base-materialization", baseReport, "--positive-truth-audit", truth, "--output-dir", output, "--report", report]);
  const result = JSON.parse(readFileSync(report, "utf8"));
  assert.equal(result.counts.trainImages, 14); assert.equal(result.counts.trainPositiveMasks, 66); assert.equal(result.addedCounts.trainPositiveMasks, 65);
  assert.equal(readFileSync(path.join(output, "labels/train/new-0.txt"), "utf8").trim().split("\n").length, 5);
  execFileSync("python", [script, "--verify-report", report]);
});
