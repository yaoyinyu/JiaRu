import { GALLERY_IMAGES } from "@/lib/utils";
import Link from "next/link";
import Image from "next/image";

export function GalleryGrid() {
  return (
    <div className="grid grid-cols-2 gap-3 sm:gap-5 md:grid-cols-3">
      {GALLERY_IMAGES.map((item, index) => (
        <Link key={item.id} href={`/editor?gallery=${item.id}`} className="group overflow-hidden rounded-[22px] border border-white/90 bg-white/72 shadow-[0_12px_35px_rgba(111,75,92,.07)] transition duration-300 hover:-translate-y-1 hover:shadow-[0_22px_48px_rgba(111,75,92,.13)]">
          <div className="relative aspect-square overflow-hidden bg-gradient-to-br from-pink-50 to-purple-50">
            <Image src={item.src} alt={item.name} width={360} height={360} className="h-full w-full object-cover transition duration-500 group-hover:scale-105" />
            <span className="absolute left-3 top-3 rounded-full border border-white/70 bg-white/68 px-2.5 py-1 text-[10px] font-medium text-[#9B7A89] backdrop-blur-md">LOOK {String(index + 1).padStart(2, "0")}</span>
          </div>
          <div className="flex items-center justify-between gap-2 p-3.5 sm:p-4">
            <div className="min-w-0"><p className="truncate text-sm font-medium text-[#554D51]">{item.name}</p><p className="mt-1 text-[10px] text-[#A49A9F]">点击进入试色</p></div>
            <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-pink-50 text-xs text-[#C96690] transition group-hover:bg-[#D4749D] group-hover:text-white">↗</span>
          </div>
        </Link>
      ))}
    </div>
  );
}
