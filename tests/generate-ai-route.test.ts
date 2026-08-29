import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import {
  AI_IMAGE_SCENE_SUFFIX,
  HAND_ANATOMY_SYSTEM_PROMPT,
  HAND_COUNT_PREFIX,
  assembleAiImagePrompt,
} from "../src/lib/ai-hand-anatomy-prompt.ts";

const ROUTE_SOURCE = resolve(
  "src/app/api/generate-ai/route.ts"
);

test("generate-ai route imports and calls the prompt assembler (hidden system prompt wired in)", () => {
  const source = readFileSync(ROUTE_SOURCE, "utf-8");
  assert.ok(
    source.includes('from "@/lib/ai-hand-anatomy-prompt"'),
    "route must import prompt assemblers from ai-hand-anatomy-prompt"
  );
  assert.ok(
    source.includes("assembleAiImagePrompt") &&
      source.includes("assembleAiImageEditPrompt"),
    "route must import both text-to-image and image-to-image assemblers"
  );
  assert.ok(
    source.includes("image\n    ? assembleAiImageEditPrompt(prompt)\n    : assembleAiImagePrompt(prompt)"),
    "route must pick image-edit assembler when a reference image is present"
  );
  assert.ok(
    !source.includes("const enhancedPrompt = `${prompt},"),
    "route must no longer use the old inline suffix template"
  );
});

test("generate-ai route validates optional reference image and ratio", () => {
  const source = readFileSync(ROUTE_SOURCE, "utf-8");
  assert.ok(
    source.includes("IMAGE_DATA_URI_PATTERN"),
    "route must validate the image Data URI prefix"
  );
  assert.ok(
    source.includes("ALLOWED_RATIOS"),
    "route must whitelist allowed ratios"
  );
  assert.ok(
    source.includes("ALLOWED_SIZES"),
    "route must whitelist allowed size tiers"
  );
  assert.ok(
    source.includes("imageDataUri: image || undefined"),
    "route must forward the image to the Agnes client"
  );
  assert.ok(
    source.includes("ratio,\n      size,"),
    "route must forward both ratio and size to the Agnes client"
  );
  assert.ok(
    source.includes('from "@/lib/ai-image-size"'),
    "route must import shared size/ratio definition"
  );
});

test("assembled provider prompt contains prefix, user prompt, scene suffix and hidden system prompt in order", () => {
  const user = "展现甜美少女风美甲的女性手部近景生活照";
  const assembled = assembleAiImagePrompt(user);
  const prefixIndex = assembled.indexOf(HAND_COUNT_PREFIX);
  const userIndex = assembled.indexOf(user);
  const systemIndex = assembled.indexOf(HAND_ANATOMY_SYSTEM_PROMPT);
  const suffixIndex = assembled.indexOf(AI_IMAGE_SCENE_SUFFIX);
  assert.equal(prefixIndex, 0, "hand-count prefix must be first");
  assert.ok(userIndex > prefixIndex, "user prompt must follow prefix");
  assert.ok(suffixIndex > userIndex, "scene suffix must follow user prompt");
  assert.ok(systemIndex > suffixIndex, "system prompt must come after suffix");
  assert.equal(
    systemIndex + HAND_ANATOMY_SYSTEM_PROMPT.length,
    assembled.length,
    "system prompt must be the very last segment"
  );
});
