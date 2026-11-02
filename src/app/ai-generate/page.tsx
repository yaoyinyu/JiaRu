"use client";

import { Suspense, useEffect, useState, useRef, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { Icon } from "@/components/Icon";
import { AI_STYLE_PROMPTS } from "@/lib/ai-style-prompts";
import { loadReferenceFromParams } from "@/lib/gallery-bridge";
import {
  addCollect,
  collectErrorToMessage,
  probeCollectStorage,
  CollectUnavailableError,
  type CollectStorageStatus,
} from "@/lib/gallery-collection";
import { StatusRegion } from "@/components/ui/StatusRegion";
import {
  AI_ERROR_MESSAGES,
  buildAiRequestBody,
  classifyAiGenerationError,
  createRequestSnapshot,
  isAbortError,
  resolveGenerateEndpoint,
  type AiEngineSettingsMap,
  type AiGenerationRequestSnapshot,
} from "@/lib/ai-generate-flow";
import {
  createWorkItem,
  saveWorkItem,
} from "@/lib/work-items";
import { loadWorkItemReference } from "@/lib/work-bridge";
import {
  AI_IMAGE_RATIOS,
  AI_IMAGE_SIZES,
  DEFAULT_AI_IMAGE_SIZE,
  isAiImageSize,
  pickReferenceRatio,
  resolveAiImageDimension,
  type AiImageRatio,
} from "@/lib/ai-image-size";
import {
  DEFAULT_SEEDREAM_SIZE,
  resolveSeedreamDimension,
  seedreamSizesFor,
} from "@/lib/seedream-image-size";

/** 生成任务状态：取消是独立终态，不算失败（方案 §6.2）。 */
type Status = "idle" | "loading" | "success" | "error" | "cancelled";

/** 生成引擎：Agnes（默认）与火山方舟 Seedream 5.0 pro / lite。 */
type Engine = "agnes" | "seedream-pro" | "seedream-lite";

const ENGINE_OPTIONS: { value: Engine; label: string }[] = [
  { value: "agnes", label: "Agnes" },
  { value: "seedream-pro", label: "Seedream 5.0 Pro" },
  { value: "seedream-lite", label: "Seedream 5.0 Lite" },
];

/** 各引擎用户提示词上限（火山方舟建议中文提示词不超过 300 字）。 */
const ENGINE_PROMPT_LIMIT: Record<Engine, number> = {
  agnes: 520,
  "seedream-pro": 300,
  "seedream-lite": 300,
};

/** 引擎可选尺寸档位（Seedream 档位随模型不同：pro 无 3K/4K，lite 无 1K）。 */
function engineSizeOptions(engine: Engine): readonly string[] {
  if (engine === "agnes") return AI_IMAGE_SIZES;
  return seedreamSizesFor(engine === "seedream-pro" ? "pro" : "lite");
}

const MAX_REFERENCE_FILE_SIZE = 10 * 1024 * 1024; // 10MB 原始文件上限
const MAX_REFERENCE_EDGE = 1024; // 压缩后最长边

// pickReferenceRatio 已抽取到 @/lib/ai-image-size（就近映射修复见评审 #9），此处直接复用。

/** 压缩参考图源到最长边 1024 并转 JPEG Data URI（透明底色填白）。 */
function compressReferenceSource(
  source: CanvasImageSource,
  sourceWidth: number,
  sourceHeight: number
): { dataUrl: string; ratio: AiImageRatio } {
  const scale = Math.min(1, MAX_REFERENCE_EDGE / Math.max(sourceWidth, sourceHeight));
  const width = Math.max(1, Math.round(sourceWidth * scale));
  const height = Math.max(1, Math.round(sourceHeight * scale));
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("无法处理图片");
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, width, height);
  ctx.drawImage(source, 0, 0, width, height);
  return {
    dataUrl: canvas.toDataURL("image/jpeg", 0.85),
    ratio: pickReferenceRatio(sourceWidth, sourceHeight),
  };
}

/** 手动上传路径：HTMLImageElement 版压缩（保持既有行为）。 */
function compressReferenceImage(img: HTMLImageElement): {
  dataUrl: string;
  ratio: AiImageRatio;
} {
  return compressReferenceSource(img, img.naturalWidth, img.naturalHeight);
}

export default function AiGeneratePage() {
  // useSearchParams 在静态渲染的客户端组件中必须包 Suspense（与 /editor 同一约定）。
  return (
    <Suspense fallback={null}>
      <AiGeneratePageInner />
    </Suspense>
  );
}

function AiGeneratePageInner() {
  const searchParams = useSearchParams();
  const workParam = searchParams.get("work");
  const galleryParam = searchParams.get("gallery");
  const collectParam = searchParams.get("collect");
  return (
    <AiGeneratePageBody
      workParam={workParam}
      galleryParam={galleryParam}
      collectParam={collectParam}
    />
  );
}

function AiGeneratePageBody({
  workParam,
  galleryParam,
  collectParam,
}: {
  workParam: string | null;
  galleryParam: string | null;
  collectParam: string | null;
}) {
  const [prompt, setPrompt] = useState("");
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [errorMsg, setErrorMsg] = useState("");
  const [referenceImage, setReferenceImage] = useState<string | null>(null);
  const [referenceError, setReferenceError] = useState("");
  const [ratio, setRatio] = useState<AiImageRatio>("1:1");
  const [engine, setEngine] = useState<Engine>("agnes");
  const [size, setSize] = useState<string>("1K");
  // 图库灵感来源名（?gallery=/collect= 自动带入参考图时展示）。
  const [refSourceName, setRefSourceName] = useState<string | null>(null);
  // 收录状态：当前生成结果是否已收录进图库。
  const [collectState, setCollectState] = useState<
    "idle" | "saving" | "saved" | "error"
  >("idle");
  // 收录失败的具体原因文案（存储不可用/读取失败等分类提示）。
  const [collectError, setCollectError] = useState<string | null>(null);
  // 本机收录能力探测：不可用时禁用收录按钮，避免假成功。
  const [collectStorage, setCollectStorage] = useState<CollectStorageStatus>("checking");

  // ── 请求快照与上一版结果（方案 §6.1/§6.3）──
  // 请求只用快照；生成期间保留旧图，新图成功后旧图折叠为「上一版」。
  const [snapshot, setSnapshot] = useState<AiGenerationRequestSnapshot | null>(null);
  const [previousResult, setPreviousResult] = useState<{
    url: string;
    snapshot: AiGenerationRequestSnapshot;
  } | null>(null);
  const [showPrevious, setShowPrevious] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  // 已等待秒数：仅视觉展示，绝不放进 live region。
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  // 每引擎独立设置（§6.4）：切换引擎恢复各自尺寸与提示词草稿，不再强制重置。
  const [engineSettings, setEngineSettings] = useState<AiEngineSettingsMap>(() => ({
    agnes: { size: DEFAULT_AI_IMAGE_SIZE, lastPromptDraft: "" },
    "seedream-pro": { size: DEFAULT_SEEDREAM_SIZE.pro, lastPromptDraft: "" },
    "seedream-lite": { size: DEFAULT_SEEDREAM_SIZE.lite, lastPromptDraft: "" },
  }));

  // 提示词与当前引擎草稿的最新值 ref：供灵感预填 effect 无过期闭包地读写。
  const promptRef = useRef("");
  const engineRef = useRef<Engine>("agnes");
  useEffect(() => {
    engineRef.current = engine;
  }, [engine]);

  // 事件驱动的草稿写入（§6.4）：所有提示词变更统一走它，同步当前引擎草稿槽。
  const setPromptDraft = useCallback(
    (text: string) => {
      promptRef.current = text;
      setPrompt(text);
      setEngineSettings((current) =>
        current[engine].lastPromptDraft === text
          ? current
          : { ...current, [engine]: { ...current[engine], lastPromptDraft: text } }
      );
    },
    [engine]
  );

  // 生成中每秒刷新等待计数（live region 之外的独立元素展示）。
  useEffect(() => {
    if (status !== "loading") return;
    const startedAt = Date.now();
    const timer = setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);
    return () => clearInterval(timer);
  }, [status]);

  // 卸载时中断进行中的请求，避免对已卸载组件应用结果。
  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  useEffect(() => {
    let cancelled = false;
    probeCollectStorage().then((result) => {
      if (!cancelled) setCollectStorage(result);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const promptLimit = ENGINE_PROMPT_LIMIT[engine];
  const promptOverLimit = prompt.length > promptLimit;

  /** 切换引擎：恢复该引擎上次尺寸与草稿（§6.4 引擎状态独立）。 */
  const handleEngineClick = (value: Engine) => {
    if (value === engine) return;
    promptRef.current = engineSettings[value].lastPromptDraft;
    setEngine(value);
    setSize(engineSettings[value].size);
    setPrompt(engineSettings[value].lastPromptDraft);
  };

  // 由「尺寸档位 + 画面比例」决定的最终输出像素尺寸：
  // Agnes 走 Agnes 尺寸表；Seedream 走火山方舟尺寸表（档位随模型联动）。
  const resolvedDimension =
    engine === "agnes"
      ? isAiImageSize(size)
        ? resolveAiImageDimension(size, ratio)
        : "—"
      : resolveSeedreamDimension(
          engine === "seedream-pro" ? "pro" : "lite",
          size,
          ratio
        ) ?? "—";

  /** 尺寸/比例选择 chip 的样式。 */
  const chipClass = (active: boolean) =>
    `inline-flex min-h-11 items-center rounded-full border px-3 py-1.5 text-xs transition ${
      active
        ? "border-pink-300 bg-pink-100 text-[#ac5145]"
        : "border-pink-100 bg-pink-50/65 text-[#a34b3f] hover:bg-[var(--surface)]"
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
    setPromptDraft(group.prompts[idx]);
  }, [setPromptDraft]);

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
    setRefSourceName(null);
  }, []);

  // 跨页参考图带入（?work= 优先于 ?gallery=/?collect=，§9.4 优先级）：
  // 与手动上传走同一条压缩链路；任何失败静默降级，不阻塞主流程。
  useEffect(() => {
    if (!workParam && !galleryParam && !collectParam) return;
    let cancelled = false;
    (async () => {
      let ref: { file: File; name: string } | null = null;
      if (workParam) {
        const file = await loadWorkItemReference(workParam);
        if (file) ref = { file, name: "本地作品" };
      }
      if (!ref && (galleryParam || collectParam)) {
        ref = await loadReferenceFromParams({ gallery: galleryParam, collect: collectParam });
      }
      if (!ref) return;
      try {
        const bitmap = await createImageBitmap(ref.file);
        try {
          const { dataUrl, ratio: refRatio } = compressReferenceSource(
            bitmap,
            bitmap.width,
            bitmap.height
          );
          if (cancelled) return;
          setReferenceImage(dataUrl);
          setRatio(refRatio);
          setRefSourceName(ref.name);
          // 灵感预填：仅当当前提示词为空时带入，并同步进当前引擎草稿槽（§6.4）。
          const prefillText = `参考「${ref.name}」的美甲样式，生成同风格的新设计`;
          if (!promptRef.current.trim()) {
            promptRef.current = prefillText;
            setPrompt(prefillText);
            setEngineSettings((current) => {
              const slot = current[engineRef.current];
              return slot.lastPromptDraft === prefillText
                ? current
                : { ...current, [engineRef.current]: { ...slot, lastPromptDraft: prefillText } };
            });
          }
        } finally {
          bitmap.close();
        }
      } catch {
        // 解码失败：静默降级，用户仍可手动上传参考图。
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [workParam, galleryParam, collectParam]);

  /** 把当前生成结果收录进图库（IndexedDB）。存储不可用/读取失败时给出分类提示。 */
  const handleCollect = async () => {
    if (!imageUrl || collectState === "saving" || collectState === "saved") return;
    if (collectStorage === "unavailable") return;
    setCollectState("saving");
    setCollectError(null);
    try {
      let blob: Blob;
      try {
        const resp = await fetch(imageUrl);
        if (!resp.ok) throw new TypeError(`HTTP ${resp.status}`);
        blob = await resp.blob();
      } catch {
        throw new Error("图片暂时无法读取，请重试");
      }
      if (!blob.type.startsWith("image/")) {
        throw new Error("返回内容不是图片");
      }
      // 收录元数据绑定回请求快照（§6.1）：记录的是产出这张图的请求参数。
      const collectSource = {
        engine: snapshot?.engine ?? engine,
        prompt: (snapshot?.prompt ?? prompt).trim().slice(0, 200),
      };
      await addCollect(blob, collectSource);
      // 主收录（经读回校验）成功后，同步登记 WorkItem（§9 新作品模型）；
      // WorkItem 写失败不回滚旧收录，也不打断成功反馈（两库并存，§9.3）。
      try {
        const item = createWorkItem({
          type: "ai-result",
          title: collectSource.prompt.slice(0, 24) || "AI 生成结果",
          previewBlob: blob,
          source: collectSource,
        });
        await saveWorkItem(item);
      } catch {
        // 静默降级：旧收录已验证成功，WorkItem 可在后续版本补建。
      }
      setCollectState("saved");
    } catch (err) {
      setCollectError(
        err instanceof CollectUnavailableError
          ? collectErrorToMessage(err)
          : err instanceof Error
            ? err.message
            : collectErrorToMessage(err)
      );
      setCollectState("error");
    }
  };

  /** 生成：请求只用快照（§6.1）；失败/取消不清旧结果（§6.2/§6.3）。 */
  const handleGenerate = async () => {
    if (status === "loading") return;
    const trimmed = prompt.trim();
    if (!trimmed) {
      setErrorMsg(AI_ERROR_MESSAGES.empty_prompt);
      setStatus("error");
      return;
    }
    if (promptOverLimit) {
      setErrorMsg(AI_ERROR_MESSAGES.prompt_over_limit);
      setStatus("error");
      return;
    }
    const requestSnapshot = createRequestSnapshot({
      engine,
      prompt: trimmed,
      ratio,
      size,
      referenceImage,
    });
    const controller = new AbortController();
    abortRef.current = controller;
    setSnapshot(requestSnapshot);
    setShowPrevious(false);
    setStatus("loading");
    setErrorMsg("");
    setCollectState("idle");
    setElapsedSeconds(0);
    try {
      const resp = await fetch(resolveGenerateEndpoint(requestSnapshot.engine), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildAiRequestBody(requestSnapshot)),
        signal: controller.signal,
      });
      const data = await resp.json().catch(() => null);
      if (!resp.ok) {
        // 服务端结构化错误信息优先；缺失时按 §6.6 错误表给分类文案。
        const kind = classifyAiGenerationError(
          new Error(data?.error ?? "request failed"),
          resp.status
        );
        throw new Error(data?.error || AI_ERROR_MESSAGES[kind]);
      }
      if (!data?.imageUrl) {
        throw new Error(AI_ERROR_MESSAGES.invalid_result);
      }
      // 新图成功：旧结果折叠为「上一版」（§6.3），主视图替换为新图。
      if (imageUrl && snapshot) {
        setPreviousResult({ url: imageUrl, snapshot });
      }
      setImageUrl(data.imageUrl);
      setStatus("success");
    } catch (err) {
      if (isAbortError(err)) {
        // 取消是独立终态（§6.2）：保留当前设置与既有结果，不自动重试。
        setStatus("cancelled");
        return;
      }
      setErrorMsg(err instanceof Error ? err.message : String(err));
      setStatus("error");
    } finally {
      abortRef.current = null;
    }
  };

  /** 取消当前生成：中断前端请求；不宣称服务端任务已终止。 */
  const handleCancelGenerate = () => {
    abortRef.current?.abort();
  };

  /** 一键切回上一版为主结果（§6.3）：主结果与上一版互换，各自绑定快照。 */
  const promotePrevious = () => {
    if (!previousResult || !imageUrl || !snapshot) return;
    const current: { url: string; snapshot: AiGenerationRequestSnapshot } = {
      url: imageUrl,
      snapshot,
    };
    setImageUrl(previousResult.url);
    setSnapshot(previousResult.snapshot);
    setPreviousResult(current);
    setShowPrevious(false);
    setCollectState("idle");
    setCollectError(null);
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

  /** 主结果块：当前结果图与操作区（成功 / 失败保底 / 取消保底共用）。 */
  const renderResultBlock = (url: string) => (
    <div className="w-full">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={url} alt="AI 生成的美甲设计" className="mx-auto max-h-[520px] w-full rounded-[22px] object-contain shadow-[var(--neu-out-md)]" />
      <div className="mx-auto mt-4 flex w-fit gap-2">
        <button onClick={handleSave} className="flex rounded-full bg-[var(--surface)] px-5 py-2.5 text-xs font-medium text-[#a34b3f] shadow-sm transition hover:bg-[var(--surface)]">保存设计到本地</button>
        <button
          onClick={handleCollect}
          disabled={collectState === "saving" || collectState === "saved" || collectStorage === "unavailable"}
          title={collectStorage === "unavailable" ? "当前浏览器不支持本地收录" : undefined}
          className="flex items-center gap-1.5 rounded-full bg-[#8a947f]/90 px-5 py-2.5 text-xs font-medium text-white shadow-sm transition hover:bg-[#8a947f] disabled:cursor-not-allowed disabled:opacity-55"
        >
          {collectStorage === "unavailable" ? (
            <>当前浏览器不支持本地收录</>
          ) : collectState === "saved" ? (
            <>已收录到图库</>
          ) : collectState === "saving" ? (
            <><span className="h-3 w-3 animate-spin rounded-full border-2 border-white/40 border-t-white" />正在收录</>
          ) : (
            <><Icon name="sparkles" className="h-3.5 w-3.5" />{collectState === "error" ? "收录失败，点击重试" : "收录到图库"}</>
          )}
        </button>
      </div>
      {collectState === "saved" && (
        <div className="mt-2 flex justify-center">
          <StatusRegion status="success" severity="success" message="已收录到图库" />
        </div>
      )}
      {collectState === "error" && (
        <div className="mt-2 flex justify-center">
          <StatusRegion
            status="error"
            severity="error"
            message={`${collectError ?? "收录失败，请重试"}${
              collectError === "图片暂时无法读取，请重试"
                ? "（图片跨域受限时可能收录失败，可先保存到本地再手动上传参考图）"
                : ""
            }`}
          />
        </div>
      )}
      {previousResult && (
        <div className="mx-auto mt-3 w-full max-w-md rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-3">
          <button
            type="button"
            onClick={() => setShowPrevious((v) => !v)}
            aria-expanded={showPrevious}
            className="text-[11px] font-medium text-[#a34b3f] underline underline-offset-2"
          >
            {showPrevious ? "收起上一版" : "查看上一版"}
          </button>
          {showPrevious && (
            <div className="mt-2">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={previousResult.url} alt="上一版生成结果" className="mx-auto max-h-[280px] w-full rounded-xl object-contain" />
              <p className="mt-1 text-[12px] text-[#6f7066]">{previousResult.snapshot.engine} · {previousResult.snapshot.size} · {previousResult.snapshot.ratio}</p>
              <button type="button" onClick={promotePrevious} className="mt-2 text-[11px] font-medium text-[#a34b3f] underline underline-offset-2">
                设为主结果
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );

  return (
    <AppShell shiftUp eyebrow="AI Nail Atelier" title="把一句灵感，变成一套美甲设计" description="描述你脑海里的颜色、材质与情绪，AI 会为你生成独一无二的视觉参考。">
      <div className="fade-in-up fade-in-up-slow grid overflow-hidden rounded-[30px] bg-[var(--surface)] shadow-[var(--neu-out-md)]  lg:grid-cols-[.9fr_1.1fr]">
        <section className="p-5 sm:p-8">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold uppercase tracking-[.16em] text-[#ac5145]">Creative brief</p>
            <span className={`text-[11px] ${promptOverLimit ? "font-medium text-red-500" : "text-[#6f7066]"}`}>{prompt.length}/{promptLimit}</span>
          </div>
          <label htmlFor="ai-prompt" className="mt-4 block text-xs font-medium text-[#67685f]">设计描述</label>
          <textarea id="ai-prompt" value={prompt} onChange={(event) => setPromptDraft(event.target.value)} placeholder="例如：银色亮片渐变，带一点月光感，简约但有细节……" maxLength={promptLimit} aria-invalid={promptOverLimit || undefined} className="mt-2 h-40 w-full resize-none rounded-2xl border border-pink-100/70 bg-[var(--surface)] p-4 text-sm leading-7 text-[#292a27] outline-none transition placeholder:text-[#6f7066] focus:border-pink-300 focus:ring-4 focus:ring-pink-100/50" />
          {promptOverLimit && (
            <p className="mt-2 text-[11px] text-red-500">当前引擎最多支持 {promptLimit} 字（已 {prompt.length} 字），请缩短后再生成。</p>
          )}
          <p className="mt-5 text-xs font-medium text-[#67685f]">参考图（可选）</p>
          {referenceImage ? (
            <div className="mt-3 flex items-center gap-3 rounded-2xl border border-pink-100/70 bg-[var(--surface)] p-3">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={referenceImage} alt="手部参考图" className="h-16 w-16 rounded-xl object-cover" />
              <div className="flex-1 text-xs text-[#6f7066]">
                <p className="font-medium text-[#292a27]">{refSourceName ? `已带入灵感「${refSourceName}」` : "已添加参考图"}</p>
                <p className="mt-1">生成结果将直接呈现在图中手部指甲上</p>
              </div>
              <button onClick={removeReferenceImage} className="rounded-full border border-pink-100 bg-pink-50/65 px-3 py-1.5 text-xs text-[#a34b3f] transition hover:bg-[var(--surface)]">移除</button>
            </div>
          ) : (
            <label className="mt-3 flex h-20 w-full cursor-pointer flex-col items-center justify-center gap-1 rounded-2xl border border-dashed border-pink-200 bg-[var(--surface)] text-xs text-[#6f7066] transition hover:border-pink-300 hover:bg-[var(--surface)]">
              <Icon name="camera" className="h-6 w-6" />
              点击上传手部照片
              <input type="file" accept="image/*" className="hidden" onChange={(event) => { const file = event.target.files?.[0]; if (file) handleReferenceFile(file); event.target.value = ""; }} />
            </label>
          )}
          {referenceError ? <p className="mt-2 text-[11px] text-red-400">{referenceError}</p> : <p className="mt-2 text-[11px] text-[#67685f]">上传的图片会发送给 AI 服务，仅用于本次生成；不上传则按文字直接生成</p>}
          <p className="mt-5 text-xs font-medium text-[#67685f]">从一个风格开始</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {AI_STYLE_PROMPTS.map((group) => <button key={group.label} onClick={() => handleStyleClick(group.label)} className="inline-flex min-h-11 items-center rounded-full border border-pink-100 bg-pink-50/65 px-3 py-2 text-xs text-[#a34b3f] transition hover:-translate-y-0.5 hover:bg-[var(--surface)] hover:shadow-sm">{group.label}</button>)}
          </div>
          <div className="mt-5 space-y-4">
            <div>
              <p className="text-xs font-medium text-[#67685f]">生成引擎</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {ENGINE_OPTIONS.map((opt) => (
                  <button key={opt.value} type="button" aria-pressed={engine === opt.value} onClick={() => handleEngineClick(opt.value)} className={chipClass(engine === opt.value)}>{opt.label}</button>
                ))}
              </div>
            </div>
            <div>
              <p className="text-xs font-medium text-[#67685f]">画面比例</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {AI_IMAGE_RATIOS.map((r) => (
                  <button key={r} type="button" aria-pressed={ratio === r} onClick={() => setRatio(r)} className={chipClass(ratio === r)}>{r}</button>
                ))}
              </div>
            </div>
            <div>
              <p className="text-xs font-medium text-[#67685f]">输出尺寸</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {engineSizeOptions(engine).map((s) => (
                  <button key={s} type="button" aria-pressed={size === s} onClick={() => setSize(s)} className={chipClass(size === s)}>{s}</button>
                ))}
              </div>
            </div>
            <p className="text-[11px] text-[#67685f]">输出尺寸：{resolvedDimension.replace("x", " × ")}（{size} · {ratio}）</p>
          </div>
          <button onClick={handleGenerate} disabled={status === "loading" || !prompt.trim() || promptOverLimit} className="mt-7 flex h-13 w-full items-center justify-center gap-2 rounded-2xl bg-[var(--coral)] text-sm font-semibold text-white shadow-[var(--neu-out-sm)] transition hover:-translate-y-0.5 hover:shadow-[var(--neu-out-md)] active:scale-[.98] disabled:cursor-not-allowed disabled:opacity-40">
            {status === "loading" ? <span key="btn-loading" className="fade-in-up inline-flex items-center gap-2"><span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />正在生成设计</span> : <span key="btn-idle" className="fade-in-up inline-flex items-center gap-2">生成我的美甲设计 <span aria-hidden="true"><Icon name="sparkles" className="h-4 w-4" /></span></span>}
          </button>
          <p className="mt-4 text-center text-[11px] text-[#67685f]">文字描述始终发送给 AI 服务；仅当你上传参考图时，图片也会发送并只用于本次生成；「用户改进计划」可在隐私页管理</p>
        </section>
        <section className="relative flex min-h-[390px] items-center justify-center overflow-hidden border-t border-[var(--line)] bg-[var(--paper)] p-5 lg:border-l lg:border-t-0 sm:p-8">
          {status === "success" && imageUrl ? (
            renderResultBlock(imageUrl)
          ) : status === "error" && imageUrl ? (
            // 再生成失败：不清上一版结果（§6.3），错误以反馈区呈现在图上方。
            <div key="error-keep" className="fade-in-up w-full">
              <div className="mx-auto mb-3 max-w-md">
                <StatusRegion
                  status="error"
                  severity="error"
                  message={`本次生成未完成：${errorMsg || AI_ERROR_MESSAGES.unknown}下方仍为上一版结果。`}
                />
              </div>
              {renderResultBlock(imageUrl)}
            </div>
          ) : status === "cancelled" && imageUrl ? (
            <div key="cancelled-keep" className="fade-in-up w-full">
              <div className="mx-auto mb-3 max-w-md">
                <StatusRegion
                  status="success"
                  severity="warning"
                  message="已取消本次生成，当前设置已保留；下方仍为上一版结果。"
                />
              </div>
              {renderResultBlock(imageUrl)}
            </div>
          ) : status === "error" ? (
            <div key="error" className="fade-in-up max-w-sm rounded-3xl border border-red-100 bg-[var(--surface)] p-6 text-center shadow-lg">
              <Icon name="circle" className="h-8 w-8 text-red-400" />
              <h2 className="mt-3 font-semibold text-red-500">生成没有完成</h2>
              <div className="mt-2">
                <StatusRegion status="error" severity="error" message={errorMsg || AI_ERROR_MESSAGES.unknown} />
              </div>
              <button onClick={handleGenerate} className="mt-4 text-xs font-medium text-red-500 underline">再试一次</button>
            </div>
          ) : status === "cancelled" ? (
            <div key="cancelled" className="fade-in-up max-w-sm rounded-3xl border border-[var(--line)] bg-[var(--surface)] p-6 text-center shadow-lg">
              <Icon name="circle" className="h-8 w-8 text-[var(--muted)]" />
              <h2 className="mt-3 font-semibold text-[var(--ink)]">已取消本次生成</h2>
              <p className="mt-2 text-xs leading-5 text-[var(--muted)]">当前设置已保留，可随时再试。</p>
              <button onClick={handleGenerate} className="mt-4 text-xs font-medium text-[#ac5145] underline">再试一次</button>
            </div>
          ) : status === "loading" ? (
            <>
              <div className="shimmer-sweep pointer-events-none" />
              <div key="loading" role="status" aria-live="polite" className="fade-in-up text-center">
                <div className="mx-auto grid h-28 w-28 place-items-center rounded-[32px] bg-[var(--surface)] shadow-[var(--neu-out-md)] "><Icon name="sparkles" className="shimmer-spark h-10 w-10 text-[#ac5145]" /></div>
                <h2 className="mt-6 font-[var(--serif)] text-xl font-medium text-[var(--ink)]">正在凝聚你的灵感…</h2>
                <p className="mt-2 text-xs text-[var(--muted)]">色彩与材质正在生成，请稍候</p>
              </div>
              {/* 等待计数与取消按钮在 live region 之外，读屏不会反复播报秒数。 */}
              <div className="absolute inset-x-0 bottom-6 flex flex-col items-center gap-2">
                <p aria-hidden="true" className="text-[11px] text-[#6f7066]">已等待 {elapsedSeconds} 秒</p>
                <button type="button" onClick={handleCancelGenerate} className="rounded-full border border-[var(--line)] bg-[var(--surface)] px-4 py-2 text-xs font-medium text-[#a34b3f] transition hover:bg-pink-50/65">
                  取消生成
                </button>
              </div>
            </>
          ) : (
            <div key="idle" className="fade-in-up text-center">
              <div className="mx-auto grid h-28 w-28 place-items-center rounded-[32px] bg-[var(--surface)] shadow-[var(--neu-out-md)] "><Icon name="diamond" className="h-10 w-10 text-[var(--coral)]" /></div>
              <h2 className="mt-6 font-[var(--serif)] text-xl font-medium text-[var(--ink)]">你的设计将在这里出现</h2>
              <p className="mt-2 text-xs text-[var(--muted)]">描述越具体，生成结果越贴近想象</p>
            </div>
          )}
        </section>
      </div>
    </AppShell>
  );
}
