/**
 * 本地 WorkItem 作品模型（方案 §9）：把分散的 gallery / collect / preset
 * 跨页参数升级为统一的本地作品对象。
 *
 * 边界（方案 §9.6，不得越界宣传）：
 * - 仅保存在当前浏览器（IndexedDB 库名 jiaru-works，store works）；
 * - 与旧「我的收录」库 jiaru-gallery 并存；迁移只读取旧库，不删除旧库；
 * - UI 不得显示「云端已保存 / 已跨设备同步 / 已发布」。
 *
 * 写入路径在存储不可用时抛错（与 gallery-collection 同一教训：不静默假成功）；
 * 读取路径降级为空列表。
 */

export type WorkItemType = "ai-result" | "editor-result" | "ar-config";

export type WorkItemSource = {
  engine?: string;
  prompt?: string;
  textureSetId?: string;
  galleryId?: string;
  collectId?: string;
};

export type WorkItem = {
  id: string;
  type: WorkItemType;
  title: string;
  previewBlob: Blob;
  createdAt: number;
  updatedAt: number;
  storageStatus: "local-only";
  source: WorkItemSource;
  metadata: Record<string, unknown>;
};

export interface WorkItemStore {
  put(item: WorkItem): Promise<void>;
  get(id: string): Promise<WorkItem | null>;
  getAll(): Promise<WorkItem[]>;
  delete(id: string): Promise<void>;
}

/** 存储不可用/写入验证失败时抛出；message 已是可直接展示的用户文案。 */
export class WorkItemUnavailableError extends Error {
  constructor(message = "本地作品存储暂不可用，请重试") {
    super(message);
    this.name = "WorkItemUnavailableError";
  }
}

const DB_NAME = "jiaru-works";
const DB_VERSION = 1;
const STORE_NAME = "works";

/** SSR / 无 IndexedDB 环境的安全降级（仅用于读取路径）。 */
function createNoopWorkItemStore(): WorkItemStore {
  return {
    put: async () => {},
    get: async () => null,
    getAll: async () => [],
    delete: async () => {},
  };
}

/** 原生 IndexedDB 适配层；环境不支持时返回 null。 */
export function createIndexedDbWorkItemStore(
  factory: IDBFactory | undefined =
    typeof indexedDB === "undefined" ? undefined : indexedDB
): WorkItemStore | null {
  if (!factory) return null;
  const idbFactory: IDBFactory = factory;

  async function withStore<T>(
    mode: IDBTransactionMode,
    run: (store: IDBObjectStore) => IDBRequest<T> | void
  ): Promise<T> {
    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      const open = idbFactory.open(DB_NAME, DB_VERSION);
      open.onupgradeneeded = () => {
        const db = open.result;
        if (!db.objectStoreNames.contains(STORE_NAME)) {
          db.createObjectStore(STORE_NAME, { keyPath: "id" });
        }
      };
      open.onsuccess = () => resolve(open.result);
      open.onerror = () => reject(open.error ?? new Error("IndexedDB 打开失败"));
      open.onblocked = () => reject(new Error("IndexedDB 被其他连接阻塞"));
    });
    try {
      return await new Promise<T>((resolve, reject) => {
        const tx = db.transaction(STORE_NAME, mode);
        const store = tx.objectStore(STORE_NAME);
        const request = run(store);
        let result: T | undefined;
        if (request) {
          request.onsuccess = () => {
            result = request.result;
          };
          request.onerror = () => reject(request.error ?? new Error("IndexedDB 操作失败"));
        }
        tx.oncomplete = () => resolve(result as T);
        tx.onerror = () => reject(tx.error ?? new Error("IndexedDB 事务失败"));
        tx.onabort = () => reject(tx.error ?? new Error("IndexedDB 事务中止"));
      });
    } finally {
      db.close();
    }
  }

  return {
    async put(item) {
      await withStore<void>("readwrite", (store) => {
        store.put(item);
      });
    },
    async get(id) {
      const item = await withStore<WorkItem | undefined>(
        "readonly",
        (store) => store.get(id) as IDBRequest<WorkItem | undefined>
      );
      return item ?? null;
    },
    async getAll() {
      const items = await withStore<WorkItem[]>(
        "readonly",
        (store) => store.getAll() as IDBRequest<WorkItem[]>
      );
      return items ?? [];
    },
    async delete(id) {
      await withStore<void>("readwrite", (store) => {
        store.delete(id);
      });
    },
  };
}

let storeOverride: WorkItemStore | null | undefined;

/** 测试专用：注入/清除（传 null）store 覆盖。 */
export function setWorkItemStoreForTests(store: WorkItemStore | null): void {
  storeOverride = store;
}

/** 写入路径解析：显式传入 > 测试注入 > 原生 IndexedDB；不可用即抛错。 */
function resolveWriteStore(store?: WorkItemStore): WorkItemStore {
  if (store) return store;
  if (storeOverride) return storeOverride;
  const created = createIndexedDbWorkItemStore();
  if (!created) {
    throw new WorkItemUnavailableError("当前浏览器不支持本地作品存储");
  }
  return created;
}

/** 生成作品 id；crypto.randomUUID 不可用时退化为时间戳 + 随机数。 */
function createWorkItemId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `work-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

/** 创建一条本地作品（storageStatus 固定 local-only，时间由本模块统一生成）。 */
export function createWorkItem(input: {
  type: WorkItemType;
  title: string;
  previewBlob: Blob;
  source?: WorkItemSource;
  metadata?: Record<string, unknown>;
  id?: string;
  createdAt?: number;
}): WorkItem {
  const now = input.createdAt ?? Date.now();
  return {
    id: input.id ?? createWorkItemId(),
    type: input.type,
    title: input.title,
    previewBlob: input.previewBlob,
    createdAt: now,
    updatedAt: now,
    storageStatus: "local-only",
    source: { ...input.source },
    metadata: { ...input.metadata },
  };
}

/** 保存作品：写入后回读验证，回读不到视为失败。 */
export async function saveWorkItem(
  item: WorkItem,
  store?: WorkItemStore
): Promise<WorkItem> {
  const target = resolveWriteStore(store);
  await target.put(item);
  const verified = await target.get(item.id);
  if (!verified) {
    throw new WorkItemUnavailableError("作品保存验证失败，请重试");
  }
  return verified;
}

/** 按 id 读取作品；读取路径无存储时返回 null。 */
export async function getWorkItem(
  id: string,
  store: WorkItemStore = storeOverride ?? createIndexedDbWorkItemStore() ?? createNoopWorkItemStore()
): Promise<WorkItem | null> {
  return store.get(id);
}

/** 列出全部作品，按更新时间降序（最新在前）。 */
export async function listWorkItems(
  store: WorkItemStore = storeOverride ?? createIndexedDbWorkItemStore() ?? createNoopWorkItemStore()
): Promise<WorkItem[]> {
  const items = await store.getAll();
  return [...items].sort((a, b) => b.updatedAt - a.updatedAt);
}

/** 删除单条作品。存储不可用时抛错。 */
export async function deleteWorkItem(id: string, store?: WorkItemStore): Promise<void> {
  await resolveWriteStore(store).delete(id);
}

/**
 * 迁移输入：旧收录记录的最小结构（与 gallery-collection 的 GalleryCollectRecord
 * 结构一致，但不在本模块 import 旧库，保持存储层解耦）。
 */
export type GalleryCollectRecordLike = {
  id: string;
  blob: Blob;
  createdAt: number;
  source: { engine: string; prompt: string };
};

/**
 * 把旧「我的收录」（jiaru-gallery / collects）迁移为 ai-result 类型 WorkItem。
 * - 幂等：已存在同 id 的作品跳过；
 * - 只读旧库，不删除旧库（方案 §9.3：旧库保留到迁移验证完成）；
 * - 存储不可用时抛错，由调用方决定重试时机。
 * 返回本次实际迁移的条数。
 */
export async function migrateCollectsToWorkItems(
  collects: readonly GalleryCollectRecordLike[],
  store?: WorkItemStore
): Promise<number> {
  const target = resolveWriteStore(store);
  let migrated = 0;
  for (const record of collects) {
    const existing = await target.get(record.id);
    if (existing) continue;
    const item = createWorkItem({
      id: record.id,
      type: "ai-result",
      title: record.source.prompt
        ? record.source.prompt.slice(0, 40)
        : "AI 生成结果",
      previewBlob: record.blob,
      source: {
        engine: record.source.engine,
        prompt: record.source.prompt,
        collectId: record.id,
      },
      metadata: { migratedFrom: "jiaru-gallery/collects", collectedAt: record.createdAt },
      createdAt: record.createdAt,
    });
    await target.put(item);
    migrated += 1;
  }
  return migrated;
}
