import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "甲如 — 美甲试色",
  description: "上传手部照片，在线试戴美甲效果。AI生成 · AR预览 · 无需下载",
  keywords: ["美甲", "试色", "美甲预览", "AI美甲", "AR美甲"],
  authors: [{ name: "甲如" }],
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body className="min-h-dvh flex flex-col bg-[#FFF5F7] text-[#4A4A4A]">
        {children}
      </body>
    </html>
  );
}
