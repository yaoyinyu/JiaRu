"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import dynamic from "next/dynamic";
import { Header } from "@/components/Header";
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

  // 用 ref 追踪以确保卸载时正确释放（在 useEffect 中同步，避免渲染期间更新 ref）
  const texturesRef = useRef(nailTextures);
  const photoUrlRef = useRef(uploadedPhotoUrl);

  useEffect(() => {
    texturesRef.current = nailTextures;
  }, [nailTextures]);

  useEffect(() => {
    photoUrlRef.current = uploadedPhotoUrl;
  }, [uploadedPhotoUrl]);

  const hasAnyTexture = nailTextures.some((t) => t != null);

  // ── 清理 ──

  useEffect(() => {
    return () => {
      const tex = texturesRef.current;
      const url = photoUrlRef.current;
      disposeAllTextures(tex);
      if (url) URL.revokeObjectURL(url);
    };
  }, []);

  // ── 颜色操作 ──

  const changeColor = (color: string) => {
    const updated = [...nailColors];
    updated[activeFinger] = color;
    setNailColors(updated);
  };

  const applyToAll = () => {
    const same = Array(5).fill(nailColors[activeFinger]);
    setNailColors(same);
  };

  // ── 纹理上传（单纹理快捷裁剪）──

  const handleTextureUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!["image/png", "image/jpeg", "image/webp"].includes(file.type)) {
      alert("仅支持 PNG、JPG、WebP 格式的图片");
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      alert("图片大小不能超过 10MB");
      return;
    }

    if (uploadedPhotoUrl) URL.revokeObjectURL(uploadedPhotoUrl);

    const url = URL.createObjectURL(file);
    setUploadedPhotoUrl(url);
    setShowCropper(true);
    e.target.value = "";
  };

  // ── 多纹理参考图上传播 ──

  const handlePatternUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!["image/png", "image/jpeg", "image/webp"].includes(file.type)) {
      alert("仅支持 PNG、JPG、WebP 格式的图片");
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      alert("图片大小不能超过 10MB");
      return;
    }

    if (uploadedPhotoUrl) URL.revokeObjectURL(uploadedPhotoUrl);

    const url = URL.createObjectURL(file);
    setUploadedPhotoUrl(url);
    setShowNailPicker(true);
    e.target.value = "";
  };

  // ── 裁剪回调 ──

  const handleCropConfirm = useCallback(
    (bitmap: ImageBitmap) => {
      const old = nailTextures[activeFinger];
      const updated = [...nailTextures];
      updated[activeFinger] = bitmap;

      // 仅当旧纹理不被其他手指引用时才释放
      if (old && !updated.some((t) => t === old)) {
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

  // ── 多纹理拣选回调 ──

  const handlePickingConfirm = useCallback(
    (assignments: NailAssignment[]) => {
      const updated = [...nailTextures];

      for (const assign of assignments) {
        const old = updated[assign.finger];
        // 释放旧纹理（仅当不被其他手指引用）
        if (old) {
          const otherRefs = updated.some(
            (t, i) => i !== assign.finger && t === old
          );
          if (!otherRefs) old.close();
        }
        updated[assign.finger] = assign.texture;
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

  // ── 纹理操作 ──

  const applyTextureToAll = () => {
    const activeTex = nailTextures[activeFinger];
    if (!activeTex) {
      alert("当前手指还没有设置纹理");
      return;
    }

    const updated = nailTextures.map((t, i) => {
      if (i === activeFinger) return t;
      // 仅释放不被其他手指引用的旧纹理
      if (t && t !== activeTex) {
        const otherRefs = nailTextures.some(
          (ot, oi) => oi !== i && oi !== activeFinger && ot === t
        );
        if (!otherRefs) t.close();
      }
      return activeTex;
    });

    setNailTextures(updated);
  };

  const removeTexture = (fingerIdx: number) => {
    const tex = nailTextures[fingerIdx];
    const updated = [...nailTextures];
    updated[fingerIdx] = null;

    if (tex && !updated.some((t) => t === tex)) {
      tex.close();
    }

    setNailTextures(updated);
  };

  // ── 渲染 ──

  return (
    <div className="min-h-dvh flex flex-col">
      <Header />

      <main className="flex-1 pt-20 pb-8 px-4 max-w-md mx-auto w-full">
        <h2 className="text-lg font-semibold text-center mb-1">📱 AR 实时试戴</h2>
        <p className="text-xs text-gray-400 text-center mb-4">
          摄像头实时预览美甲效果，手指移动时颜色跟随
        </p>

        {/* 开始按钮 */}
        {!isStarted && (
          <div className="flex flex-col items-center gap-4 py-8">
            <div className="w-40 h-40 rounded-full bg-gradient-to-br from-pink-100 to-purple-100
                            flex items-center justify-center shadow-inner">
              <span className="text-6xl">🤚</span>
            </div>
            <button
              onClick={() => setIsStarted(true)}
              className="w-full h-14 rounded-2xl bg-gradient-to-r from-[#E8A0BF] to-[#D4749D]
                         text-white text-base font-medium shadow-md
                         hover:shadow-lg active:scale-[0.98] transition-all"
            >
              📷 开启摄像头
            </button>
            <p className="text-xs text-gray-300 text-center">
              需要摄像头权限 · 仅本地处理不录制不上传
            </p>
          </div>
        )}

        {/* AR 视图 */}
        {isStarted && (
          <ArView
            nailColors={nailColors}
            nailTextures={nailTextures}
            mode={mode}
          />
        )}

        {/* 控制面板（AR开启后显示） */}
        {isStarted && (
          <div className="mt-4 bg-white rounded-2xl p-4 shadow-sm border border-pink-100">
            {/* 模式切换 */}
            <div className="flex gap-1 mb-3 p-1 bg-pink-50 rounded-xl">
              <button
                onClick={() => setMode("color")}
                className={`flex-1 py-1.5 text-xs rounded-lg transition-all ${
                  mode === "color"
                    ? "bg-white text-[#E8A0BF] font-medium shadow-sm"
                    : "text-gray-400"
                }`}
              >
                🎨 纯色
              </button>
              <button
                onClick={() => setMode("texture")}
                className={`flex-1 py-1.5 text-xs rounded-lg transition-all ${
                  mode === "texture"
                    ? "bg-white text-[#E8A0BF] font-medium shadow-sm"
                    : "text-gray-400"
                }`}
              >
                🖼️ 纹理
              </button>
            </div>

            {/* 手指选择 */}
            <div className="flex gap-2 mb-3 justify-center">
              {FINGER_NAMES.map((name, i) => (
                <button
                  key={i}
                  onClick={() => setActiveFinger(i)}
                  className={`px-3 py-1.5 rounded-full text-xs transition-all relative
                    ${activeFinger === i
                      ? "bg-[#E8A0BF] text-white shadow-sm"
                      : "bg-pink-50 text-gray-400 hover:bg-pink-100"
                    }`}
                >
                  {name}
                  {nailTextures[i] && (
                    <span className="absolute -top-1 -right-1 w-2.5 h-2.5 bg-green-400 rounded-full border border-white" />
                  )}
                </button>
              ))}
            </div>

            {/* 纹理模式内容 */}
            {mode === "texture" && (
              <div className="mb-3 text-center">
                {nailTextures[activeFinger] ? (
                  <div className="flex items-center gap-3 justify-center mb-2">
                    <div className="w-12 h-12 rounded-xl overflow-hidden border-2 border-pink-300 bg-pink-50 flex items-center justify-center">
                      <TextureThumb
                        bitmap={nailTextures[activeFinger]!}
                        size={48}
                      />
                    </div>
                    <div className="text-left">
                      <p className="text-xs font-medium">
                        {FINGER_NAMES[activeFinger]}纹理
                      </p>
                      <button
                        onClick={() => removeTexture(activeFinger)}
                        className="text-xs text-red-400 hover:text-red-500"
                      >
                        移除
                      </button>
                    </div>
                  </div>
                ) : (
                  <p className="text-xs text-gray-400 mb-2">
                    {FINGER_NAMES[activeFinger]}暂未设置纹理
                  </p>
                )}

                <div className="flex gap-2 justify-center">
                  <label className="px-3 py-1.5 text-xs rounded-full bg-pink-50 text-[#E8A0BF] cursor-pointer hover:bg-pink-100 transition-colors">
                    📷 上传美甲照片
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept="image/png,image/jpeg,image/webp"
                      onChange={handleTextureUpload}
                      className="hidden"
                    />
                  </label>
                  <label className="px-3 py-1.5 text-xs rounded-full bg-purple-50 text-purple-500 cursor-pointer hover:bg-purple-100 transition-colors">
                    🎨 多纹理提取
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
                      className="px-3 py-1.5 text-xs rounded-full bg-pink-50 text-[#E8A0BF] hover:bg-pink-100 transition-colors"
                    >
                      应用到全部
                    </button>
                  )}
                </div>
              </div>
            )}

            {/* 纯色模式内容 */}
            {mode === "color" && (
              <>
                <div className="flex items-center gap-3 justify-center mb-3">
                  <div
                    className="w-8 h-8 rounded-full border-2 border-gray-100 shadow-sm"
                    style={{ backgroundColor: nailColors[activeFinger] }}
                  />
                  <span className="text-xs text-gray-400">
                    {FINGER_NAMES[activeFinger]}颜色
                  </span>
                  <button
                    onClick={applyToAll}
                    className="text-xs text-[#E8A0BF] underline hover:text-[#D4749D]"
                  >
                    应用到全部
                  </button>
                </div>

                <div className="flex flex-wrap gap-2 justify-center">
                  {PRESET_COLORS.filter((_, i) => i < 12).map((item) => (
                    <button
                      key={item.name}
                      title={item.name}
                      onClick={() => changeColor(item.color)}
                      className={`w-9 h-9 rounded-full shadow-sm border-2 transition-all hover:scale-110
                        ${nailColors[activeFinger] === item.color
                          ? "ring-2 ring-offset-2 ring-pink-400 scale-110"
                          : ""
                        }
                        ${item.color === "#FFFFFF" || item.name === "透明"
                          ? "border-gray-200"
                          : "border-transparent"
                        }`}
                      style={{ backgroundColor: item.color }}
                    />
                  ))}
                </div>

                <div className="flex items-center justify-center gap-2 mt-3">
                  <span className="text-xs text-gray-400">自定义:</span>
                  <input
                    type="color"
                    value={nailColors[activeFinger]}
                    onChange={(e) => changeColor(e.target.value)}
                    className="w-9 h-9 rounded-full cursor-pointer border-0 p-0"
                  />
                </div>
              </>
            )}
          </div>
        )}

        {/* 纹理裁剪模态框 */}
        {showCropper && uploadedPhotoUrl && (
          <TextureCropper
            imageUrl={uploadedPhotoUrl}
            onConfirm={handleCropConfirm}
            onCancel={handleCropCancel}
          />
        )}

        {/* 多纹理提取器 */}
        {showNailPicker && uploadedPhotoUrl && (
          <NailArtPicker
            imageUrl={uploadedPhotoUrl}
            onConfirm={handlePickingConfirm}
            onCancel={handlePickingCancel}
          />
        )}

        {/* 隐私说明 */}
        <div className="mt-4 space-y-2">
          <div className="p-3 bg-white/60 rounded-xl border border-pink-50 text-center">
            <p className="text-xs text-gray-400">
              🔒 摄像头画面仅在内存中处理，不录制不上传
            </p>
          </div>
          <div className="p-3 bg-white/60 rounded-xl border border-pink-50 text-center">
            <p className="text-xs text-gray-400">
              📱 初次加载约 5-10 秒 · 建议在光线充足的环境使用
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}

// ─── 纹理缩略图子组件 ────────────────────────────────────

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
      className="w-full h-full object-contain"
    />
  );
}
