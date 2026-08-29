"use client";

import { useState, useRef, useCallback } from "react";
import { AppShell } from "@/components/AppShell";
import { Icon } from "@/components/Icon";
import { AI_STYLE_PROMPTS } from "@/lib/ai-style-prompts";
import {
  AI_IMAGE_RATIOS,
  AI_IMAGE_SIZES,
  resolveAiImageDimension,
  type AiImageRatio,
  type AiImageSize,
} from "@/lib/ai-image-size";

type Status = "idle" | "loading" | "success" | "error";

const MAX_REFERENCE_FILE_SIZE = 10 * 1024 * 1024; // 10MB 原始文件上限
const MAX_REFERENCE_EDGE = 1024; // 压缩后最长边

/** 按原图宽高比就近映射到 Agnes 支持的 ratio 白名单（覆盖全部 8 种比例）。 */
function pickReferenceRatio(width: number, height: number): AiImageRatio {
  const r = width / height;
  if (r >= 2.0) return "21:9";
  if (r >= 1.65) return "16:9";
  if (r >= 1.4) return "3:2";
  if (r >= 1.2) return "4:3";
  if (r >= 0.95) return "1:1";
  if (r >= 0.85) return "3:4";
  if (r >= 0.7) return "2:3";
  return "9:16";
}

/** 压缩参考图到最长边 1024 并转 JPEG Data URI（透明底色填白）。 */
function compressReferenceImage(img: HTMLImageElement): {
  dataUrl: string;
  ratio: AiImageRatio;
} {
  const scale = Math.min(1, MAX_REFERENCE_EDGE / Math.max(img.naturalWidth, img.naturalHeight));
  const width = Math.max(1, Math.round(img.naturalWidth * scale));
  const height = Math.max(1, Math.round(img.naturalHeight * scale));
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("无法处理图片");
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, width, height);
  ctx.drawImage(img, 0, 0, width, height);
  return {
    dataUrl: canvas.toDataURL("image/jpeg", 0.85),
    ratio: pickReferenceRatio(img.naturalWidth, img.naturalHeight),
  };
}

export default function AiGeneratePage() {
  const [prompt, setPrompt] = useState("");
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [errorMsg, setErrorMsg] = useState("");
  const [referenceImage, setReferenceImage] = useState<string | null>(null);
  const [referenceError, setReferenceError] = useState("");
  const [ratio, setRatio] = useState<AiImageRatio>("1:1");
  const [size, setSize] = useState<AiImageSize>("1K");

  // 由「尺寸档位 + 画面比例」决定的最终输出像素尺寸（参考 Agnes 输出尺寸参考表）。
  const resolvedDimension = resolveAiImageDimension(size, ratio);

  /** 尺寸/比例选择 chip 的样式。 */
  const chipClass = (active: boolean) =>
    `rounded-full border px-3 py-1.5 text-xs transition ${
      active
        ? "border-pink-300 bg-pink-100 text-[#A4506F]"
        : "border-pink-100 bg-pink-50/65 text-[#B96A8C] hover:bg-white"
    }`;

  // Track the last shown prompt index for each style label to avoid immediate repeats.
  const lastIndices = useRef<Record<string, number>>({});

  const handleStyleClick = useCallback((label: string) => {
    const group = AI_STYLE_PROMPTS.find((g) => g.label === label);
    if (!group || group.prompts.length === 0) return;
    const count = group.prompts.length;
    const lastIdx = lastIndices.current[label];
    let idx = Math.floor(Math.random() * count);
    // Avoid showing the exact same prompt twice in a row for the same style.
    if (count > 1 && idx === lastIdx) {
      idx = (idx + 1) % count;
    }
    lastIndices.current[label] = idx;
    setPrompt(group.prompts[idx]);
  }, []);

  const handleReferenceFile = useCallback((file: File) => {
    setReferenceError("");
    if (!file.type.startsWith("image/")) {
      setReferenceError("请选择图片文件（PNG/JPG/WebP）");
      return;
    }
    if (file.size > MAX_REFERENCE_FILE_SIZE) {
      setReferenceError("图片超过 10MB，请更换更小的图片");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const img = new Image();
      img.onload = () => {
        try {
          const { dataUrl, ratio: refRatio } = compressReferenceImage(img);
          setReferenceImage(dataUrl);
          // 参考图上传时把画面比例就近设为图片自身比例（用户随后可在选择器中覆盖）。
          setRatio(refRatio);
        } catch {
          setReferenceError("图片处理失败，请更换图片重试");
        }
      };
      img.onerror = () => setReferenceError("图片解码失败，请更换图片重试");
      img.src = String(reader.result);
    };
    reader.onerror = () => setReferenceError("读取文件失败，请重试");
    reader.readAsDataURL(file);
  }, []);

  const removeReferenceImage = useCallback(() => {
    setReferenceImage(null);
    setReferenceError("");
  }, []);

  const handleGenerate = async () => {
    if (!prompt.trim() || status === "loading") return;
    setStatus("loading");
    setErrorMsg("");
    setImageUrl(null);
    try {
      const resp = await fetch("/api/generate-ai", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt,
          image: referenceImage ?? undefined,
          ratio,
          size,
        }),
      });
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
    <AppShell shiftUp eyebrow="AI Nail Atelier" title="把一句灵感，变成一套美甲设计" description="描述你脑海里的颜色、材质与情绪，AI 会为你生成独一无二的视觉参考。">
      <div className="fade-in-up fade-in-up-slow grid overflow-hidden rounded-[30px] border border-white/80 bg-white/58 shadow-[0_28px_80px_rgba(116,73,92,.11)] backdrop-blur-2xl lg:grid-cols-[.9fr_1.1fr]">
        <section className="p-5 sm:p-8">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold uppercase tracking-[.16em] text-[#CF6F99]">Creative brief</p>
            <span className="text-[11px] text-[#B1A7AC]">{prompt.length}/520</span>
          </div>
          <textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder="例如：银色亮片渐变，带一点月光感，简约但有细节……" maxLength={520} className="mt-4 h-40 w-full resize-none rounded-2xl border border-pink-100/70 bg-white/75 p-4 text-sm leading-7 text-[#544C50] outline-none transition placeholder:text-[#BEB4B9] focus:border-pink-300 focus:ring-4 focus:ring-pink-100/50" />
          <p className="mt-5 text-xs font-medium text-[#7F767B]">参考图（可选）</p>
          {referenceImage ? (
            <div className="mt-3 flex items-center gap-3 rounded-2xl border border-pink-100/70 bg-white/75 p-3">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={referenceImage} alt="手部参考图" className="h-16 w-16 rounded-xl object-cover" />
              <div className="flex-1 text-xs text-[#8B8287]">
                <p className="font-medium text-[#5A5156]">已添加参考图</p>
                <p className="mt-1">生成结果将直接呈现在图中手部指甲上</p>
              </div>
              <button onClick={removeReferenceImage} className="rounded-full border border-pink-100 bg-pink-50/65 px-3 py-1.5 text-xs text-[#B96A8C] transition hover:bg-white">移除</button>
            </div>
          ) : (
            <label className="mt-3 flex h-20 w-full cursor-pointer flex-col items-center justify-center gap-1 rounded-2xl border border-dashed border-pink-200 bg-white/45 text-xs text-[#B98AA4] transition hover:border-pink-300 hover:bg-white/70">
              <Icon name="camera" className="h-6 w-6" />
              点击上传手部照片
              <input type="file" accept="image/*" className="hidden" onChange={(event) => { const file = event.target.files?.[0]; if (file) handleReferenceFile(file); event.target.value = ""; }} />
            </label>
          )}
          {referenceError ? <p className="mt-2 text-[11px] text-red-400">{referenceError}</p> : <p className="mt-2 text-[11px] text-[#AAA1A6]">上传的图片会发送给 AI 服务，仅用于本次生成；不上传则按文字直接生成</p>}
          <p className="mt-5 text-xs font-medium text-[#7F767B]">从一个风格开始</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {AI_STYLE_PROMPTS.map((group) => <button key={group.label} onClick={() => handleStyleClick(group.label)} className="rounded-full border border-pink-100 bg-pink-50/65 px-3 py-2 text-xs text-[#B96A8C] transition hover:-translate-y-0.5 hover:bg-white hover:shadow-sm">{group.label}</button>)}
          </div>
          <div className="mt-5 space-y-4">
            <div>
              <p className="text-xs font-medium text-[#7F767B]">画面比例</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {AI_IMAGE_RATIOS.map((r) => (
                  <button key={r} type="button" onClick={() => setRatio(r)} className={chipClass(ratio === r)}>{r}</button>
                ))}
              </div>
            </div>
            <div>
              <p className="text-xs font-medium text-[#7F767B]">输出尺寸</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {AI_IMAGE_SIZES.map((s) => (
                  <button key={s} type="button" onClick={() => setSize(s)} className={chipClass(size === s)}>{s}</button>
                ))}
              </div>
            </div>
            <p className="text-[11px] text-[#AAA1A6]">输出尺寸：{resolvedDimension.replace("x", " × ")}（{size} · {ratio}）</p>
          </div>
          <button onClick={handleGenerate} disabled={status === "loading" || !prompt.trim()} className="mt-7 flex h-13 w-full items-center justify-center gap-2 rounded-2xl bg-gradient-to-r from-[#E8A0BF] to-[#C96591] text-sm font-semibold text-white shadow-[0_12px_28px_rgba(207,111,153,.25)] transition hover:-translate-y-0.5 hover:shadow-[0_16px_34px_rgba(207,111,153,.32)] active:scale-[.98] disabled:cursor-not-allowed disabled:opacity-40">
            {status === "loading" ? <span key="btn-loading" className="fade-in-up inline-flex items-center gap-2"><span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />正在生成设计</span> : <span key="btn-idle" className="fade-in-up inline-flex items-center gap-2">生成我的美甲设计 <span aria-hidden="true"><Icon name="sparkles" className="h-4 w-4" /></span></span>}
          </button>
          <p className="mt-4 text-center text-[11px] text-[#AAA1A6]">文字描述始终发送给 AI 服务；仅当你上传参考图时，图片也会发送并只用于本次生成；「用户改进计划」可在隐私页管理</p>
        </section>
        <section className="relative flex min-h-[390px] items-center justify-center overflow-hidden border-t border-white/80 bg-[radial-gradient(circle_at_35%_25%,rgba(238,176,204,.55),transparent_40%),radial-gradient(circle_at_75%_75%,rgba(255,213,146,.48),transparent_42%),linear-gradient(145deg,#fff8fb,#faf6ff)] p-5 lg:border-l lg:border-t-0 sm:p-8">
          {status === "success" && imageUrl ? (
            <div key="success" className="fade-in-up w-full">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={imageUrl} alt="AI 生成的美甲设计" className="mx-auto max-h-[520px] w-full rounded-[22px] object-contain shadow-[0_20px_60px_rgba(80,52,67,.18)]" />
              <button onClick={handleSave} className="mx-auto mt-4 flex rounded-full bg-white/85 px-5 py-2.5 text-xs font-medium text-[#B95F87] shadow-sm backdrop-blur transition hover:bg-white">保存设计到本地</button>
            </div>
          ) : status === "error" ? (
            <div key="error" className="fade-in-up max-w-sm rounded-3xl border border-red-100 bg-white/80 p-6 text-center shadow-lg">
              <Icon name="circle" className="h-8 w-8 text-red-400" /><h2 className="mt-3 font-semibold text-red-500">生成没有完成</h2><p className="mt-2 text-xs leading-5 text-red-400">{errorMsg}</p><button onClick={handleGenerate} className="mt-4 text-xs font-medium text-red-500 underline">再试一次</button>
            </div>
          ) : status === "loading" ? (
            <>
              <div className="shimmer-sweep pointer-events-none" />
              <div key="loading" role="status" aria-live="polite" className="fade-in-up text-center">
                <div className="mx-auto grid h-28 w-28 place-items-center rounded-[32px] border border-white/80 bg-white/45 shadow-[0_18px_50px_rgba(126,77,99,.10)] backdrop-blur-xl"><Icon name="sparkles" className="shimmer-spark h-10 w-10 text-[#CF6F99]" /></div>
                <h2 className="mt-6 text-lg font-semibold text-[#5A5156]">正在凝聚你的灵感…</h2>
                <p className="mt-2 text-xs text-[#9D9298]">色彩与材质正在生成，请稍候</p>
              </div>
            </>
          ) : (
            <div key="idle" className="fade-in-up text-center">
              <div className="mx-auto grid h-28 w-28 place-items-center rounded-[32px] border border-white/80 bg-white/45 shadow-[0_18px_50px_rgba(126,77,99,.10)] backdrop-blur-xl"><Icon name="diamond" className="h-10 w-10 text-[#D9A7BC]" /></div>
              <h2 className="mt-6 text-lg font-semibold text-[#5A5156]">你的设计将在这里出现</h2>
              <p className="mt-2 text-xs text-[#9D9298]">描述越具体，生成结果越贴近想象</p>
            </div>
          )}
        </section>
      </div>
    </AppShell>
  );
}
