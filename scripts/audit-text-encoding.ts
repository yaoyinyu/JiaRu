import path from "node:path";
import process from "node:process";
import { readdir, readFile, writeFile } from "node:fs/promises";

const TEXT_EXTENSIONS = new Set([
  ".css",
  ".csv",
  ".json",
  ".md",
  ".py",
  ".ts",
  ".tsx",
  ".txt",
  ".yaml",
  ".yml",
]);
const DEFAULT_ROOTS = ["src", "scripts", "model/training", "docs", "tests"];
const IGNORED_DIRECTORIES = new Set([".git", ".next", "__pycache__", "node_modules"]);
const COMMON_MOJIBAKE_FRAGMENTS = [
  [0x951b, 0xfffd],
  [0x9286, 0xfffd],
  [0x9225, 0xfffd],
  [0x9428, 0x52eb],
  [0x9359, 0xe219],
  [0x7481, 0xe160],
  [0x7efe, 0x572d, 0x608a],
].map((codePoints) => String.fromCodePoint(...codePoints));

interface CliOptions {
  roots: string[];
  outputPath?: string;
}

function parseArgs(argv: string[]): CliOptions {
  const roots: string[] = [];
  let outputPath: string | undefined;
  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === "--root") roots.push(path.resolve(argv[++index] ?? ""));
    else if (arg === "--output") outputPath = path.resolve(argv[++index] ?? "");
    else {
      throw new Error(
        "Usage: node --experimental-strip-types scripts/audit-text-encoding.ts [--root <dir-or-file>]... [--output <report.json>]"
      );
    }
  }
  return {
    roots: roots.length > 0 ? roots : DEFAULT_ROOTS.map((root) => path.resolve(root)),
    outputPath,
  };
}

async function collectTextFiles(targetPath: string): Promise<string[]> {
  const entry = await import("node:fs/promises").then(({ stat }) => stat(targetPath));
  if (entry.isFile()) {
    return TEXT_EXTENSIONS.has(path.extname(targetPath).toLowerCase()) ? [targetPath] : [];
  }
  if (!entry.isDirectory()) return [];
  const files: string[] = [];
  for (const child of await readdir(targetPath, { withFileTypes: true })) {
    if (child.isDirectory() && IGNORED_DIRECTORIES.has(child.name)) continue;
    const childPath = path.join(targetPath, child.name);
    if (child.isDirectory()) files.push(...(await collectTextFiles(childPath)));
    else if (child.isFile() && TEXT_EXTENSIONS.has(path.extname(child.name).toLowerCase())) {
      files.push(childPath);
    }
  }
  return files;
}

const options = parseArgs(process.argv.slice(2));
const decoder = new TextDecoder("utf-8", { fatal: true });
const files = (
  await Promise.all(options.roots.map((root) => collectTextFiles(root)))
).flat().sort();
const failures: Array<{
  filePath: string;
  reasons: string[];
}> = [];
let filesWithBom = 0;

for (const filePath of files) {
  const bytes = await readFile(filePath);
  const reasons: string[] = [];
  let text = "";
  try {
    text = decoder.decode(bytes);
  } catch {
    reasons.push("invalid-utf8");
  }
  if (bytes.length >= 3 && bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf) {
    filesWithBom++;
  }
  if (text.includes("\0")) reasons.push("nul-character");
  if (text.includes(String.fromCodePoint(0xfffd))) {
    reasons.push("replacement-character");
  }
  if ([...text].some((character) => {
    const codePoint = character.codePointAt(0) ?? 0;
    return codePoint >= 0xe000 && codePoint <= 0xf8ff;
  })) {
    reasons.push("private-use-character");
  }
  if (COMMON_MOJIBAKE_FRAGMENTS.some((fragment) => text.includes(fragment))) {
    reasons.push("common-gbk-mojibake");
  }
  if (reasons.length > 0) failures.push({ filePath, reasons: [...new Set(reasons)] });
}

const summary = {
  ok: failures.length === 0,
  roots: options.roots,
  totals: {
    files: files.length,
    failures: failures.length,
    filesWithBom,
  },
  failures,
  checks: [
    "strict UTF-8 decoding",
    "NUL characters",
    "Unicode replacement characters",
    "Unicode private-use characters",
    "high-confidence GBK/UTF-8 mojibake fragments",
  ],
  nextSteps:
    failures.length > 0
      ? ["Re-encode the listed files as UTF-8 and replace corrupted text before release."]
      : ["Text encoding audit passed; keep this gate in regression checks."],
};

if (options.outputPath) {
  await writeFile(options.outputPath, JSON.stringify(summary, null, 2), "utf8");
}
console.log(JSON.stringify(summary, null, 2));
if (!summary.ok) process.exitCode = 1;
