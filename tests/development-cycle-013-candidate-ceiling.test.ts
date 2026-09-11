import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const SCRIPT = path.join(
  process.cwd(),
  "model",
  "training",
  "analyze-development-cycle-013-candidate-ceiling.py",
);

const PREAMBLE = [
  "import importlib.util, json, sys",
  `spec = importlib.util.spec_from_file_location('ceiling', r'${SCRIPT}')`,
  "m = importlib.util.module_from_spec(spec)",
  "sys.modules['ceiling'] = m",
  "spec.loader.exec_module(m)",
];

/** 通过 python 子进程在已加载模块的命名空间里执行多行代码，返回去掉首尾空白的 stdout。 */
function run(lines: string[]): string {
  const program = [...PREAMBLE, ...lines].join("\n");
  return execFileSync("python", ["-c", program], { encoding: "utf8" }).trim();
}

function runJson<T>(lines: string[]): T {
  const output = run(lines);
  return JSON.parse(output.split("\n").pop() as string) as T;
}

const HELPERS = [
  "from shapely.geometry import Polygon",
  "box = lambda x0, y0, x1, y1: Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])",
  "def make_recon(images, summary):",
  "    internal = {row['stem']: {'role': row['role'], 'truth': row['truth'], 'predicted': row['predicted'], 'matches': row['matches'], 'missing': row['missing'], 'unmatched': row['unmatched']} for row in images}",
  "    return {'summary': summary, 'internal': internal}",
];

test("wilson 区间在 k=0 与 k=n 边界处有限且落在 [0,1]", () => {
  const result = runJson<{ low0: number; high0: number; lowN: number; highN: number }>([
    "a = m.wilson_interval(0, 58)",
    "b = m.wilson_interval(58, 58)",
    "print(json.dumps({'low0': a[0], 'high0': a[1], 'lowN': b[0], 'highN': b[1]}))",
  ]);
  assert.equal(result.low0, 0);
  assert.ok(result.high0 > 0 && result.high0 < 1);
  assert.equal(result.highN, 1);
  assert.ok(result.lowN > 0 && result.lowN < 1);
});

test("基线漏甲图 13/58 的 Wilson 区间覆盖相对门 10/58，判定为噪声内不可判别", () => {
  const result = runJson<{ low: number; high: number; gate: number; inside: boolean }>([
    "low, high = m.wilson_interval(13, 58)",
    "gate = 10 / 58",
    "print(json.dumps({'low': low, 'high': high, 'gate': gate, 'inside': bool(low <= gate <= high)}))",
  ]);
  assert.equal(result.inside, true, "10/58 必须落在 13/58 的 95% 区间内（判定分辨率不足）");
  assert.ok(result.gate > result.low && result.gate < result.high);
});

test("最大基数匹配在候选竞争场景优于贪心（贪心得 1，最大匹配得 2）", () => {
  const result = runJson<{ size: number }>([
    "pairs = [(0.9, 0, 0), (0.8, 1, 0), (0.1, 0, 1)]",
    "print(json.dumps({'size': len(m.maximum_bipartite_matching(pairs))}))",
  ]);
  assert.equal(result.size, 2);
});

test("最大基数匹配不虚高：一个候选不能同时救两枚真值", () => {
  const result = runJson<{ size: number; manyToOne: number }>([
    "a = m.maximum_bipartite_matching([(0.8, 0, 0), (0.7, 0, 1)])",
    "b = m.maximum_bipartite_matching([(0.9, 0, 0), (0.8, 1, 0), (0.7, 2, 0)])",
    "print(json.dumps({'size': len(a), 'manyToOne': len(b)}))",
  ]);
  assert.equal(result.size, 1);
  assert.equal(result.manyToOne, 1);
});

test("附着矩阵只保留正 IoU 边，且 ε 阈值可过滤", () => {
  const result = runJson<{ raw: number; atFive: number; atTen: number }>([
    ...HELPERS,
    "truth = [(box(0, 0, .2, .2), 0.9, True), (box(.5, .5, .7, .7), 0.9, True)]",
    "pred = [(box(0, 0, .2, .2), .9, True), (box(.52, .52, .68, .68), .8, True), (box(.9, 0, 1, .1), .7, True)]",
    "pairs = m.attachment_pairs(truth, pred, [1, 2], [1])",
    "print(json.dumps({'raw': len(pairs), 'atFive': sum(1 for iou, _, _ in pairs if iou >= 0.05), 'atTen': sum(1 for iou, _, _ in pairs if iou >= 0.10)}))",
  ]);
  assert.equal(result.raw, 1, "纯杂散候选与漏甲真值无重叠，不应产生附着边");
  assert.equal(result.atFive, 1);
  assert.equal(result.atTen, 1);
});

test("全零预测图不可由逐甲 mask 替换修复：漏甲图数保持不变", () => {
  const result = runJson<{
    rescued: number;
    missingAfter: number;
    missingImages: number;
    unattached: number;
  }>([
    ...HELPERS,
    "images = [{'stem': 'n', 'role': 'train-positive', 'truth': [(box(0, 0, .2, .2), 1.0, True)], 'predicted': [], 'matches': [], 'missing': [0], 'unmatched': []}]",
    "summary = {'predictions': 0, 'matched': 0, 'weightedSpuriousNumerator': 0.0}",
    "run = m.simulate(make_recon(images, summary), 0.05, 1.0)",
    "print(json.dumps({'rescued': run['rescuedInstances'], 'missingAfter': run['summary']['missing'], 'missingImages': run['summary']['missingImages'], 'unattached': run['missingTruthsWithoutAttachableCandidate']}))",
  ]);
  assert.equal(result.rescued, 0);
  assert.equal(result.missingAfter, 1);
  assert.equal(result.missingImages, 1);
  assert.equal(result.unattached, 1);
});

test("杂散轴可达：救回一个假阳性候选使加权分子减少 2", () => {
  const result = runJson<{ reduction: number; ceiling: number; rescued: number }>([
    ...HELPERS,
    "images = [{'stem': 's', 'role': 'train-positive', 'truth': [(box(0, 0, .2, .2), 0.9, True), (box(.5, .5, .7, .7), 0.9, True)], 'predicted': [(box(0, 0, .2, .2), .9, True), (box(.52, .52, .68, .68), .8, True), (box(.9, 0, 1, .1), .7, True)], 'matches': [(0, 0, 1.0)], 'missing': [1], 'unmatched': [1, 2]}]",
    "summary = {'predictions': 3, 'matched': 1, 'weightedSpuriousNumerator': 4.0}",
    "run = m.simulate(make_recon(images, summary), 0.05, 1.0)",
    "print(json.dumps({'reduction': run['weightedSpuriousReduction'], 'ceiling': run['summary']['weightedSpuriousNumerator'], 'rescued': run['rescuedInstances']}))",
  ]);
  assert.equal(result.rescued, 1);
  assert.equal(result.reduction, 2);
  assert.equal(result.ceiling, 2);
});

test("三档判决由双轴达标情况决定", () => {
  const result = runJson<{ reachable: string; single: string; none: string; maxAllowed: number }>([
    "def s(recall, complete, missingImages, spurious, positives=58):",
    "    return {'instanceRecall': recall, 'completeMaskRatio': complete, 'missingImages': missingImages, 'weightedSpuriousRate': spurious, 'positiveImages': positives}",
    "a = m.verdict_for(s(0.95, 0.90, 3, 0.01))",
    "b = m.verdict_for(s(0.95, 0.90, 3, 0.50))",
    "c = m.verdict_for(s(0.50, 0.50, 30, 0.50))",
    "print(json.dumps({'reachable': a['decision'], 'single': b['decision'], 'none': c['decision'], 'maxAllowed': a['maximumMissingImagesAllowed']}))",
  ]);
  assert.equal(result.reachable, "reachable");
  assert.equal(result.single, "reachable_on_single_axis_only");
  assert.equal(result.none, "unreachable_by_mask_replacement_stage2");
  assert.equal(result.maxAllowed, 5, "58 张正图的 10% 门限为 5 张");
});

test("余量警示：需要吃掉 ≥90% 可达余量时标记 requiresNearPerfectStage2", () => {
  const result = runJson<{ tight: boolean; shareTight: number; loose: boolean; shareLoose: number }>([
    "base = {'summary': {'predictions': 20, 'matched': 0, 'weightedSpuriousNumerator': 20.0}}",
    "tight = m.build_margin(base, {'summary': {'weightedSpuriousNumerator': 7.0}, 'missingTruthsWithoutAttachableCandidate': 0})",
    "loose = m.build_margin(base, {'summary': {'weightedSpuriousNumerator': 0.0}, 'missingTruthsWithoutAttachableCandidate': 0})",
    "print(json.dumps({'tight': tight['requiresNearPerfectStage2'], 'shareTight': tight['requiredShareOfAchievableDrop'], 'loose': loose['requiresNearPerfectStage2'], 'shareLoose': loose['requiredShareOfAchievableDrop']}))",
  ]);
  assert.equal(result.tight, true);
  assert.ok(result.shareTight >= 0.9);
  assert.equal(result.loose, false);
  assert.ok(result.shareLoose < 0.9);
});

test("保真门：重建与冻结报告不一致时阻止给出结论", () => {
  const result = runJson<{ okSame: boolean; okDiff: boolean; mismatch: number; checks: number }>([
    "row = {'stem': 'a', 'role': 'train-positive', 'truthCount': 1, 'predictionCount': 1, 'matchedCount': 1, 'completeMaskCount': 1, 'missingCount': 0, 'missingTruthIndices': [], 'duplicateCount': 0, 'falsePositiveCount': 0, 'invalidPredictionMaskCount': 0, 'matchedInstances': [{'truthIndex': 1, 'predictionIndex': 1}], 'unmatchedPredictions': []}",
    "summary = {'matched': 1, 'completeMasks': 1, 'missing': 0, 'missingImages': 0, 'duplicates': 0, 'falsePositives': 0, 'invalidPredictionMasks': 0, 'truth': 1, 'predictions': 1, 'instanceRecall': 1.0, 'completeMaskRatio': 1.0, 'missingImageRate': 0.0, 'weightedSpuriousRate': 0.0, 'directlyExtractableRate': 1.0}",
    "recon = {'images': [dict(row)], 'summary': dict(summary)}",
    "frozen = {'images': [dict(row)], 'summary': dict(summary)}",
    "same = m.check_fidelity(recon, frozen)",
    "bad = json.loads(json.dumps(frozen))",
    "bad['images'][0]['missingCount'] = 1",
    "diff = m.check_fidelity(recon, bad)",
    "print(json.dumps({'okSame': same['ok'], 'okDiff': diff['ok'], 'mismatch': diff['mismatchCount'], 'checks': same['checks']}))",
  ]);
  assert.equal(result.okSame, true);
  assert.equal(result.okDiff, false);
  assert.equal(result.mismatch, 1);
  assert.ok(result.checks > 0);
});

test("内容哈希校验能检出被篡改的报告，深重放拒绝未知报告类型", () => {
  const dir = mkdtempSync(path.join(tmpdir(), "cycle013-ceiling-"));
  const report = path.join(dir, "report.json");
  try {
    writeFileSync(
      report,
      run([
        "body = {'schemaVersion': 1, 'decision': 'reachable'}",
        "body['contentSha256'] = m.canonical_sha256(body)",
        "print(json.dumps(body, ensure_ascii=False))",
      ]),
      "utf8",
    );
    const verifyContent = [
      "p = m.read_json(__import__('pathlib').Path(sys.argv[1]))",
      "sys.exit(0 if m.verify_content_sha256(p) else 1)",
    ];
    const intact = spawnSync("python", ["-c", [...PREAMBLE, ...verifyContent].join("\n"), report], {
      encoding: "utf8",
    });
    assert.equal(intact.status, 0, "未篡改的报告内容哈希应通过");
    const deep = spawnSync(
      "python",
      ["-c", [...PREAMBLE, "sys.exit(m.verify_report(__import__('pathlib').Path(sys.argv[1])))"].join("\n"), report],
      { encoding: "utf8" },
    );
    assert.notEqual(deep.status, 0, "未知报告类型不能伪装成已深重放");

    writeFileSync(
      report,
      JSON.stringify({ schemaVersion: 1, decision: "unreachable", contentSha256: "deadbeef" }),
      "utf8",
    );
    const tampered = spawnSync("python", ["-c", [...PREAMBLE, ...verifyContent].join("\n"), report], {
      encoding: "utf8",
    });
    assert.notEqual(tampered.status, 0, "篡改后的报告必须非零退出");
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
