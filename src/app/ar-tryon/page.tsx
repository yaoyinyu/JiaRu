"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import dynamic from "next/dynamic";
import { AppShell } from "@/components/AppShell";
import { Icon } from "@/components/Icon";
import { ArView, type NailFitAdjustment } from "@/components/ArView";
import { PRESET_COLORS } from "@/lib/utils";
import { disposeAllTextures } from "@/lib/texture";
import type { NailAssignment } from "@/components/NailArtPicker";
import { validateImageUpload } from "@/lib/image-upload-validation";

const TextureCropper = dynamic(() => import("@/components/TextureCropper"), {
  ssr: false,
});

const NailArtPicker = dynamic(() => import("@/components/NailArtPicker"), {
  ssr: false,
});

const FINGER_NAMES = ["拇指", "食指", "中指", "无名指", "小指"];
const DEFAULT_NAIL_FIT: NailFitAdjustment = {
  lengthScale: 1,
  widthScale: 1,
  rootOffset: 0,
};

function createDefaultNailFits(): NailFitAdjustment[] {
  return Array.from({ length: 5 }, () => ({ ...DEFAULT_NAIL_FIT }));
}

export default function ArTryonPage() {
  const [nailColors, setNailColors] = useState([
    "#E8A0BF", "#E8A0BF", "#E8A0BF", "#E8A0BF", "#E8A0BF",
  ]);
  const [nailTextures, setNailTextures] = useState<(ImageBitmap | null)[]>([
    null, null, null, null, null,
  ]);
  const [activeFinger, setActiveFinger] = useState(0);
  const [mode, setMode] = useState<"color" | "texture">("color");
  const [nailFits, setNailFits] = useState<NailFitAdjustment[]>(createDefaultNailFits);
  const [showCropper, setShowCropper] = useState(false);
  const [showNailPicker, setShowNailPicker] = useState(false);
  const [uploadedPhotoUrl, setUploadedPhotoUrl] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // 用 ref 跟踪最新纹理和图片 URL，确保组件卸载时正确释放资源。
  const texturesRef = useRef(nailTextures);
  const photoUrlRef = useRef(uploadedPhotoUrl);

  useEffect(() => {
    texturesRef.current = nailTextures;
  }, [nailTextures]);

  useEffect(() => {
    photoUrlRef.current = uploadedPhotoUrl;
  }, [uploadedPhotoUrl]);

  const hasAnyTexture = nailTextures.some((texture) => texture != null);
  const activeNailFit = nailFits[activeFinger] ?? DEFAULT_NAIL_FIT;

  const updateActiveNailFit = (patch: Partial<NailFitAdjustment>) => {
    setNailFits((current) => current.map((fit, index) => (
      index === activeFinger ? { ...fit, ...patch } : fit
    )));
  };

  useEffect(() => {
    return () => {
      disposeAllTextures(texturesRef.current);
      const url = photoUrlRef.current;
      if (url) URL.revokeObjectURL(url);
    };
  }, []);

  const changeColor = (color: string) => {
    const updated = [...nailColors];
    updated[activeFinger] = color;
    setNailColors(updated);
  };

  const applyToAll = () => {
    setNailColors(Array(5).fill(nailColors[activeFinger]));
  };

  const prepareUploadUrl = (file: File) => {
    if (uploadedPhotoUrl) {
      URL.revokeObjectURL(uploadedPhotoUrl);
    }
    return URL.createObjectURL(file);
  };

  // 单纹理快捷裁剪上传。
  const handleTextureUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";
    const validation = await validateImageUpload(file);
    if (!validation.ok) {
      alert(validation.message);
      return;
    }

    const url = prepareUploadUrl(file);
    setUploadedPhotoUrl(url);
    setShowCropper(true);
  };

  // 多纹理参考图上传。
  const handlePatternUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";
    const validation = await validateImageUpload(file);
    if (!validation.ok) {
      alert(validation.message);
      return;
    }

    const url = prepareUploadUrl(file);
    setUploadedPhotoUrl(url);
    setShowNailPicker(true);
  };

  const handleCropConfirm = useCallback(
    (bitmap: ImageBitmap) => {
      const old = nailTextures[activeFinger];
      const updated = [...nailTextures];
      updated[activeFinger] = bitmap;

      // 仅当旧纹理没有被其他手指复用时才释放。
      if (old && !updated.some((texture) => texture === old)) {
        old.close();
      }

      setNailTextures(updated);
      setShowCropper(false);
      setMode("texture");
    },
    [activeFinger, nailTextures]
  );

  const handleCropCancel = useCallback(() => {
    setShowCropper(false);
  }, []);

  const handlePickingConfirm = useCallback(
    (assignments: NailAssignment[]) => {
      const updated = [...nailTextures];

      for (const assignment of assignments) {
        const old = updated[assignment.finger];
        if (old) {
          const otherRefs = updated.some(
            (texture, index) => index !== assignment.finger && texture === old
          );
          if (!otherRefs) old.close();
        }
        updated[assignment.finger] = assignment.texture;
      }

      setNailTextures(updated);
      setShowNailPicker(false);
      setMode("texture");
    },
    [nailTextures]
  );

  const handlePickingCancel = useCallback(() => {
    setShowNailPicker(false);
  }, []);

  const applyTextureToAll = () => {
    const activeTexture = nailTextures[activeFinger];
    if (!activeTexture) {
      alert("当前手指还没有设置纹理");
      return;
    }

    const updated = nailTextures.map((texture, index) => {
      if (index === activeFinger) return texture;
      if (texture && texture !== activeTexture) {
        const otherRefs = nailTextures.some(
          (otherTexture, otherIndex) =>
            otherIndex !== index &&
            otherIndex !== activeFinger &&
            otherTexture === texture
        );
        if (!otherRefs) texture.close();
      }
      return activeTexture;
    });

    setNailTextures(updated);
  };

  const removeTexture = (fingerIndex: number) => {
    const texture = nailTextures[fingerIndex];
    const updated = [...nailTextures];
    updated[fingerIndex] = null;

    if (texture && !updated.some((item) => item === texture)) {
      texture.close();
    }

    setNailTextures(updated);
  };

  return (
    <AppShell
      wide
      eyebrow="实时试戴"
      title="让每一次抬手，都提前看见效果"
      description="实时追踪手部动作，让颜色与纹理自然贴合指甲。所有摄像头画面都只在本地内存中处理。"
    >
      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_390px]">
        <section className="overflow-hidden rounded-[30px] border border-white/80 bg-white/55 p-3 shadow-[0_26px_80px_rgba(71,49,60,.12)] backdrop-blur-2xl sm:p-5">
          <ArView
            nailColors={nailColors}
            nailTextures={nailTextures}
            mode={mode}
            nailAdjustments={nailFits}
          />
        </section>
        <aside className="rounded-[28px] border border-white/80 bg-white/68 p-5 shadow-[0_22px_65px_rgba(91,59,74,.09)] backdrop-blur-2xl xl:sticky xl:top-24">
          <div className="mb-5">
            <p className="text-xs font-semibold tracking-[.16em] text-[#CF6F99]">试戴控制</p>
            <h2 className="mt-1 text-lg font-semibold text-[#4A4447]">试戴设置</h2>
          </div>
        <div className="w-full">
          <div className="mb-3 flex gap-1 rounded-xl bg-pink-50 p-1">
            <button
              onClick={() => setMode("color")}
              className={`flex-1 rounded-lg py-1.5 text-xs transition-all ${
                mode === "color"
                  ? "bg-white text-[#E8A0BF] font-medium shadow-sm"
                  : "text-gray-400"
              }`}
            >
              <span className="inline-flex items-center justify-center gap-1.5"><Icon name="palette" className="h-4 w-4" />纯色</span>
            </button>
            <button
              onClick={() => setMode("texture")}
              className={`flex-1 rounded-lg py-1.5 text-xs transition-all ${
                mode === "texture"
                  ? "bg-white text-[#E8A0BF] font-medium shadow-sm"
                  : "text-gray-400"
              }`}
            >
              <span className="inline-flex items-center justify-center gap-1.5"><Icon name="image" className="h-4 w-4" />纹理</span>
            </button>
          </div>

          <div className="mb-4 rounded-2xl border border-pink-100 bg-white/70 p-3">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-xs font-medium text-[#665C61]">
                {FINGER_NAMES[activeFinger]}逐指校准
              </span>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => updateActiveNailFit(DEFAULT_NAIL_FIT)}
                  className="text-[11px] text-[#CF6F99] hover:text-[#B85C86]"
                >
                  重置本指
                </button>
                <button
                  type="button"
                  onClick={() => setNailFits(createDefaultNailFits())}
                  className="text-[11px] text-gray-400 hover:text-gray-600"
                >
                  重置全部
                </button>
              </div>
            </div>
            <label className="grid grid-cols-[42px_1fr_42px] items-center gap-2 text-[11px] text-gray-500">
              <span>长度</span>
              <input
                aria-label={`${FINGER_NAMES[activeFinger]}甲面长度`}
                type="range"
                min="75"
                max="140"
                step="1"
                value={Math.round(activeNailFit.lengthScale * 100)}
                onChange={(event) => updateActiveNailFit({
                  lengthScale: Number(event.target.value) / 100,
                })}
                className="accent-[#D4749D]"
              />
              <span className="text-right">{Math.round(activeNailFit.lengthScale * 100)}%</span>
            </label>
            <label className="mt-2 grid grid-cols-[42px_1fr_42px] items-center gap-2 text-[11px] text-gray-500">
              <span>宽度</span>
              <input
                aria-label={`${FINGER_NAMES[activeFinger]}甲面宽度`}
                type="range"
                min="70"
                max="145"
                step="1"
                value={Math.round(activeNailFit.widthScale * 100)}
                onChange={(event) => updateActiveNailFit({
                  widthScale: Number(event.target.value) / 100,
                })}
                className="accent-[#D4749D]"
              />
              <span className="text-right">{Math.round(activeNailFit.widthScale * 100)}%</span>
            </label>
            <label className="mt-2 grid grid-cols-[42px_1fr_42px] items-center gap-2 text-[11px] text-gray-500">
              <span>位置</span>
              <input
                aria-label="甲面位置"
                type="range"
                min="-20"
                max="20"
                step="1"
                value={Math.round(activeNailFit.rootOffset * 100)}
                onChange={(event) => updateActiveNailFit({
                  rootOffset: Number(event.target.value) / 100,
                })}
                className="accent-[#D4749D]"
              />
              <span className="text-right">
                {activeNailFit.rootOffset === 0
                  ? "居中"
                  : activeNailFit.rootOffset > 0
                    ? `指根${Math.round(activeNailFit.rootOffset * 100)}`
                    : `甲尖${Math.round(-activeNailFit.rootOffset * 100)}`}
              </span>
            </label>
          </div>

          <div className="mb-3 flex justify-center gap-2">
            {FINGER_NAMES.map((name, index) => (
              <button
                key={index}
                onClick={() => setActiveFinger(index)}
                className={`relative rounded-full px-3 py-1.5 text-xs transition-all ${
                  activeFinger === index
                    ? "bg-[#E8A0BF] text-white shadow-sm"
                    : "bg-pink-50 text-gray-400 hover:bg-pink-100"
                }`}
              >
                {name}
                {nailTextures[index] && (
                  <span className="absolute -top-1 -right-1 h-2.5 w-2.5 rounded-full border border-white bg-green-400" />
                )}
              </button>
            ))}
          </div>

          {mode === "texture" && (
            <div className="mb-3 text-center">
              {nailTextures[activeFinger] ? (
                <div className="mb-2 flex items-center justify-center gap-3">
                  <div className="flex h-12 w-12 items-center justify-center overflow-hidden rounded-xl border-2 border-pink-300 bg-pink-50">
                    <TextureThumb bitmap={nailTextures[activeFinger]!} size={48} />
                  </div>
                  <div className="text-left">
                    <p className="text-xs font-medium">{FINGER_NAMES[activeFinger]}纹理</p>
                    <button
                      onClick={() => removeTexture(activeFinger)}
                      className="text-xs text-red-400 hover:text-red-500"
                    >
                      移除
                    </button>
                  </div>
                </div>
              ) : (
                <p className="mb-2 text-xs text-gray-400">
                  {FINGER_NAMES[activeFinger]}暂未设置纹理
                </p>
              )}

              <div className="flex justify-center gap-2">
                <label className="cursor-pointer rounded-full bg-pink-50 px-3 py-1.5 text-xs text-[#E8A0BF] transition-colors hover:bg-pink-100">
                  <span className="inline-flex items-center justify-center gap-1.5"><Icon name="camera" className="h-4 w-4" />上传美甲照片</span>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/png,image/jpeg,image/webp"
                    onChange={handleTextureUpload}
                    className="hidden"
                  />
                </label>
                <label className="cursor-pointer rounded-full bg-purple-50 px-3 py-1.5 text-xs text-purple-500 transition-colors hover:bg-purple-100">
                  <span className="inline-flex items-center justify-center gap-1.5"><Icon name="sparkles" className="h-4 w-4" />多纹理提取</span>
                  <input
                    type="file"
                    accept="image/png,image/jpeg,image/webp"
                    onChange={handlePatternUpload}
                    className="hidden"
                  />
                </label>
                {hasAnyTexture && (
                  <button
                    onClick={applyTextureToAll}
                    className="rounded-full bg-pink-50 px-3 py-1.5 text-xs text-[#E8A0BF] transition-colors hover:bg-pink-100"
                  >
                    应用到全部
                  </button>
                )}
              </div>
            </div>
          )}

          {mode === "color" && (
            <>
              <div className="mb-3 flex items-center justify-center gap-3">
                <div
                  className="h-8 w-8 rounded-full border-2 border-gray-100 shadow-sm"
                  style={{ backgroundColor: nailColors[activeFinger] }}
                />
                <span className="text-xs text-gray-400">{FINGER_NAMES[activeFinger]}颜色</span>
                <button
                  onClick={applyToAll}
                  className="text-xs text-[#E8A0BF] underline hover:text-[#D4749D]"
                >
                  应用到全部
                </button>
              </div>

              <div className="flex flex-wrap justify-center gap-2">
                {PRESET_COLORS.filter((_, index) => index < 12).map((item) => (
                  <button
                    key={item.name}
                    title={item.name}
                    onClick={() => changeColor(item.color)}
                    className={`h-9 w-9 rounded-full border-2 shadow-sm transition-all hover:scale-110 ${
                      nailColors[activeFinger] === item.color
                        ? "scale-110 ring-2 ring-pink-400 ring-offset-2"
                        : ""
                    } ${
                      item.color === "#FFFFFF" || item.name === "透明"
                        ? "border-gray-200"
                        : "border-transparent"
                    }`}
                    style={{ backgroundColor: item.color }}
                  />
                ))}
              </div>

              <div className="mt-3 flex items-center justify-center gap-2">
                <span className="text-xs text-gray-400">自定义</span>
                <input
                  type="color"
                  value={nailColors[activeFinger]}
                  onChange={(e) => changeColor(e.target.value)}
                  className="h-9 w-9 cursor-pointer rounded-full border-0 p-0"
                />
              </div>
            </>
          )}
        </div>
        </aside>
      </div>

        {showCropper && uploadedPhotoUrl && (
          <TextureCropper
            imageUrl={uploadedPhotoUrl}
            onConfirm={handleCropConfirm}
            onCancel={handleCropCancel}
          />
        )}

        {showNailPicker && uploadedPhotoUrl && (
          <NailArtPicker
            imageUrl={uploadedPhotoUrl}
            onConfirm={handlePickingConfirm}
            onCancel={handlePickingCancel}
          />
        )}

        <div className="mx-auto mt-5 grid w-full max-w-3xl gap-3 text-center sm:grid-cols-2">
          <div className="rounded-2xl border border-white/75 bg-white/55 p-4 text-xs leading-5 text-[#94898F] backdrop-blur-xl"><Icon name="lock" className="mr-1.5 inline h-4 w-4 align-[-3px]" />摄像头画面默认仅在内存中处理，不录制；「用户改进计划」可在隐私页关闭</div>
          <div className="rounded-2xl border border-white/75 bg-white/55 p-4 text-xs leading-5 text-[#94898F] backdrop-blur-xl"><Icon name="lightbulb" className="mr-1.5 inline h-4 w-4 align-[-3px]" />首次加载大约需要 5-10 秒，建议在光线充足的环境使用。</div>
        </div>
    </AppShell>
  );
}

function TextureThumb({
  bitmap,
  size,
}: {
  bitmap: ImageBitmap;
  size: number;
}) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const scale = Math.min(size / bitmap.width, size / bitmap.height);
    const dw = bitmap.width * scale;
    const dh = bitmap.height * scale;
    const dx = (size - dw) / 2;
    const dy = (size - dh) / 2;

    ctx.clearRect(0, 0, size, size);
    ctx.drawImage(bitmap, dx, dy, dw, dh);
  }, [bitmap, size]);

  return (
    <canvas
      ref={ref}
      width={size}
      height={size}
      className="h-full w-full object-contain"
    />
  );
}
