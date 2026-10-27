import { AppShell } from "@/components/AppShell";
import { GalleryGrid } from "@/components/GalleryGrid";
import { Icon } from "@/components/Icon";

export default function GalleryPage() {
  return (
    <AppShell
      shiftUp
      eyebrow="Curated for You"
      title="此刻心动"
      description="从柔和裸色到大胆纹理，浏览精选灵感系列。每一款都可以直接试色、让 AI 生成相似款，或带入 AR 试戴。"
    >
      <p className="mb-5 flex min-h-[50px] items-center gap-3 rounded-full bg-[var(--surface)] px-5 text-[12.5px] tracking-[.04em] text-[#8b8c81] shadow-[var(--neu-in-sm)]">
        <Icon name="search" className="h-[15px] w-[15px]" />
        共 6 款精选 · 点开任意款式即可试色、生成相似款或 AR 试戴
      </p>

      <GalleryGrid />
    </AppShell>
  );
}
