"use client";

import { GALLERY_IMAGES } from "@/lib/utils";
import Link from "next/link";
import Image from "next/image";

export function GalleryGrid() {
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
      {GALLERY_IMAGES.map((item) => (
        <Link
          key={item.id}
          href={`/editor?gallery=${item.id}`}
          className="group overflow-hidden rounded-[24px] border border-[#e8a0bf]/15 bg-white/70 shadow-[0_8px_28px_rgba(232,160,191,0.08)] backdrop-blur-xl transition hover:-translate-y-1 hover:shadow-[0_16px_42px_rgba(212,116,157,0.14)] active:scale-[0.98]"
        >
          <div className="aspect-square bg-gradient-to-br from-[#fff5f7] to-[#f4efff]">
            <Image
              src={item.src}
              alt={item.name}
              width={240}
              height={240}
              className="h-full w-full object-cover transition duration-300 group-hover:scale-105"
            />
          </div>
          <div className="p-3">
            <p className="text-center text-sm font-medium text-[#4a4a4a]">{item.name}</p>
          </div>
        </Link>
      ))}
    </div>
  );
}