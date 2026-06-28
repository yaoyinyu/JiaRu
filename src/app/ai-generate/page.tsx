"use client";

import { useState } from "react";
import { Header } from "@/components/Header";
import { AI_STYLES } from "@/lib/utils";

type Status = "idle" | "loading" | "success" | "error";

export default function AiGeneratePage() {
  const [prompt, setPrompt] = useState("");
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [errorMsg, setErrorMsg] = useState("");

  const handleGenerate = async () => {
    if (!prompt.trim() || status === "loading") return;

    setStatus("loading");
    setErrorMsg("");
    setImageUrl(null);

    try {
      const resp = await fetch("/api/generate-ai", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt }),
      });

      const data = await resp.json();

      if (!resp.ok) {
        throw new Error(data?.error || `请求失败 (${resp.status})`);
      }

      if (!data?.imageUrl) {
        throw new Error("API 返回数据异常");
      }

      setImageUrl(data.imageUrl);
      setStatus("success");
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : String(err));
      setStatus("error");
    }
  };

  const handleSave = async () => {
    if (!imageUrl) return;
    try {
      const resp = await fetch(imageUrl);
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.download = `jiaru-ai-${Date.now()}.png`;
      link.href = url;
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      // 跨域下载失败时回退到新窗口打开
      window.open(imageUrl, "_blank");
    }
  };

  return (
    <div className="min-h-dvh flex flex-col">
      <Header />

      <main className="flex-1 pt-20 pb-8 px-4 max-w-md mx-auto w-full">
        <h2 className="text-lg font-semibold text-center mb-1">
          ✨ AI 生成美甲
        </h2>
        <p className="text-xs text-gray-400 text-center mb-6">
          输入风格描述，AI为你设计独一无二的美甲
        </p>

        {/* 输入区 */}
        <div className="bg-white rounded-2xl p-4 shadow-sm border border-pink-100 mb-4">
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="描述你想要的风格，如：银色亮片渐变，简约气质..."
            maxLength={500}
            className="w-full h-24 resize-none outline-none text-sm
                       text-gray-700 placeholder:text-gray-300"
          />

          {/* 字数统计 */}
          <div className="text-right text-[10px] text-gray-300 mt-1">
            {prompt.length}/500
          </div>

          {/* 预设风格关键词 */}
          <div className="flex flex-wrap gap-2 mt-2">
            {AI_STYLES.map((style) => (
              <button
                key={style}
                onClick={() => setPrompt(style)}
                className="px-3 py-1.5 rounded-full text-xs
                           bg-pink-50 text-pink-400 border border-pink-100
                           hover:bg-pink-100 transition-colors"
              >
                {style}
              </button>
            ))}
          </div>
        </div>

        {/* 生成按钮 */}
        <button
          onClick={handleGenerate}
          disabled={status === "loading" || !prompt.trim()}
          className="w-full h-12 rounded-2xl bg-gradient-to-r from-[#E8A0BF] to-[#D4749D]
                     text-white text-sm font-medium shadow-sm
                     hover:shadow-md active:scale-[0.98] transition-all
                     disabled:opacity-40 disabled:cursor-not-allowed
                     flex items-center justify-center gap-2"
        >
          {status === "loading" ? (
            <>
              <span className="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              生成中...
            </>
          ) : (
            <>✨ AI 生成</>
          )}
        </button>

        {/* 结果展示 — 错误 */}
        {status === "error" && (
          <div className="mt-6 bg-red-50 rounded-2xl p-4 shadow-sm border border-red-200">
            <p className="text-sm text-red-500 font-medium mb-1">❌ 生成失败</p>
            <p className="text-xs text-red-400">{errorMsg}</p>
            <button
              onClick={handleGenerate}
              className="mt-3 text-xs text-red-500 underline hover:text-red-600"
            >
              重试
            </button>
          </div>
        )}

        {/* 结果展示 — 成功 */}
        {status === "success" && imageUrl && (
          <div className="mt-6 bg-white rounded-2xl p-4 shadow-sm border border-pink-100">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={imageUrl}
              alt="AI生成效果"
              className="w-full rounded-xl"
            />
            <button
              onClick={handleSave}
              className="mt-3 w-full h-10 rounded-xl bg-pink-50 text-pink-500 text-sm
                         hover:bg-pink-100 transition-colors font-medium"
            >
              💾 保存图片
            </button>
          </div>
        )}

        {/* 隐私说明 */}
        <div className="mt-6 p-3 bg-white/60 rounded-2xl border border-pink-50 text-center">
          <p className="text-xs text-gray-400">
            🔒 只发送文字描述，不发送你的照片
          </p>
        </div>
      </main>
    </div>
  );
}
