import assert from "node:assert/strict";
import test from "node:test";

import {
  loadWorkItemReference,
  resolveWorkRef,
} from "../src/lib/work-bridge.ts";
import {
  createWorkItem,
  saveWorkItem,
  setWorkItemStoreForTests,
  type WorkItemStore,
} from "../src/lib/work-items.ts";

test("resolveWorkRef 按优先级 work > gallery > collect > preset", () => {
  assert.deepEqual(resolveWorkRef({ work: "w1" }), { kind: "work", id: "w1" });
  assert.deepEqual(resolveWorkRef({ gallery: "g1" }), { kind: "gallery", id: "g1" });
  assert.deepEqual(resolveWorkRef({ collect: "c1" }), { kind: "collect", id: "c1" });
  assert.deepEqual(resolveWorkRef({ preset: "p1" }), { kind: "preset", id: "p1" });
  assert.deepEqual(
    resolveWorkRef({ work: "w1", gallery: "g1", collect: "c1", preset: "p1" }),
    { kind: "work", id: "w1" }
  );
  assert.deepEqual(resolveWorkRef({ gallery: "g1", preset: "p1" }), { kind: "gallery", id: "g1" });
  assert.equal(resolveWorkRef({}), null);
  assert.equal(resolveWorkRef({ work: null, gallery: "", collect: undefined }), null);
});

test("loadWorkItemReference 读取作品转 File，缺失/失败静默降级为 null", async () => {
  const memory: WorkItemStore = {
    put: async (item) => {
      memoryItems.set(item.id, item);
    },
    get: async (id) => memoryItems.get(id) ?? null,
    getAll: async () => [...memoryItems.values()],
    delete: async (id) => {
      memoryItems.delete(id);
    },
  };
  const memoryItems = new Map<string, Awaited<ReturnType<typeof saveWorkItem>>>();
  setWorkItemStoreForTests(memory);
  const item = createWorkItem({
    type: "ai-result",
    title: "银色亮片",
    previewBlob: new Blob([new Uint8Array([0xff, 0xd8])], { type: "image/jpeg" }),
    source: { engine: "agnes", prompt: "银色亮片" },
  });
  await saveWorkItem(item, memory);

  const file = await loadWorkItemReference(item.id);
  assert.ok(file instanceof File);
  assert.equal(file?.type, "image/jpeg");
  assert.match(file?.name ?? "", /^jiaru-work-.+\.jpg$/);

  setWorkItemStoreForTests(null);
  // 无 IndexedDB 环境（node）：读取路径降级返回 null，不抛错。
  assert.equal(await loadWorkItemReference("missing"), null);
});
