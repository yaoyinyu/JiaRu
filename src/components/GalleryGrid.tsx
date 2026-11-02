"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { GALLERY_IMAGES } from "@/lib/utils";
import Link from "next/link";
import Image from "next/image";
import { Icon } from "@/components/Icon";
import { AppDialog } from "@/components/ui/AppDialog";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { StatusRegion } from "@/components/ui/StatusRegion";
import {
  clearCollects,
  collectErrorToMessage,
  deleteCollect,
  listCollects,
  probeCollectStorage,
} from "@/lib/gallery-collection";
import type { GalleryCollectRecord } from "@/lib/gallery-collection";
import { migrateCollectsToWorkItems } from "@/lib/work-items";

/** 收录卡片的视图状态：blob 的 objectURL 与记录绑定，便于释放。 */
type CollectView = { record: GalleryCollectRecord; url: string };

/** 「我的收录」区块状态模型（方案 §4.3）：各状态可区分、可读屏感知。 */
type CollectSectionState =
  | "checking"
  | "available"
  | "empty"
  | "load_error"
  | "unavailable";

/** 单条删除的 5 秒撤销窗口；窗口结束后才真正写库删除。 */
const DELETE_UNDO_MS = 5000;

/** 收录时间格式化（仅客户端渲染，无水合风险）。 */
function formatCollectTime(timestamp: number): string {
  const date = new Date(timestamp);
  return `${date.getMonth() + 1}月${date.getDate()}日 ${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

export function GalleryGrid() {
  // 点心仪款式后先选择试戴方式（2026-11-03 用户指示）：静态试色（上传手部
  // 照片自动贴合）或 AR 实时预览；底部出口按钮保持直达。
  const [chooser, setChooser] = useState<{ id: string; name: string } | null>(null);
  return (
    <>
      <div className="grid grid-cols-2 gap-3 sm:gap-5 md:grid-cols-3 wl:grid-cols-4">
        {GALLERY_IMAGES.map((item, index) => (
          <div
            key={item.id}
            className="group overflow-hidden rounded-[20px] bg-[var(--surface)] shadow-[var(--neu-out-sm)] transition duration-300 hover:shadow-[var(--neu-out-hover)]"
          >
            <button
              type="button"
              onClick={() => setChooser({ id: String(item.id), name: item.name })}
              aria-label={`选择「${item.name}」的试戴方式（静态试色或 AR 实时预览）`}
              className="relative block aspect-square overflow-hidden bg-[var(--sage)]"
            >
              <Image src={item.src} alt={item.name} width={360} height={360} className="h-full w-full object-cover transition duration-500 group-hover:opacity-90" />
              <span className="absolute left-2.5 top-2.5 rounded-full bg-[var(--surface)] px-2.5 py-1 font-[var(--serif)] text-[12px] tracking-[.16em] text-[#6f7066] shadow-[var(--neu-out-sm)]">LOOK {String(index + 1).padStart(2, "0")}</span>
            </button>
            <div className="p-3 sm:p-4">
              <button
                type="button"
                onClick={() => setChooser({ id: String(item.id), name: item.name })}
                className="block w-full truncate text-left font-[var(--serif)] text-[14.5px] font-medium text-[var(--ink)] transition-colors hover:text-[var(--coral-deep)]"
              >
                {item.name}
              </button>
              <div className="mt-2.5 flex flex-wrap gap-2">
                <Link href={`/editor?gallery=${item.id}`} aria-label={`为「${item.name}」试色`} className="inline-flex min-h-11 items-center gap-1.5 rounded-full bg-[var(--coral-soft)] px-3 text-xs font-medium text-[var(--coral-deep)] transition hover:shadow-[var(--neu-out-sm)]">
                  <Icon name="palette" className="h-4 w-4" />
                  试色
                </Link>
                <Link href={`/ai-generate?gallery=${item.id}`} aria-label={`为「${item.name}」生成 AI 相似款`} className="inline-flex min-h-11 items-center gap-1.5 rounded-full bg-[var(--sage)] px-3 text-xs font-medium text-[#5c6752] transition hover:shadow-[var(--neu-out-sm)]">
                  <Icon name="sparkles" className="h-4 w-4" />
                  AI 相似款
                </Link>
                <Link href={`/ar-tryon?gallery=${item.id}`} aria-label={`AR 试戴「${item.name}」（需要摄像头权限）`} title="AR 试戴需要摄像头权限" className="inline-flex min-h-11 items-center gap-1.5 rounded-full bg-[var(--surface)] px-3 text-xs font-medium text-[var(--muted)] shadow-[var(--neu-out-sm)] transition hover:text-[var(--coral-deep)] hover:shadow-[var(--neu-out-hover)]">
                  <Icon name="camera" className="h-4 w-4" />
                  AR 试戴
                </Link>
              </div>
            </div>
          </div>
        ))}
      </div>
      <AppDialog
        open={chooser !== null}
        onClose={() => setChooser(null)}
        title={chooser ? `选择「${chooser.name}」的试戴方式` : "选择试戴方式"}
        description="两种效果都基于这张灵感款式；静态试色会把相近纹理自动贴合到你上传的手部照片上。"
      >
        <div className="grid gap-2">
          <Link
            href={chooser ? `/editor?gallery=${chooser.id}` : "#"}
            className="flex min-h-11 flex-col justify-center rounded-2xl border border-[var(--line)] bg-[var(--surface)] px-4 py-3 transition hover:border-pink-200 hover:shadow-[var(--neu-out-sm)]"
          >
            <span className="text-sm font-medium text-[var(--ink)]">上传手部照片 · 静态试色</span>
            <span className="mt-0.5 text-xs leading-5 text-[#67685f]">自动定位甲面并贴合相近纹理套装，可逐指调整</span>
          </Link>
          <Link
            href={chooser ? `/ar-tryon?gallery=${chooser.id}` : "#"}
            className="flex min-h-11 flex-col justify-center rounded-2xl border border-[var(--line)] bg-[var(--surface)] px-4 py-3 transition hover:border-pink-200 hover:shadow-[var(--neu-out-sm)]"
          >
            <span className="text-sm font-medium text-[var(--ink)]">开启摄像头 · AR 实时预览</span>
            <span className="mt-0.5 text-xs leading-5 text-[#67685f]">从该款提取纹理并实时试戴（需要摄像头权限）</span>
          </Link>
        </div>
      </AppDialog>
      <CollectsSection />
    </>
  );
}

/** 「我的收录」区块：状态模型驱动，空态/加载态/失败态/不可用均可区分。 */
function CollectsSection() {
  const [collects, setCollects] = useState<CollectView[]>([]);
  const [sectionState, setSectionState] = useState<CollectSectionState>("checking");
  const [confirmClear, setConfirmClear] = useState(false);
  const [feedback, setFeedback] = useState<{ status: "success" | "error"; message: string } | null>(null);
  // 待撤销删除：窗口期内保留记录与 objectURL，超时才真正写库删除。
  const [undoableDelete, setUndoableDelete] = useState<{ view: CollectView; timer: ReturnType<typeof setTimeout> } | null>(null);
  const urlsRef = useRef<string[]>([]);
  // WorkItem 迁移每次会话只尝试一次（迁移本身幂等，避免每次刷新重复写）。
  const migratedOnceRef = useRef(false);

  const revokeAndForget = useCallback((url: string) => {
    URL.revokeObjectURL(url);
    urlsRef.current = urlsRef.current.filter((item) => item !== url);
  }, []);

  const refresh = useCallback(async () => {
    try {
      const storage = await probeCollectStorage();
      if (storage === "unavailable") {
        setSectionState("unavailable");
        return;
      }
      // checking 标记放在首个 await 之后：effect 挂载路径不得同步 setState。
      setSectionState("checking");
      const records = await listCollects();
      // 旧收录一次性迁移为 WorkItem（方案 §9.3）：幂等、不删除旧库；
      // 失败静默不阻塞图库展示，下次挂载自动重试。
      if (!migratedOnceRef.current) {
        migratedOnceRef.current = true;
        try {
          await migrateCollectsToWorkItems(records);
        } catch {
          // 迁移失败保持旧收录可用；WorkItem 可在后续访问补建。
        }
      }
      const views = records.map((record) => {
        const url = URL.createObjectURL(record.blob);
        urlsRef.current.push(url);
        return { record, url };
      });
      setCollects(views);
      setSectionState(views.length > 0 ? "available" : "empty");
    } catch {
      setCollects([]);
      setSectionState("load_error");
    }
  }, []);

  useEffect(() => {
    // 经微任务挂载：refresh 内含 setState，effect 同步路径不直接调用。
    queueMicrotask(() => void refresh());
    return () => {
      for (const url of urlsRef.current) URL.revokeObjectURL(url);
      urlsRef.current = [];
    };
  }, [refresh]);

  // 卸载/刷新时立即执行未过撤销期的真实删除（方案 §3.2 撤销策略）。
  useEffect(() => {
    return () => {
      if (undoableDelete) {
        clearTimeout(undoableDelete.timer);
        void deleteCollect(undoableDelete.view.record.id).catch(() => {});
      }
    };
    // 仅卸载时执行；undoableDelete 变化不重启清理。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /** 撤销期结束：真正删除；失败则恢复卡片并提示。 */
  const finalizeDelete = useCallback(
    async (view: CollectView) => {
      try {
        await deleteCollect(view.record.id);
        revokeAndForget(view.url);
      } catch (err) {
        setCollects((current) =>
          [...current, view].sort((a, b) => b.record.createdAt - a.record.createdAt)
        );
        setFeedback({ status: "error", message: collectErrorToMessage(err) });
      }
    },
    [revokeAndForget]
  );

  const handleDelete = (id: string) => {
    const view = collects.find((item) => item.record.id === id);
    if (!view) return;
    // 同一时间只保留一个待撤销删除：新删除先落定上一个。
    if (undoableDelete) {
      clearTimeout(undoableDelete.timer);
      const previous = undoableDelete;
      setUndoableDelete(null);
      void finalizeDelete(previous.view);
    }
    setCollects((current) => current.filter((item) => item.record.id !== id));
    const timer = setTimeout(() => {
      setUndoableDelete((current) => (current?.view.record.id === id ? null : current));
      void finalizeDelete(view);
    }, DELETE_UNDO_MS);
    setUndoableDelete({ view, timer });
    setFeedback(null);
  };

  const undoDelete = () => {
    if (!undoableDelete) return;
    clearTimeout(undoableDelete.timer);
    const view = undoableDelete.view;
    setUndoableDelete(null);
    setCollects((current) =>
      [...current, view].sort((a, b) => b.record.createdAt - a.record.createdAt)
    );
  };

  const handleConfirmClearAll = async () => {
    setConfirmClear(false);
    // 清空会移除所有卡片：先落定待撤销删除，避免撤销恢复出已清空的记录。
    if (undoableDelete) {
      clearTimeout(undoableDelete.timer);
      setUndoableDelete(null);
    }
    try {
      await clearCollects();
      for (const url of urlsRef.current) URL.revokeObjectURL(url);
      urlsRef.current = [];
      setCollects([]);
      setSectionState("empty");
      setFeedback({ status: "success", message: "已清空全部收录。" });
    } catch (err) {
      setFeedback({ status: "error", message: collectErrorToMessage(err) });
    }
  };

  const sectionHeader = (
    <div className="mb-4 flex items-center justify-between">
      <p className="flex items-center gap-2 font-[var(--serif)] text-[14.5px] font-medium text-[var(--ink)]">
        <Icon name="sparkles" className="h-4 w-4 text-[var(--coral)]" />
        我的收录
        {sectionState === "available" && (
          <span className="rounded-full bg-[var(--coral-soft)] px-2 py-0.5 text-[12px] font-medium text-[var(--coral-deep)]">{collects.length}</span>
        )}
      </p>
      {sectionState === "available" && collects.length > 0 && (
        <button onClick={() => setConfirmClear(true)} className="min-h-11 px-1 text-[11px] text-[var(--muted)] transition hover:text-[var(--coral-deep)]">
          清空全部
        </button>
      )}
    </div>
  );

  const stateMessage: Partial<Record<CollectSectionState, string>> = {
    checking: "正在读取本机收录…",
    empty: "还没有收录。生成结果可一键收录到这里。",
    load_error: "本机收录暂时无法读取。",
    unavailable: "当前浏览器不支持本地收录",
  };

  return (
    <div className="mt-8 border-t border-[var(--line)] pt-6">
      {sectionHeader}

      {sectionState === "available" ? (
        <div className="grid grid-cols-2 gap-3 sm:gap-5 md:grid-cols-3 wl:grid-cols-4">
          {collects.map(({ record, url }) => (
            <div
              key={record.id}
              className="group overflow-hidden rounded-[20px] bg-[var(--surface)] shadow-[var(--neu-out-sm)] transition duration-300 hover:shadow-[var(--neu-out-hover)]"
            >
              <div className="relative aspect-square overflow-hidden bg-[var(--sage)]">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={url} alt="我的收录" className="h-full w-full object-cover transition duration-500 group-hover:opacity-90" />
                <span className="absolute left-2.5 top-2.5 rounded-full bg-[var(--surface)] px-2.5 py-1 text-[12px] tracking-[.1em] text-[#6f7066] shadow-[var(--neu-out-sm)]">我的收录</span>
              </div>
              <div className="p-3 sm:p-4">
                <div className="flex items-center justify-between gap-2">
                  <p className="min-w-0 truncate text-[11px] text-[var(--muted)]">
                    {formatCollectTime(record.createdAt)}
                    {record.source.engine ? ` · ${record.source.engine}` : ""}
                  </p>
                  <button
                    onClick={() => handleDelete(record.id)}
                    aria-label="删除这条收录（5 秒内可撤销）"
                    className="grid h-7 w-7 shrink-0 place-items-center rounded-full text-[#b6b3a5] transition hover:bg-[var(--coral-soft)] hover:text-[var(--coral-deep)]"
                  >
                    <Icon name="trash" className="h-3.5 w-3.5" />
                  </button>
                </div>
                <div className="mt-2.5 grid grid-cols-2 gap-2">
                  <Link href={`/ai-generate?collect=${record.id}`} aria-label="为这条收录生成 AI 相似款" className="grid h-11 place-items-center rounded-full bg-[var(--sage)] text-[#5c6752] transition hover:shadow-[var(--neu-out-sm)]">
                    <Icon name="sparkles" className="h-[18px] w-[18px]" />
                  </Link>
                  <Link href={`/ar-tryon?collect=${record.id}`} aria-label="AR 试戴这条收录（需要摄像头权限）" className="grid h-11 place-items-center rounded-full bg-[var(--surface)] text-[var(--muted)] shadow-[var(--neu-out-sm)] transition hover:text-[var(--coral-deep)] hover:shadow-[var(--neu-out-hover)]">
                    <Icon name="camera" className="h-[18px] w-[18px]" />
                  </Link>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-xs leading-5 text-[var(--muted)]" role="status">
            {stateMessage[sectionState]}
          </p>
          {sectionState === "load_error" && (
            <button
              type="button"
              onClick={() => void refresh()}
              className="min-h-11 rounded-full bg-[var(--coral-soft)] px-4 text-xs font-medium text-[var(--coral-deep)] transition hover:shadow-[var(--neu-out-sm)]"
            >
              重试
            </button>
          )}
        </div>
      )}

      {/* 单条删除撤销条：5 秒窗口内可撤销，超时自动落定 */}
      {undoableDelete && (
        <div className="mt-3 flex items-center gap-3 rounded-2xl border border-[var(--line)] bg-[var(--surface)] px-4 py-2.5">
          <p role="status" className="flex-1 text-xs text-[var(--muted)]">已删除 1 条收录。</p>
          <button
            type="button"
            onClick={undoDelete}
            className="min-h-11 rounded-full bg-[var(--coral-soft)] px-4 text-xs font-medium text-[var(--coral-deep)] transition hover:shadow-[var(--neu-out-sm)]"
          >
            撤销
          </button>
        </div>
      )}

      {feedback && (
        <div className="mt-3">
          <StatusRegion status={feedback.status} severity={feedback.status} message={feedback.message} />
        </div>
      )}

      <ConfirmDialog
        open={confirmClear}
        title="清空全部收录？"
        description={`将永久删除本浏览器中的 ${collects.length} 张收录图片。`}
        confirmLabel="清空"
        destructive
        onConfirm={() => void handleConfirmClearAll()}
        onCancel={() => setConfirmClear(false)}
      />
    </div>
  );
}
