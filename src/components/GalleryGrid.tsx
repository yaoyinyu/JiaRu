"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { GALLERY_IMAGES } from "@/lib/utils";
import Link from "next/link";
import Image from "next/image";
import { Icon } from "@/components/Icon";
import {
  clearCollects,
  deleteCollect,
  listCollects,
} from "@/lib/gallery-collection";
import type { GalleryCollectRecord } from "@/lib/gallery-collection";

/** 收录卡片的视图状态：blob 的 objectURL 与记录绑定，便于释放。 */
type CollectView = { record: GalleryCollectRecord; url: string };

/** 收录时间格式化（仅客户端渲染，无水合风险）。 */
function formatCollectTime(timestamp: number): string {
  const date = new Date(timestamp);
  return `${date.getMonth() + 1}月${date.getDate()}日 ${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

export function GalleryGrid() {
  return (
    <>
      <div className="grid grid-cols-2 gap-3 sm:gap-5 md:grid-cols-3 wl:grid-cols-4">
        {GALLERY_IMAGES.map((item, index) => (
          <div
            key={item.id}
            className="group overflow-hidden rounded-[20px] bg-[var(--surface)] shadow-[var(--neu-out-sm)] transition duration-300 hover:shadow-[var(--neu-out-hover)]"
          >
            <div className="relative aspect-square overflow-hidden bg-[var(--sage)]">
              <Image src={item.src} alt={item.name} width={360} height={360} className="h-full w-full object-cover transition duration-500 group-hover:scale-[1.03]" />
              <span className="absolute left-2.5 top-2.5 rounded-full bg-[var(--surface)] px-2.5 py-1 font-[var(--serif)] text-[9.5px] tracking-[.16em] text-[#8b8c81] shadow-[var(--neu-out-sm)]">LOOK {String(index + 1).padStart(2, "0")}</span>
            </div>
            <div className="p-3 sm:p-4">
              <p className="truncate font-[var(--serif)] text-[14.5px] font-medium text-[var(--ink)]">{item.name}</p>
              <div className="mt-2.5 grid grid-cols-3 gap-2">
                <Link href={`/editor?gallery=${item.id}`} aria-label={`为「${item.name}」试色`} className="grid h-11 place-items-center rounded-full bg-[var(--coral-soft)] text-[var(--coral-deep)] transition hover:shadow-[var(--neu-out-sm)]">
                  <Icon name="palette" className="h-[18px] w-[18px]" />
                </Link>
                <Link href={`/ai-generate?gallery=${item.id}`} aria-label={`为「${item.name}」生成 AI 相似款`} className="grid h-11 place-items-center rounded-full bg-[var(--sage)] text-[#5c6752] transition hover:shadow-[var(--neu-out-sm)]">
                  <Icon name="sparkles" className="h-[18px] w-[18px]" />
                </Link>
                <Link href={`/ar-tryon?gallery=${item.id}`} aria-label={`AR 试戴「${item.name}」`} className="grid h-11 place-items-center rounded-full bg-[var(--surface)] text-[var(--muted)] shadow-[var(--neu-out-sm)] transition hover:text-[var(--coral-deep)] hover:shadow-[var(--neu-out-hover)]">
                  <Icon name="camera" className="h-[18px] w-[18px]" />
                </Link>
              </div>
            </div>
          </div>
        ))}
      </div>
      <CollectsSection />
    </>
  );
}

/** 「我的收录」区块：首屏不渲染，IndexedDB 读取完成后异步追加，避免 SSR 水合错位。 */
function CollectsSection() {
  const [collects, setCollects] = useState<CollectView[]>([]);
  const [loaded, setLoaded] = useState(false);
  const urlsRef = useRef<string[]>([]);

  const refresh = useCallback(async () => {
    try {
      const records = await listCollects();
      const views = records.map((record) => {
        const url = URL.createObjectURL(record.blob);
        urlsRef.current.push(url);
        return { record, url };
      });
      setCollects(views);
    } catch {
      setCollects([]);
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    void refresh();
    return () => {
      for (const url of urlsRef.current) URL.revokeObjectURL(url);
      urlsRef.current = [];
    };
  }, [refresh]);

  const handleDelete = async (id: string) => {
    const view = collects.find((item) => item.record.id === id);
    try {
      await deleteCollect(id);
    } catch {
      // 删除失败时保持现状，不打断浏览。
      return;
    }
    if (view) URL.revokeObjectURL(view.url);
    urlsRef.current = urlsRef.current.filter((url) => url !== view?.url);
    setCollects((current) => current.filter((item) => item.record.id !== id));
  };

  const handleClearAll = async () => {
    try {
      await clearCollects();
    } catch {
      return;
    }
    for (const url of urlsRef.current) URL.revokeObjectURL(url);
    urlsRef.current = [];
    setCollects([]);
  };

  if (!loaded || collects.length === 0) return null;

  return (
    <div className="mt-8 border-t border-[var(--line)] pt-6">
      <div className="mb-4 flex items-center justify-between">
        <p className="flex items-center gap-2 font-[var(--serif)] text-[14.5px] font-medium text-[var(--ink)]">
          <Icon name="sparkles" className="h-4 w-4 text-[var(--coral)]" />
          我的收录
          <span className="rounded-full bg-[var(--coral-soft)] px-2 py-0.5 text-[10px] font-medium text-[var(--coral-deep)]">{collects.length}</span>
        </p>
        <button onClick={handleClearAll} className="text-[11px] text-[var(--muted)] transition hover:text-[var(--coral-deep)]">清空全部</button>
      </div>
      <div className="grid grid-cols-2 gap-3 sm:gap-5 md:grid-cols-3 wl:grid-cols-4">
        {collects.map(({ record, url }) => (
          <div
            key={record.id}
            className="group overflow-hidden rounded-[20px] bg-[var(--surface)] shadow-[var(--neu-out-sm)] transition duration-300 hover:shadow-[var(--neu-out-hover)]"
          >
            <div className="relative aspect-square overflow-hidden bg-[var(--sage)]">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={url} alt="我的收录" className="h-full w-full object-cover transition duration-500 group-hover:scale-[1.03]" />
              <span className="absolute left-2.5 top-2.5 rounded-full bg-[var(--surface)] px-2.5 py-1 text-[9.5px] tracking-[.1em] text-[#8b8c81] shadow-[var(--neu-out-sm)]">我的收录</span>
            </div>
            <div className="p-3 sm:p-4">
              <div className="flex items-center justify-between gap-2">
                <p className="min-w-0 truncate text-[11px] text-[var(--muted)]">
                  {formatCollectTime(record.createdAt)}
                  {record.source.engine ? ` · ${record.source.engine}` : ""}
                </p>
                <button
                  onClick={() => handleDelete(record.id)}
                  aria-label="删除这条收录"
                  className="grid h-7 w-7 shrink-0 place-items-center rounded-full text-[#b6b3a5] transition hover:bg-[var(--coral-soft)] hover:text-[var(--coral-deep)]"
                >
                  <Icon name="trash" className="h-3.5 w-3.5" />
                </button>
              </div>
              <div className="mt-2.5 grid grid-cols-2 gap-2">
                <Link href={`/ai-generate?collect=${record.id}`} aria-label="为这条收录生成 AI 相似款" className="grid h-11 place-items-center rounded-full bg-[var(--sage)] text-[#5c6752] transition hover:shadow-[var(--neu-out-sm)]">
                  <Icon name="sparkles" className="h-[18px] w-[18px]" />
                </Link>
                <Link href={`/ar-tryon?collect=${record.id}`} aria-label="AR 试戴这条收录" className="grid h-11 place-items-center rounded-full bg-[var(--surface)] text-[var(--muted)] shadow-[var(--neu-out-sm)] transition hover:text-[var(--coral-deep)] hover:shadow-[var(--neu-out-hover)]">
                  <Icon name="camera" className="h-[18px] w-[18px]" />
                </Link>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
