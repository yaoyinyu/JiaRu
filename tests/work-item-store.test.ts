import assert from "node:assert/strict";
import test from "node:test";

import {
  createWorkItem,
  deleteWorkItem,
  getWorkItem,
  listWorkItems,
  migrateCollectsToWorkItems,
  saveWorkItem,
  setWorkItemStoreForTests,
  WorkItemUnavailableError,
  type GalleryCollectRecordLike,
  type WorkItem,
  type WorkItemStore,
} from "../src/lib/work-items.ts";

const jpegBlob = () => new Blob([new Uint8Array([0xff, 0xd8, 0xff, 0xe0])], { type: "image/jpeg" });

/** 基于内存 Map 的最小 store 实现。 */
function createMemoryStore(): WorkItemStore & { items: Map<string, WorkItem> } {
  const items = new Map<string, WorkItem>();
  return {
    items,
    put: async (item) => {
      items.set(item.id, item);
    },
    get: async (id) => items.get(id) ?? null,
    getAll: async () => [...items.values()],
    delete: async (id) => {
      items.delete(id);
    },
  };
}

test("createWorkItem 固定 local-only 并生成 id/时间", () => {
  const item = createWorkItem({ type: "ai-result", title: "测试", previewBlob: jpegBlob() });
  assert.equal(item.storageStatus, "local-only");
  assert.ok(item.id.length > 0);
  assert.equal(item.createdAt, item.updatedAt);
  assert.deepEqual(item.source, {});
});

test("saveWorkItem 写入并回读，listWorkItems 按更新时间降序", async () => {
  const store = createMemoryStore();
  const first = createWorkItem({ type: "ai-result", title: "旧", previewBlob: jpegBlob(), createdAt: 1000 });
  const second = createWorkItem({ type: "ar-config", title: "新", previewBlob: jpegBlob(), createdAt: 2000 });
  await saveWorkItem(first, store);
  await saveWorkItem(second, store);
  const listed = await listWorkItems(store);
  assert.deepEqual(listed.map((item) => item.title), ["新", "旧"]);
  const fetched = await getWorkItem(first.id, store);
  assert.equal(fetched?.title, "旧");
});

test("deleteWorkItem 正确委托", async () => {
  const store = createMemoryStore();
  const item = createWorkItem({ type: "editor-result", title: "x", previewBlob: jpegBlob() });
  await saveWorkItem(item, store);
  await deleteWorkItem(item.id, store);
  assert.equal(store.items.size, 0);
  assert.equal(await getWorkItem(item.id, store), null);
});

test("无 IndexedDB 环境写入路径真实失败，读取路径降级为空", async () => {
  setWorkItemStoreForTests(null);
  const item = createWorkItem({ type: "ai-result", title: "x", previewBlob: jpegBlob() });
  await assert.rejects(() => saveWorkItem(item), WorkItemUnavailableError);
  await assert.rejects(() => deleteWorkItem(item.id), WorkItemUnavailableError);
  assert.deepEqual(await listWorkItems(), []);
  assert.equal(await getWorkItem(item.id), null);
});

test("saveWorkItem 回读不到视为失败", async () => {
  const ghost: WorkItemStore = {
    put: async () => {},
    get: async () => null,
    getAll: async () => [],
    delete: async () => {},
  };
  const item = createWorkItem({ type: "ai-result", title: "x", previewBlob: jpegBlob() });
  await assert.rejects(() => saveWorkItem(item, ghost), /验证失败/);
});

test("migrateCollectsToWorkItems 迁移旧收录且幂等，不删除旧库语义由调用方保证", async () => {
  const store = createMemoryStore();
  const collects: GalleryCollectRecordLike[] = [
    {
      id: "collect-1",
      blob: jpegBlob(),
      createdAt: 500,
      source: { engine: "agnes", prompt: "银色亮片" },
    },
    {
      id: "collect-2",
      blob: jpegBlob(),
      createdAt: 600,
      source: { engine: "seedream-pro", prompt: "" },
    },
  ];
  const first = await migrateCollectsToWorkItems(collects, store);
  assert.equal(first, 2);
  const again = await migrateCollectsToWorkItems(collects, store);
  assert.equal(again, 0);
  const items = await listWorkItems(store);
  assert.deepEqual(items.map((item) => item.type), ["ai-result", "ai-result"]);
  const migrated = await getWorkItem("collect-1", store);
  assert.equal(migrated?.source.collectId, "collect-1");
  assert.equal(migrated?.metadata.migratedFrom, "jiaru-gallery/collects");
  assert.match(migrated?.title ?? "", /银色亮片/);
  assert.equal(migrated?.createdAt, 500);
});
