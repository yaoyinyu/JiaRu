import assert from "node:assert/strict";
import test from "node:test";

import {
  addCollect,
  clearCollects,
  createIndexedDbCollectStore,
  deleteCollect,
  listCollects,
  setCollectStoreForTests,
  type GalleryCollectRecord,
  type GalleryCollectStore,
} from "../src/lib/gallery-collection.ts";

const jpegBlob = () => new Blob([new Uint8Array([0xff, 0xd8, 0xff, 0xe0])], { type: "image/jpeg" });

/** 基于内存 Map 的最小 store 实现，用于业务逻辑单测。 */
function createMemoryStore(): GalleryCollectStore & { items: Map<string, GalleryCollectRecord> } {
  const items = new Map<string, GalleryCollectRecord>();
  return {
    items,
    put: async (record) => {
      items.set(record.id, record);
    },
    get: async (id) => items.get(id) ?? null,
    getAll: async () => [...items.values()],
    delete: async (id) => {
      items.delete(id);
    },
    clear: async () => {
      items.clear();
    },
  };
}

test("addCollect 生成完整记录并写入 store", async () => {
  const store = createMemoryStore();
  const record = await addCollect(jpegBlob(), { engine: "agnes", prompt: "银色亮片" }, store);
  assert.ok(record.id.length > 0);
  assert.ok(Number.isFinite(record.createdAt));
  assert.equal(record.source.engine, "agnes");
  assert.equal(record.source.prompt, "银色亮片");
  assert.equal(store.items.size, 1);
  assert.ok(store.items.get(record.id));
});

test("addCollect 的 source 是快照而非引用", async () => {
  const store = createMemoryStore();
  const source = { engine: "agnes", prompt: "原始" };
  await addCollect(jpegBlob(), source, store);
  source.prompt = "外部篡改";
  const [record] = await listCollects(store);
  assert.equal(record.source.prompt, "原始");
});

test("listCollects 按创建时间降序排列", async () => {
  const store = createMemoryStore();
  await addCollect(jpegBlob(), { engine: "agnes", prompt: "a" }, store);
  await new Promise((resolve) => setTimeout(resolve, 5));
  await addCollect(jpegBlob(), { engine: "agnes", prompt: "b" }, store);
  await new Promise((resolve) => setTimeout(resolve, 5));
  await addCollect(jpegBlob(), { engine: "agnes", prompt: "c" }, store);
  const records = await listCollects(store);
  assert.deepEqual(records.map((r) => r.source.prompt), ["c", "b", "a"]);
});

test("deleteCollect 与 clearCollects 正确委托", async () => {
  const store = createMemoryStore();
  const first = await addCollect(jpegBlob(), { engine: "agnes", prompt: "a" }, store);
  await addCollect(jpegBlob(), { engine: "agnes", prompt: "b" }, store);
  await deleteCollect(first.id, store);
  assert.equal(store.items.size, 1);
  await clearCollects(store);
  assert.equal(store.items.size, 0);
  assert.deepEqual(await listCollects(store), []);
});

test("createIndexedDbCollectStore 在无 indexedDB 环境返回 null", () => {
  // node:test 进程没有全局 indexedDB，若未来 Node 提供则该用例需调整。
  assert.equal(typeof globalThis.indexedDB, "undefined");
  assert.equal(createIndexedDbCollectStore(undefined), null);
});

test("默认 getCollectStore 在无 indexedDB 环境降级为 no-op", async () => {
  setCollectStoreForTests(null);
  const { getCollectStore } = await import("../src/lib/gallery-collection.ts");
  const store = getCollectStore();
  assert.deepEqual(await store.getAll(), []);
  assert.equal(await store.get("any"), null);
  await store.put({ id: "x", blob: jpegBlob(), createdAt: 0, source: { engine: "agnes", prompt: "" } });
  await store.delete("x");
  await store.clear();
  assert.deepEqual(await store.getAll(), []);
  setCollectStoreForTests(null);
});

test("store 抛错时公开 API 原样传递异常（由调用方决定降级）", async () => {
  const failing: GalleryCollectStore = {
    put: async () => {
      throw new Error("quota exceeded");
    },
    get: async () => null,
    getAll: async () => {
      throw new Error("closed");
    },
    delete: async () => {},
    clear: async () => {},
  };
  await assert.rejects(
    () => addCollect(jpegBlob(), { engine: "agnes", prompt: "" }, failing),
    /quota exceeded/
  );
  await assert.rejects(() => listCollects(failing), /closed/);
});
