import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  clearEditorDraft,
  draftMatchesImageSize,
  EDITOR_DRAFT_STORAGE_KEY,
  loadEditorDraft,
  saveEditorDraft,
  type EditorDraft,
  type EditorDraftStorage,
} from "../src/lib/editor-draft.ts";

// ── 内存 storage 注入（浏览器 sessionStorage 同构接口） ──

function createMemoryStorage(): EditorDraftStorage & { dump(): string | undefined } {
  const map = new Map<string, string>();
  return {
    getItem: (key) => map.get(key) ?? null,
    setItem: (key, value) => {
      map.set(key, value);
    },
    removeItem: (key) => {
      map.delete(key);
    },
    dump: () => map.get(EDITOR_DRAFT_STORAGE_KEY),
  };
}

function createThrowingStorage(): EditorDraftStorage {
  return {
    getItem: () => {
      throw new Error("storage_blocked");
    },
    setItem: () => {
      throw new Error("quota_exceeded");
    },
    removeItem: () => {
      throw new Error("storage_blocked");
    },
  };
}

function validDraft(overrides: Partial<EditorDraft> = {}): EditorDraft {
  return {
    frames: [
      {
        id: "frame-1",
        cx: 100,
        cy: 200,
        angle: 0.2,
        nl: 60,
        nw: 30,
        assignedFinger: 1,
      },
    ],
    placements: [
      {
        id: "placement-frame-1",
        frameId: "frame-1",
        textureKey: "set-a/1",
        textureSrc: "/nail-textures/set-a/finger-2.png",
        aspect: 1.1,
        angle: 0.2,
        baseCx: 100,
        baseCy: 200,
        baseLength: 60,
        baseWidth: 30,
        cx: 100,
        cy: 200,
        length: 66,
        width: 30,
        adjust: { lengthScale: 1, widthScale: 1, rootOffset: 0 },
      },
    ],
    activeSetId: "set-a",
    pinnedTextureKey: null,
    imageWidth: 1200,
    imageHeight: 900,
    savedAt: 1730000000000,
    ...overrides,
  };
}

// ── 保存 / 恢复 round-trip ──

test("saveEditorDraft then loadEditorDraft round-trips the full draft", () => {
  const storage = createMemoryStorage();
  const draft = validDraft();
  assert.equal(saveEditorDraft(storage, draft), true);

  const loaded = loadEditorDraft(storage);
  assert.ok(loaded);
  assert.deepEqual(loaded, draft);
  assert.equal(loaded.frames.length, 1);
  assert.equal(loaded.placements.length, 1);
  assert.equal(loaded.activeSetId, "set-a");
  assert.equal(loaded.imageWidth, 1200);
  assert.equal(loaded.imageHeight, 900);
});

test("saveEditorDraft strips recognition masks (Uint8Array) before serializing", () => {
  const storage = createMemoryStorage();
  const draft = validDraft();
  draft.frames[0]!.mask = {
    width: 2,
    height: 2,
    data: new Uint8Array([1, 0, 1, 0]),
    originX: 0,
    originY: 0,
    scale: 1,
  };
  assert.equal(saveEditorDraft(storage, draft), true);

  const raw = storage.dump();
  assert.ok(raw);
  const parsed = JSON.parse(raw) as { frames: Array<Record<string, unknown>> };
  assert.equal("mask" in parsed.frames[0]!, false, "mask 不得进入草稿序列化字节");

  const loaded = loadEditorDraft(storage);
  assert.ok(loaded);
  assert.equal(loaded.frames[0]?.mask, undefined);
  // 几何与指位保留，足够重建贴合。
  assert.equal(loaded.frames[0]?.nl, 60);
  assert.equal(loaded.frames[0]?.assignedFinger, 1);
});

test("saveEditorDraft keeps null texture selection fields", () => {
  const storage = createMemoryStorage();
  const draft = validDraft({ activeSetId: null, pinnedTextureKey: "set-b/2" });
  assert.equal(saveEditorDraft(storage, draft), true);
  const loaded = loadEditorDraft(storage);
  assert.ok(loaded);
  assert.equal(loaded.activeSetId, null);
  assert.equal(loaded.pinnedTextureKey, "set-b/2");
});

// ── 失效分支：缺失 / 损坏 / 结构不合法 / 存储异常 ──

test("loadEditorDraft returns null when no draft was saved", () => {
  const storage = createMemoryStorage();
  assert.equal(loadEditorDraft(storage), null);
});

test("loadEditorDraft returns null on corrupted JSON", () => {
  const storage = createMemoryStorage();
  storage.setItem(EDITOR_DRAFT_STORAGE_KEY, "{not-json");
  assert.equal(loadEditorDraft(storage), null);
});

test("loadEditorDraft returns null when required draft fields are missing or wrong", () => {
  const cases: unknown[] = [
    null,
    "string",
    42,
    {},
    validDraft({ frames: "nope" as unknown as EditorDraft["frames"] }),
    validDraft({ placements: "nope" as unknown as EditorDraft["placements"] }),
    validDraft({ activeSetId: 3 as unknown as string }),
    validDraft({ pinnedTextureKey: 3 as unknown as string }),
    validDraft({ imageWidth: 0 }),
    validDraft({ imageHeight: Number.NaN }),
    validDraft({ savedAt: "yesterday" as unknown as number }),
  ];
  for (const invalid of cases) {
    const storage = createMemoryStorage();
    storage.setItem(EDITOR_DRAFT_STORAGE_KEY, JSON.stringify(invalid));
    assert.equal(loadEditorDraft(storage), null, `应拒绝非法草稿：${JSON.stringify(invalid)}`);
  }
});

test("loadEditorDraft rejects drafts with malformed frame or placement entries", () => {
  const missingFrameGeometry = validDraft();
  (missingFrameGeometry.frames[0] as unknown as Record<string, unknown>).nl = "wide";
  const missingPlacementId = validDraft();
  (missingPlacementId.placements[0] as unknown as Record<string, unknown>).id = "";

  for (const invalid of [missingFrameGeometry, missingPlacementId]) {
    const storage = createMemoryStorage();
    storage.setItem(EDITOR_DRAFT_STORAGE_KEY, JSON.stringify(invalid));
    assert.equal(loadEditorDraft(storage), null);
  }
});

test("storage failures degrade: save returns false, load/clear stay silent", () => {
  const storage = createThrowingStorage();
  assert.equal(saveEditorDraft(storage, validDraft()), false);
  assert.equal(loadEditorDraft(storage), null);
  assert.doesNotThrow(() => clearEditorDraft(storage));
});

test("null storage is accepted and no-ops", () => {
  assert.equal(saveEditorDraft(null, validDraft()), false);
  assert.equal(loadEditorDraft(null), null);
  assert.doesNotThrow(() => clearEditorDraft(null));
});

test("clearEditorDraft removes the stored draft", () => {
  const storage = createMemoryStorage();
  saveEditorDraft(storage, validDraft());
  clearEditorDraft(storage);
  assert.equal(loadEditorDraft(storage), null);
});

// ── 恢复判决：原图尺寸比对 ──

test("draftMatchesImageSize accepts only exact dimension matches", () => {
  const draft = validDraft();
  assert.equal(draftMatchesImageSize(draft, 1200, 900), true);
  assert.equal(draftMatchesImageSize(draft, 900, 1200), false);
  assert.equal(draftMatchesImageSize(draft, 1201, 900), false);
  assert.equal(draftMatchesImageSize(draft, 1200, 901), false);
});

// ── 页面接线合同：恢复提示、尺寸不一致丢弃、导出清除、beforeunload 守卫 ──

function readPageSource(): string {
  return readFileSync(new URL("../src/app/editor/page.tsx", import.meta.url), "utf8");
}

test("editor page mounts the restore banner and auto-restores after upload", () => {
  const source = readPageSource();
  assert.match(source, /loadEditorDraft\(getSessionStorage\(\)\)/);
  assert.match(source, /上次编辑未保存，重新上传原图可恢复。/);
  // 上传成功（原图解码回调）后按尺寸比对恢复。
  assert.match(source, /restoreFromDraftIfCompatible\(image\)/);
  assert.match(source, /新照片与草稿尺寸不符，已忽略草稿。/);
  assert.match(source, /已恢复上次编辑：/);
  // 消费过草稿的上传跳过自动识别（识别会覆盖恢复出的甲面框）。
  assert.match(source, /if \(restoredForImageRef\.current\) return;/);
});

test("editor page saves the draft debounced and clears it after export or photo change", () => {
  const source = readPageSource();
  assert.match(source, /DRAFT_SAVE_DEBOUNCE_MS = 500/);
  assert.match(source, /saveEditorDraft\(storage, \{/);
  assert.match(source, /clearEditorDraft\(getSessionStorage\(\)\)/);
  // 导出成功回调清除草稿并复位未保存标记（beforeunload 随之豁免）。
  assert.match(source, /dirtyRef\.current = false;/);
  assert.doesNotMatch(source, /exportExemptRef/);
  // 更换照片两步确认（无浏览器原生确认弹窗）。
  assert.match(source, /CHANGE_PHOTO_ARMED_MS = 5000/);
  assert.match(source, /确认更换（丢弃 \$\{frames\.length\} 框与 \$\{placements\.length\} 处贴合）/);
  assert.doesNotMatch(source, /window\.confirm/);
  assert.doesNotMatch(source, /window\.alert/);
});

test("editor page registers a beforeunload guard for unexported edits", () => {
  const source = readPageSource();
  assert.match(source, /window\.addEventListener\("beforeunload", handler\)/);
  assert.match(source, /if \(!dirtyRef\.current\) return;/);
  assert.match(source, /event\.returnValue = ""/);
  // 守卫条件：贴合非空或手动框非空。
  assert.match(source, /item\.id\.startsWith\(MANUAL_FRAME_ID_PREFIX\)/);
});

test("editor page keeps the draft key contract", () => {
  const source = readFileSync(
    new URL("../src/lib/editor-draft.ts", import.meta.url),
    "utf8"
  );
  assert.match(source, /EDITOR_DRAFT_STORAGE_KEY = "jiaru-editor-draft-v1"/);
});
