import { AppShell } from "@/components/AppShell";
import { GalleryGrid } from "@/components/GalleryGrid";

export default function GalleryPage() {
  return (
    <AppShell shiftUp eyebrow="Curated for You" title="此刻心动">
      <GalleryGrid />
    </AppShell>
  );
}
