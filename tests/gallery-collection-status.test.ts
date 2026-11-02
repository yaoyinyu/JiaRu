import assert from "node:assert/strict";
import test from "node:test";

import {
  addCollect,
  clearCollects,
  collectErrorToMessage,
  collectUnavailableMessage,
  deleteCollect,
  probeCollectStorage,
  setCollectStoreForTests,
  CollectUnavailableError,
  type GalleryCollectRecord,
  type GalleryCollectStore,
} from "../src/lib/gallery-collection.ts";

const jpegBlob = () => new Blob([new Uint8Array([0xff, 0xd8, 0xff, 0xe0])], { type: "image/jpeg" });

/** 基于内存 Map 的最小 store 实现。 */
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

test("addCollect 在无 IndexedDB 环境真实失败（不静默 no-op）", async () => {
  setCollectStoreForTests(null);
  await assert.rejects(
    () => addCollect(jpegBlob(), { engine: "agnes", prompt: "x" }),
    (err: unknown) => {
      assert.ok(err instanceof CollectUnavailableError);
      assert.equal(err.reason, "indexed_db_missing");
      assert.match(err.message, /不支持本地收藏/);
      return true;
    }
  );
});

test("deleteCollect / clearCollects 在无 IndexedDB 环境真实失败", async () => {
  setCollectStoreForTests(null);
  await assert.rejects(() => deleteCollect("any"), CollectUnavailableError);
  await assert.rejects(() => clearCollects(), CollectUnavailableError);
});

test("addCollect 写入后回读不到视为失败", async () => {
  const ghostStore: GalleryCollectStore = {
    put: async () => {},
    get: async () => null,
    getAll: async () => [],
    delete: async () => {},
    clear: async () => {},
  };
  await assert.rejects(
    () => addCollect(jpegBlob(), { engine: "agnes", prompt: "x" }, ghostStore),
    (err: unknown) => {
      assert.ok(err instanceof CollectUnavailableError);
      assert.equal(err.reason, "unknown");
      assert.match(err.message, /写入验证失败/);
      return true;
    }
  );
});

test("addCollect 注入 store 时写入并回读成功", async () => {
  const store = createMemoryStore();
  const record = await addCollect(jpegBlob(), { engine: "agnes", prompt: "ok" }, store);
  assert.equal(store.items.size, 1);
  assert.equal((await store.get(record.id))?.source.prompt, "ok");
});

test("probeCollectStorage 在无 IndexedDB 环境返回 unavailable，注入 store 时返回 available", async () => {
  setCollectStoreForTests(null);
  assert.equal(await probeCollectStorage(), "unavailable");
  setCollectStoreForTests(createMemoryStore());
  assert.equal(await probeCollectStorage(), "available");
  setCollectStoreForTests(null);
  assert.equal(await probeCollectStorage(), "unavailable");
});

test("collectUnavailableMessage 覆盖全部原因分类", () => {
  assert.equal(collectUnavailableMessage("indexed_db_missing"), "当前浏览器不支持本地收藏");
  assert.match(collectUnavailableMessage("indexed_db_open_failed"), /无法打开/);
  assert.match(collectUnavailableMessage("storage_denied"), /站点权限/);
  assert.match(collectUnavailableMessage("quota_exceeded"), /空间不足/);
  assert.match(collectUnavailableMessage("unknown"), /收录失败/);
});

test("collectErrorToMessage 分类 CollectUnavailableError 与常见浏览器存储错误", () => {
  assert.equal(
    collectErrorToMessage(new CollectUnavailableError("quota_exceeded")),
    "本地存储空间不足，请删除部分收录"
  );
  const quota = Object.assign(new Error("quota"), { name: "QuotaExceededError" });
  assert.match(collectErrorToMessage(quota), /空间不足/);
  const denied = Object.assign(new Error("denied"), { name: "SecurityError" });
  assert.match(collectErrorToMessage(denied), /站点权限/);
  assert.equal(collectErrorToMessage(new Error("mystery")), "收录失败，请重试");
  assert.equal(collectErrorToMessage(undefined), "收录失败，请重试");
});
