"use client";

import { FlowingShell, GlassPanel, PageHero } from "@/components/FlowingShell";
import { GalleryGrid } from "@/components/GalleryGrid";

export default function GalleryPage() {
  return (
    <FlowingShell maxWidth="max-w-4xl">
      <PageHero
        eyebrow="灵感图库"
        title="从精选款式里找到你的心动设计"
        description="选择喜欢的美甲风格作为参考，再进入编辑器继续试色。"
      />

      <GlassPanel className="p-4 sm:p-6">
        <GalleryGrid />
      </GlassPanel>
    </FlowingShell>
  );
}