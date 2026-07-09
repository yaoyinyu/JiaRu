"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import dynamic from "next/dynamic";
import { FlowingShell, GlassPanel, PageHero } from "@/components/FlowingShell";
import { ArView } from "@/components/ArView";
import { FINGER_NAMES, PRESET_COLORS } from "@/lib/utils";
import { disposeAllTextures } from "@/lib/texture";
import type { NailAssignment } from "@/components/NailArtPicker";

const TextureCropper = dynamic(() => import("@/components/TextureCropper"), {
  ssr: false,
});

const NailArtPicker = dynamic(() => import("@/components/NailArtPicker"), {
  ssr: false,
});

export default function ArTryonPage() {
  const [nailColors, setNailColors] = useState([
    "#E8A0BF", "#E8A0BF", "#E8A0BF", "#E8A0BF", "#E8A0BF",
  ]);
  const [nailTextures, setNailTextures] = useState<(ImageBitmap | null)[]>([
    null, null, null, null, null,
  ]);
  const [activeFinger, setActiveFinger] = useState(0);
  const [mode, setMode] = useState<"color" | "texture">("color");
  const [showCropper, setShowCropper] = useState(false);
  const [showNailPicker, setShowNailPicker] = useState(false);
  const [uploadedPhotoUrl, setUploadedPhotoUrl] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

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

  const handleTextureUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!validateImageFile(file)) return;

    const url = prepareUploadUrl(file);
    setUploadedPhotoUrl(url);
    setShowCropper(true);
    e.target.value = "";
  };

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
    <FlowingShell>
      <PageHero
        eyebrow="AR 试戴"
        title="实时预览指尖效果"
        description="打开摄像头，让颜色和纹理跟随手指移动；也可以上传参考图自动提取多枚美甲纹理。"
      />

<<<<<<< HEAD
      <GlassPanel className="overflow-hidden p-3">
        <ArView nailColors={nailColors} nailTextures={nailTextures} mode={mode} />
      </GlassPanel>
=======
      {!isStarted && (
        <GlassPanel className="p-6 text-center">
          <div className="mx-auto mb-5 flex h-40 w-40 items-center justify-center rounded-full border border-white/60 bg-gradient-to-br from-[#fff5f7] via-white to-[#ffe4ec] text-6xl shadow-xl shadow-pink-200/30">
            💅
          </div>
          <button
            onClick={() => setIsStarted(true)}
            className="h-14 w-full rounded-2xl bg-gradient-to-b from-[#f0b8d0] to-[#d4749d] text-base font-semibold text-white shadow-[0_8px_24px_rgba(212,116,157,0.2)] transition hover:-translate-y-0.5 hover:shadow-[0_12px_32px_rgba(212,116,157,0.24)] active:scale-[0.98]"
          >
            开启摄像头
          </button>
          <p className="mt-4 text-xs leading-5 text-gray-400">
            需要摄像头权限。画面仅在本地实时处理，不录制也不上传。
          </p>
        </GlassPanel>
      )}

      {isStarted && (
        <GlassPanel className="overflow-hidden p-3">
          <ArView nailColors={nailColors} nailTextures={nailTextures} mode={mode} />
        </GlassPanel>
      )}
>>>>>>> b6786dd9403a34a2b35448e7c2ebda8e7f2d6608

      <GlassPanel className="mt-4 p-4">
        <div className="mb-4 flex gap-1 rounded-2xl bg-pink-50/80 p-1">
          <button
            onClick={() => setMode("color")}
            className={`flex-1 rounded-xl py-2 text-xs transition-all ${
              mode === "color"
                ? "bg-white font-semibold text-[#d4749d] shadow-sm"
                : "text-gray-400"
            }`}
          >
            纯色
          </button>
          <button
            onClick={() => setMode("texture")}
            className={`flex-1 rounded-xl py-2 text-xs transition-all ${
              mode === "texture"
                ? "bg-white font-semibold text-[#d4749d] shadow-sm"
                : "text-gray-400"
            }`}
          >
            纹理
          </button>
        </div>

        <div className="mb-4 flex flex-wrap justify-center gap-2">
          {FINGER_NAMES.map((name, index) => (
            <button
              key={name}
              onClick={() => setActiveFinger(index)}
              className={`relative rounded-full px-3 py-1.5 text-xs transition-all ${
                activeFinger === index
                  ? "bg-[#d4749d] text-white shadow-sm"
                  : "bg-white/70 text-gray-400 hover:bg-pink-50"
              }`}
            >
              {name}
              {nailTextures[index] && (
                <span className="absolute -right-1 -top-1 h-2.5 w-2.5 rounded-full border border-white bg-green-400" />
              )}
            </button>
          ))}
        </div>

        {mode === "texture" && (
          <div className="text-center">
            {nailTextures[activeFinger] ? (
              <div className="mb-3 flex items-center justify-center gap-3">
                <div className="flex h-12 w-12 items-center justify-center overflow-hidden rounded-xl border-2 border-pink-300 bg-pink-50">
                  <TextureThumb bitmap={nailTextures[activeFinger]!} size={48} />
                </div>
                <div className="text-left">
                  <p className="text-xs font-medium text-[#4a4a4a]">{FINGER_NAMES[activeFinger]}纹理</p>
                  <button
                    onClick={() => removeTexture(activeFinger)}
                    className="text-xs text-red-400 hover:text-red-500"
                  >
                    移除
                  </button>
                </div>
              </div>
            ) : (
              <p className="mb-3 text-xs text-gray-400">{FINGER_NAMES[activeFinger]} 暂未设置纹理</p>
            )}

            <div className="flex flex-wrap justify-center gap-2">
              <label className="cursor-pointer rounded-full bg-pink-50 px-3 py-1.5 text-xs font-medium text-[#d4749d] transition-colors hover:bg-pink-100">
                上传单枚纹理
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  onChange={handleTextureUpload}
                  className="hidden"
                />
              </label>
              <label className="cursor-pointer rounded-full bg-purple-50 px-3 py-1.5 text-xs font-medium text-purple-500 transition-colors hover:bg-purple-100">
                多纹理提取
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
                  className="rounded-full bg-pink-50 px-3 py-1.5 text-xs font-medium text-[#d4749d] transition-colors hover:bg-pink-100"
                >
                  应用到全部
                </button>
              )}
            </div>
          </div>
        )}

        {mode === "color" && (
          <>
            <div className="mb-4 flex items-center justify-center gap-3">
              <div
                className="h-8 w-8 rounded-full border-2 border-white shadow-sm"
                style={{ backgroundColor: nailColors[activeFinger] }}
              />
              <span className="text-xs text-gray-400">{FINGER_NAMES[activeFinger]}颜色</span>
              <button
                onClick={applyToAll}
                className="text-xs font-medium text-[#d4749d] underline underline-offset-4 hover:text-[#b95f86]"
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

            <div className="mt-4 flex items-center justify-center gap-2">
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
      </GlassPanel>

      {showCropper && uploadedPhotoUrl && (
        <TextureCropper imageUrl={uploadedPhotoUrl} onConfirm={handleCropConfirm} onCancel={handleCropCancel} />
      )}

      {showNailPicker && uploadedPhotoUrl && (
        <NailArtPicker imageUrl={uploadedPhotoUrl} onConfirm={handlePickingConfirm} onCancel={handlePickingCancel} />
      )}

      <div className="mt-4 space-y-2">
        <GlassPanel className="p-3 text-center">
          <p className="text-xs leading-5 text-gray-400">摄像头画面仅在内存中处理，不录制，也不会上传。</p>
        </GlassPanel>
        <GlassPanel className="p-3 text-center">
          <p className="text-xs leading-5 text-gray-400">首次加载可能需要几秒，建议在光线充足的环境使用。</p>
        </GlassPanel>
      </div>
    </FlowingShell>
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

  return <canvas ref={ref} width={size} height={size} className="h-full w-full object-contain" />;
<<<<<<< HEAD
}
=======
}
>>>>>>> b6786dd9403a34a2b35448e7c2ebda8e7f2d6608
