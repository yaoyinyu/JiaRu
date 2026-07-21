import { realpath, stat } from "node:fs/promises";
import path from "node:path";

function caseFold(value: string): string {
  return path.resolve(value).replaceAll("/", "\\").toLowerCase();
}

async function resolvedAlias(filePath: string): Promise<string> {
  const resolved = path.resolve(filePath);
  try {
    return caseFold(await realpath(resolved));
  } catch {
    try {
      const parent = await realpath(path.dirname(resolved));
      return caseFold(path.join(parent, path.basename(resolved)));
    } catch {
      return caseFold(resolved);
    }
  }
}

async function fileIdentity(filePath: string): Promise<string | null> {
  try {
    const info = await stat(filePath, { bigint: true });
    return `${info.dev}:${info.ino}`;
  } catch {
    return null;
  }
}

export async function assertSafeOutputPath(outputPath: string, inputPaths: Iterable<string>): Promise<void> {
  const output = path.resolve(outputPath);
  const outputFolded = caseFold(output);
  const outputAlias = await resolvedAlias(output);
  const outputIdentity = await fileIdentity(output);
  const uniqueInputs = [...new Set(
    [...inputPaths]
      .filter((value) => typeof value === "string" && value.trim())
      .map((value) => path.resolve(value)),
  )];
  for (const input of uniqueInputs) {
    if (outputFolded === caseFold(input) || outputAlias === await resolvedAlias(input)) {
      throw new Error(`--output must not overwrite an input evidence file: ${input}`);
    }
    const inputIdentity = outputIdentity === null ? null : await fileIdentity(input);
    if (outputIdentity !== null && inputIdentity !== null && outputIdentity === inputIdentity) {
      throw new Error(`--output must not overwrite an input evidence file alias: ${input}`);
    }
  }
}
