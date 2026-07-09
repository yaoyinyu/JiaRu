"use client";

import { useState } from "react";
import { FlowingShell, GlassPanel, PageHero } from "@/components/FlowingShell";
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
      window.open(imageUrl, "_blank");
    }
  };

  return (
    <FlowingShell>
      <PageHero
        eyebrow="AI 生成"
        title="用一句话生成美甲灵感"
        description="描述颜色、质感、图案或场景，生成一张可保存的美甲效果图。"
      />

      <GlassPanel className="p-5">
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="描述你想要的风格，例如：银色亮片渐变，极简气质，适合通勤..."
          maxLength={500}
          className="h-28 w-full resize-none rounded-2xl border border-[#e8a0bf]/15 bg-white/70 p-4 text-sm text-gray-700 outline-none placeholder:text-gray-300 focus:border-[#d4749d]/40 focus:ring-4 focus:ring-[#e8a0bf]/10"
        />

        <div className="mt-2 text-right text-[10px] text-gray-300">{prompt.length}/500</div>

        <div className="mt-4 flex flex-wrap gap-2">
          {AI_STYLES.map((style) => (
            <button
              key={style}
              onClick={() => setPrompt(style)}
              className="rounded-full border border-[#e8a0bf]/15 bg-pink-50/80 px-3 py-1.5 text-xs text-[#d4749d] transition-colors hover:bg-pink-100"
            >
              {style}
            </button>
          ))}
        </div>
      </GlassPanel>

      <button
        onClick={handleGenerate}
        disabled={status === "loading" || !prompt.trim()}
        className="mt-4 flex h-12 w-full items-center justify-center gap-2 rounded-2xl bg-gradient-to-b from-[#f0b8d0] to-[#d4749d] text-sm font-semibold text-white shadow-[0_8px_24px_rgba(212,116,157,0.2)] transition hover:-translate-y-0.5 hover:shadow-[0_12px_32px_rgba(212,116,157,0.24)] active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-40"
      >
        {status === "loading" ? (
          <>
            <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
            生成中...
          </>
        ) : (
          <>✨ AI 生成</>
        )}
      </button>

      {status === "error" && (
        <GlassPanel className="mt-6 border-red-200 bg-red-50/80 p-5">
          <p className="mb-1 text-sm font-semibold text-red-500">生成失败</p>
          <p className="text-xs text-red-400">{errorMsg}</p>
          <button onClick={handleGenerate} className="mt-3 text-xs font-medium text-red-500 underline underline-offset-4">
            重试
          </button>
        </GlassPanel>
      )}

      {status === "success" && imageUrl && (
        <GlassPanel className="mt-6 p-4">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={imageUrl} alt="AI 生成效果" className="w-full rounded-2xl" />
          <button
            onClick={handleSave}
            className="mt-3 h-11 w-full rounded-2xl bg-pink-50 text-sm font-semibold text-[#d4749d] transition-colors hover:bg-pink-100"
          >
            保存图片
          </button>
        </GlassPanel>
      )}

      <GlassPanel className="mt-6 p-4 text-center">
        <p className="text-xs leading-5 text-gray-400">只发送文字描述，不发送你的照片。</p>
      </GlassPanel>
    </FlowingShell>
  );
}