"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import dynamic from "next/dynamic";
import { AppShell } from "@/components/AppShell";
import { ArView } from "@/components/ArView";
import { PRESET_COLORS } from "@/lib/utils";
import { disposeAllTextures } from "@/lib/texture";
import type { NailAssignment } from "@/components/NailArtPicker";

const TextureCropper = dynamic(() => import("@/components/TextureCropper"), {
  ssr: false,
});

const NailArtPicker = dynamic(() => import("@/components/NailArtPicker"), {
  ssr: false,
});

const FINGER_NAMES = ["拇指", "食指", "中指", "无名指", "小指"];

export default function ArTryonPage() {
  const [nailColors, setNailColors] = useState([
    "#E8A0BF", "#E8A0BF", "#E8A0BF", "#E8A0BF", "#E8A0BF",
  ]);
  const [nailTextures, setNailTextures] = useState<(ImageBitmap | null)[]>([
    null, null, null, null, null,
  ]);
  const [activeFinger, setActiveFinger] = useState(0);
  const [isStarted, setIsStarted] = useState(false);
  const [mode, setMode] = useState<"color" | "texture">("color");
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

  const validateImageFile = (file: File): boolean => {
    if (!["image/png", "image/jpeg", "image/webp"].includes(file.type)) {
      alert("仅支持 PNG、JPG、WebP 格式的图片");
      return false;
    }
    if (file.size > 10 * 1024 * 1024) {
      alert("图片大小不能超过 10MB");
      return false;
    }
    return true;
  };

  const prepareUploadUrl = (file: File) => {
    if (uploadedPhotoUrl) {
      URL.revokeObjectURL(uploadedPhotoUrl);
    }
    return URL.createObjectURL(file);
  };

  // 单纹理快捷裁剪上传。
  const handleTextureUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!validateImageFile(file)) return;

    const url = prepareUploadUrl(file);
    setUploadedPhotoUrl(url);
    setShowCropper(true);
    e.target.value = "";
  };

  // 多纹理参考图上传。
  const handlePatternUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!validateImageFile(file)) return;

    const url = prepareUploadUrl(file);
    setUploadedPhotoUrl(url);
    setShowNailPicker(true);
    e.target.value = "";
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
      eyebrow="Live Try-on"
      title="让每一次抬手，都提前看见效果"
      description="实时追踪手部动作，让颜色与纹理自然贴合指甲。所有摄像头画面都只在本地内存中处理。"
    >
      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_390px]">
        <section className="overflow-hidden rounded-[30px] border border-white/80 bg-white/55 p-3 shadow-[0_26px_80px_rgba(71,49,60,.12)] backdrop-blur-2xl sm:p-5">
        {!isStarted && (
          <div className="mx-auto flex w-full max-w-md flex-col items-center gap-4 py-8">
            <div className="flex h-40 w-40 items-center justify-center rounded-full bg-gradient-to-br from-pink-100 to-purple-100 shadow-inner">
              <span className="text-6xl">💅</span>
            </div>
            <button
              onClick={() => setIsStarted(true)}
              className="h-14 w-full rounded-2xl bg-gradient-to-r from-[#E8A0BF] to-[#D4749D] text-base font-medium text-white shadow-md transition-all hover:shadow-lg active:scale-[0.98]"
            >
              📷 开启摄像头
            </button>
            <p className="text-center text-xs text-gray-300">
              需要摄像头权限 · 仅在本地处理，不录制也不会上传。
            </p>
          </div>
        )}

        {isStarted && (
          <ArView nailColors={nailColors} nailTextures={nailTextures} mode={mode} />
        )}
        </section>
        <aside className="rounded-[28px] border border-white/80 bg-white/68 p-5 shadow-[0_22px_65px_rgba(91,59,74,.09)] backdrop-blur-2xl xl:sticky xl:top-24">
          <div className="mb-5">
            <p className="text-xs font-semibold uppercase tracking-[.16em] text-[#CF6F99]">Style controls</p>
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
              🎨 纯色
            </button>
            <button
              onClick={() => setMode("texture")}
              className={`flex-1 rounded-lg py-1.5 text-xs transition-all ${
                mode === "texture"
                  ? "bg-white text-[#E8A0BF] font-medium shadow-sm"
                  : "text-gray-400"
              }`}
            >
              🖼️ 纹理
            </button>
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
                  📷 上传美甲照片
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/png,image/jpeg,image/webp"
                    onChange={handleTextureUpload}
                    className="hidden"
                  />
                </label>
                <label className="cursor-pointer rounded-full bg-purple-50 px-3 py-1.5 text-xs text-purple-500 transition-colors hover:bg-purple-100">
                  ✨ 多纹理提取
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
          <div className="rounded-2xl border border-white/75 bg-white/55 p-4 text-xs leading-5 text-[#94898F] backdrop-blur-xl">🔒 摄像头画面仅在内存中处理，不录制，也不会上传。</div>
          <div className="rounded-2xl border border-white/75 bg-white/55 p-4 text-xs leading-5 text-[#94898F] backdrop-blur-xl">💡 首次加载大约需要 5-10 秒，建议在光线充足的环境使用。</div>
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
