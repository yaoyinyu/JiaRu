"use client";

import { GALLERY_IMAGES } from "@/lib/utils";
import Link from "next/link";

export function GalleryGrid() {
  return (
    <div className="grid grid-cols-2 gap-4 px-4 max-w-md mx-auto">
      {GALLERY_IMAGES.map((item) => (
        <Link
          key={item.id}
          href={`/editor?gallery=${item.id}`}
          className="bg-white rounded-2xl overflow-hidden shadow-sm border border-pink-50
                     hover:shadow-md active:scale-[0.98] transition-all"
        >
          <div className="aspect-square bg-gradient-to-br from-pink-100 to-purple-100 flex items-center justify-center">
            <span className="text-4xl">💅</span>
          </div>
          <div className="p-3">
            <p className="text-sm text-gray-500 text-center">{item.name}</p>
          </div>
        </Link>
      ))}
    </div>
  );
}
