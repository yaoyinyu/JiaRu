"use client";

import { useState, useRef, useCallback } from "react";
import { AppShell } from "@/components/AppShell";
import { AI_STYLE_PROMPTS } from "@/lib/ai-style-prompts";

type Status = "idle" | "loading" | "success" | "error";

export default function AiGeneratePage() {
  const [prompt, setPrompt] = useState("");
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [errorMsg, setErrorMsg] = useState("");

  // Track which prompt index to show next for each style label.
  const styleIndices = useRef<Record<string, number>>({});

  const handleStyleClick = useCallback((label: string) => {
    const group = AI_STYLE_PROMPTS.find((g) => g.label === label);
    if (!group) return;
    const currentIdx = styleIndices.current[label] ?? 0;
    const nextIdx = (currentIdx + 1) % group.prompts.length;
    styleIndices.current[label] = nextIdx;
    setPrompt(group.prompts[currentIdx]);
  }, []);

  const handleGenerate = async () => {
    if (!prompt.trim() || status === "loading") return;
    setStatus("loading");
    setErrorMsg("");
    setImageUrl(null);
    try {
      const resp = await fetch("/api/generate-ai", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ prompt }) });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data?.error || `请求失败 (${resp.status})`);
      if (!data?.imageUrl) throw new Error("API 返回数据异常");
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
    <AppShell eyebrow="AI Nail Atelier" title="把一句灵感，变成一套美甲设计" description="描述你脑海里的颜色、材质与情绪，AI 会为你生成独一无二的视觉参考。">
      <div className="grid overflow-hidden rounded-[30px] border border-white/80 bg-white/58 shadow-[0_28px_80px_rgba(116,73,92,.11)] backdrop-blur-2xl lg:grid-cols-[.9fr_1.1fr]">
        <section className="p-5 sm:p-8">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold uppercase tracking-[.16em] text-[#CF6F99]">Creative brief</p>
            <span className="text-[11px] text-[#B1A7AC]">{prompt.length}/500</span>
          </div>
          <textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder="例如：银色亮片渐变，带一点月光感，简约但有细节……" maxLength={500} className="mt-4 h-40 w-full resize-none rounded-2xl border border-pink-100/70 bg-white/75 p-4 text-sm leading-7 text-[#544C50] outline-none transition placeholder:text-[#BEB4B9] focus:border-pink-300 focus:ring-4 focus:ring-pink-100/50" />
          <p className="mt-5 text-xs font-medium text-[#7F767B]">从一个风格开始</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {AI_STYLE_PROMPTS.map((group) => <button key={group.label} onClick={() => handleStyleClick(group.label)} className="rounded-full border border-pink-100 bg-pink-50/65 px-3 py-2 text-xs text-[#B96A8C] transition hover:-translate-y-0.5 hover:bg-white hover:shadow-sm">{group.label}</button>)}
          </div>
          <button onClick={handleGenerate} disabled={status === "loading" || !prompt.trim()} className="mt-7 flex h-13 w-full items-center justify-center gap-2 rounded-2xl bg-gradient-to-r from-[#E8A0BF] to-[#C96591] text-sm font-semibold text-white shadow-[0_12px_28px_rgba(207,111,153,.25)] transition hover:-translate-y-0.5 hover:shadow-[0_16px_34px_rgba(207,111,153,.32)] active:scale-[.98] disabled:cursor-not-allowed disabled:opacity-40">
            {status === "loading" ? <><span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />正在生成设计</> : <>生成我的美甲设计 <span aria-hidden="true">✦</span></>}
          </button>
          <p className="mt-4 text-center text-[11px] text-[#AAA1A6]">只发送文字描述，不会发送你的照片</p>
        </section>
        <section className="relative flex min-h-[390px] items-center justify-center border-t border-white/80 bg-[radial-gradient(circle_at_35%_25%,rgba(238,176,204,.55),transparent_40%),radial-gradient(circle_at_75%_75%,rgba(255,213,146,.48),transparent_42%),linear-gradient(145deg,#fff8fb,#faf6ff)] p-5 lg:border-l lg:border-t-0 sm:p-8">
          {status === "success" && imageUrl ? (
            <div className="w-full">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={imageUrl} alt="AI 生成的美甲设计" className="mx-auto max-h-[520px] w-full rounded-[22px] object-contain shadow-[0_20px_60px_rgba(80,52,67,.18)]" />
              <button onClick={handleSave} className="mx-auto mt-4 flex rounded-full bg-white/85 px-5 py-2.5 text-xs font-medium text-[#B95F87] shadow-sm backdrop-blur transition hover:bg-white">保存设计到本地</button>
            </div>
          ) : status === "error" ? (
            <div className="max-w-sm rounded-3xl border border-red-100 bg-white/80 p-6 text-center shadow-lg">
              <span className="text-3xl">○</span><h2 className="mt-3 font-semibold text-red-500">生成没有完成</h2><p className="mt-2 text-xs leading-5 text-red-400">{errorMsg}</p><button onClick={handleGenerate} className="mt-4 text-xs font-medium text-red-500 underline">再试一次</button>
            </div>
          ) : (
            <div className="text-center">
              <div className="mx-auto grid h-28 w-28 place-items-center rounded-[32px] border border-white/80 bg-white/45 shadow-[0_18px_50px_rgba(126,77,99,.10)] backdrop-blur-xl"><span className="text-4xl">{status === "loading" ? "✦" : "◇"}</span></div>
              <h2 className="mt-6 text-lg font-semibold text-[#5A5156]">{status === "loading" ? "正在凝聚你的灵感…" : "你的设计将在这里出现"}</h2>
              <p className="mt-2 text-xs text-[#9D9298]">{status === "loading" ? "色彩与材质正在生成，请稍候" : "描述越具体，生成结果越贴近想象"}</p>
            </div>
          )}
        </section>
      </div>
    </AppShell>
  );
}
