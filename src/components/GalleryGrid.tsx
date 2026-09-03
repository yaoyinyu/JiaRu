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
      <div className="grid grid-cols-2 gap-3 sm:gap-5 md:grid-cols-3">
        {GALLERY_IMAGES.map((item, index) => (
          <div
            key={item.id}
            className="group overflow-hidden rounded-[22px] border border-white/90 bg-white/72 shadow-[0_12px_35px_rgba(111,75,92,.07)] transition duration-300 hover:-translate-y-1 hover:shadow-[0_22px_48px_rgba(111,75,92,.13)]"
          >
            <div className="relative aspect-square overflow-hidden bg-gradient-to-br from-pink-50 to-purple-50">
              <Image src={item.src} alt={item.name} width={360} height={360} className="h-full w-full object-cover transition duration-500 group-hover:scale-105" />
              <span className="absolute left-3 top-3 rounded-full border border-white/70 bg-white/68 px-2.5 py-1 text-[10px] font-medium text-[#9B7A89] backdrop-blur-md">LOOK {String(index + 1).padStart(2, "0")}</span>
            </div>
            <div className="p-3.5 sm:p-4">
              <p className="truncate text-sm font-medium text-[#554D51]">{item.name}</p>
              <div className="mt-3 grid grid-cols-3 gap-1.5">
                <Link href={`/editor?gallery=${item.id}`} className="rounded-full bg-pink-100/80 px-2 py-1.5 text-center text-[11px] font-medium text-[#B95F87] transition hover:bg-[#D4749D] hover:text-white">试色</Link>
                <Link href={`/ai-generate?gallery=${item.id}`} className="rounded-full bg-purple-50 px-2 py-1.5 text-center text-[11px] font-medium text-[#9A7BB8] transition hover:bg-[#A583C4] hover:text-white">AI 相似款</Link>
                <Link href={`/ar-tryon?gallery=${item.id}`} className="rounded-full bg-pink-50 px-2 py-1.5 text-center text-[11px] font-medium text-[#B96A8C] transition hover:bg-white hover:shadow-sm">AR 试戴</Link>
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
    <div className="mt-8 border-t border-pink-100/80 pt-6">
      <div className="mb-4 flex items-center justify-between">
        <p className="flex items-center gap-2 text-sm font-semibold text-[#7A7076]">
          <Icon name="sparkles" className="h-4 w-4 text-[#CF6F99]" />
          我的收录
          <span className="rounded-full bg-pink-100 px-2 py-0.5 text-[10px] font-medium text-[#B95F87]">{collects.length}</span>
        </p>
        <button onClick={handleClearAll} className="text-[11px] text-[#AAA1A6] transition hover:text-red-400">清空全部</button>
      </div>
      <div className="grid grid-cols-2 gap-3 sm:gap-5 md:grid-cols-3">
        {collects.map(({ record, url }) => (
          <div
            key={record.id}
            className="group overflow-hidden rounded-[22px] border border-purple-100/90 bg-white/72 shadow-[0_12px_35px_rgba(111,75,92,.07)] transition duration-300 hover:-translate-y-1 hover:shadow-[0_22px_48px_rgba(111,75,92,.13)]"
          >
            <div className="relative aspect-square overflow-hidden bg-gradient-to-br from-pink-50 to-purple-50">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={url} alt="我的收录" className="h-full w-full object-cover transition duration-500 group-hover:scale-105" />
              <span className="absolute left-3 top-3 rounded-full border border-white/70 bg-purple-100/85 px-2.5 py-1 text-[10px] font-medium text-[#8B6AA8] backdrop-blur-md">我的收录</span>
            </div>
            <div className="p-3.5 sm:p-4">
              <div className="flex items-center justify-between gap-2">
                <p className="min-w-0 truncate text-[11px] text-[#A49A9F]">
                  {formatCollectTime(record.createdAt)}
                  {record.source.engine ? ` · ${record.source.engine}` : ""}
                </p>
                <button
                  onClick={() => handleDelete(record.id)}
                  aria-label="删除这条收录"
                  className="grid h-7 w-7 shrink-0 place-items-center rounded-full text-[#C9B6C0] transition hover:bg-red-50 hover:text-red-400"
                >
                  <Icon name="trash" className="h-3.5 w-3.5" />
                </button>
              </div>
              <div className="mt-3 grid grid-cols-2 gap-1.5">
                <Link href={`/ai-generate?collect=${record.id}`} className="rounded-full bg-purple-50 px-2 py-1.5 text-center text-[11px] font-medium text-[#9A7BB8] transition hover:bg-[#A583C4] hover:text-white">AI 相似款</Link>
                <Link href={`/ar-tryon?collect=${record.id}`} className="rounded-full bg-pink-50 px-2 py-1.5 text-center text-[11px] font-medium text-[#B96A8C] transition hover:bg-white hover:shadow-sm">AR 试戴</Link>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
