"use client";

import { useState } from "react";
import { FlowingShell, GlassPanel, PageHero } from "@/components/FlowingShell";
import { UploadButton } from "@/components/UploadButton";
import { NailCanvas } from "@/components/NailCanvas";
import { ColorPalette } from "@/components/ColorPalette";
import { FINGER_NAMES } from "@/lib/utils";

export default function EditorPage() {
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [nailColors, setNailColors] = useState<string[]>(Array(5).fill("#E8A0BF"));
  const [activeFinger, setActiveFinger] = useState(0);
  const [brushSize] = useState(15);

  const currentColor = nailColors[activeFinger];

  const handleUpload = (file: File) => {
    const url = URL.createObjectURL(file);
    setImageUrl(url);
  };

  const changeColor = (color: string) => {
    const updated = [...nailColors];
    updated[activeFinger] = color;
    setNailColors(updated);
  };

  const applyToAll = () => {
    setNailColors(Array(5).fill(nailColors[activeFinger]));
  };

  return (
    <FlowingShell>
      <PageHero
        eyebrow="上传试色"
        title={imageUrl ? "涂抹你的专属甲色" : "上传手部照片开始试色"}
        description="选择手指、挑选颜色，在照片上快速预览不同美甲配色。"
      />

      {!imageUrl && <UploadButton onUpload={handleUpload} />}

      {imageUrl && (
        <GlassPanel className="p-4">
          <div className="mb-4 flex flex-wrap justify-center gap-2">
            {FINGER_NAMES.map((name, i) => (
              <button
                key={name}
                onClick={() => setActiveFinger(i)}
                className={`rounded-full px-3 py-1.5 text-xs transition-all ${
                  activeFinger === i
                    ? "bg-[#d4749d] text-white shadow-sm"
                    : "bg-white/70 text-gray-400 hover:bg-pink-50"
                }`}
              >
                {name}
              </button>
            ))}
          </div>

          <div className="mb-4 flex items-center justify-center gap-3">
            <div
              className="h-8 w-8 rounded-full border-2 border-white shadow-sm"
              style={{ backgroundColor: currentColor }}
            />
            <span className="text-xs text-gray-400">{FINGER_NAMES[activeFinger]}颜色</span>
            <button
              onClick={applyToAll}
              className="text-xs font-medium text-[#d4749d] underline underline-offset-4 hover:text-[#b95f86]"
            >
              应用到全部
            </button>
          </div>

          <NailCanvas
            imageUrl={imageUrl}
            nailColors={nailColors}
            activeFinger={activeFinger}
            brushSize={brushSize}
          />

          <div className="mt-6">
            <p className="mb-3 text-center text-xs text-gray-400">
              选择颜色后，在指甲位置点击或涂抹。
            </p>
            <ColorPalette selectedColor={currentColor} onSelectColor={changeColor} />
          </div>

          <div className="mt-5 text-center">
            <button
              onClick={() => setImageUrl(null)}
              className="text-sm font-medium text-gray-400 underline underline-offset-4 hover:text-[#d4749d]"
            >
              换一张照片
            </button>
          </div>
        </GlassPanel>
      )}

      <GlassPanel className="mt-6 p-5">
        <h2 className="mb-3 text-sm font-semibold text-[#4a4a4a]">使用提示</h2>
        <ul className="space-y-2 text-xs leading-5 text-gray-400">
          <li>• 上传清晰、光线均匀的手部照片效果更好。</li>
          <li>• 先选择手指，再给对应指甲涂色。</li>
          <li>• 不同手指可以设置不同颜色，也可以一键应用到全部。</li>
          <li>• 所有处理都在本地完成，照片不会上传。</li>
        </ul>
      </GlassPanel>
    </FlowingShell>
  );
}