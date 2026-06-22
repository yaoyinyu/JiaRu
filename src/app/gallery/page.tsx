"use client";

import { Header } from "@/components/Header";
import { GalleryGrid } from "@/components/GalleryGrid";

export default function GalleryPage() {
  return (
    <div className="min-h-dvh flex flex-col">
      <Header />

      <main className="flex-1 pt-20 pb-8">
        <h2 className="text-lg font-semibold text-center mb-4">🖼️ 预设美甲图库</h2>
        <p className="text-xs text-gray-400 text-center mb-6 px-4">
          选择喜欢的款式作为参考，进入编辑器试色
        </p>

        <GalleryGrid />
      </main>
    </div>
  );
}
