"use client";

import Link from "next/link";

export function Header() {
  return (
    <header className="fixed top-0 left-0 right-0 z-50 h-16 bg-white/80 backdrop-blur-md border-b border-pink-100">
      <div className="max-w-md mx-auto h-full px-4 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2">
          <span className="text-lg">💅</span>
          <span className="font-bold text-[#4A4A4A]">甲如</span>
        </Link>
      </div>
    </header>
  );
}
