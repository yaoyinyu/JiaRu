import { AppShell } from "@/components/AppShell";
import { GalleryGrid } from "@/components/GalleryGrid";

export default function GalleryPage() {
  return (
    <AppShell eyebrow="Inspiration Library" title="把心动款式，变成你的下一次美甲" description="从柔和裸色到大胆纹理，浏览我们精选的灵感系列，点击任意款式即可进入试色。">
      <div className="rounded-[30px] border border-white/80 bg-white/48 p-3 shadow-[0_24px_70px_rgba(116,73,92,.08)] backdrop-blur-2xl sm:p-5">
        <GalleryGrid />
      </div>
    </AppShell>
  );
}