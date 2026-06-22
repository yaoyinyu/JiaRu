"use client";

import { useState } from "react";
import { Header } from "@/components/Header";
import { UploadButton } from "@/components/UploadButton";
import { NailCanvas } from "@/components/NailCanvas";
import { ColorPalette } from "@/components/ColorPalette";
import { FINGER_NAMES } from "@/lib/utils";

export default function EditorPage() {
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [nailColors, setNailColors] = useState<string[]>(
    Array(5).fill("#E8A0BF")
  );
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
    <div className="min-h-dvh flex flex-col">
      <Header />

      <main className="flex-1 pt-20 pb-8 px-4 max-w-md mx-auto w-full">
        <h2 className="text-lg font-semibold text-center mb-4">
          {imageUrl ? "💅 涂抹试色" : "📷 上传手部照片"}
        </h2>

        {/* 未上传 -> 显示上传按钮 */}
        {!imageUrl && <UploadButton onUpload={handleUpload} />}

        {/* 已上传 -> 显示编辑器 */}
        {imageUrl && (
          <>
            {/* 手指选择 tab */}
            <div className="flex gap-2 mb-3 justify-center">
              {FINGER_NAMES.map((name, i) => (
                <button
                  key={i}
                  onClick={() => setActiveFinger(i)}
                  className={`px-3 py-1.5 rounded-full text-xs transition-all
                    ${
                      activeFinger === i
                        ? "bg-[#E8A0BF] text-white shadow-sm"
                        : "bg-pink-50 text-gray-400 hover:bg-pink-100"
                    }`}
                >
                  {name}
                </button>
              ))}
            </div>

            {/* 当前手指颜色预览 + 应用到全部 */}
            <div className="flex items-center gap-3 justify-center mb-3">
              <div
                className="w-7 h-7 rounded-full border-2 border-gray-100 shadow-sm"
                style={{ backgroundColor: currentColor }}
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

            <NailCanvas
              imageUrl={imageUrl}
              nailColors={nailColors}
              activeFinger={activeFinger}
              brushSize={brushSize}
            />

            <div className="mt-6">
              <p className="text-center text-xs text-gray-400 mb-3">
                选择颜色后，在指甲位置点击或涂抹
              </p>
              <ColorPalette
                selectedColor={currentColor}
                onSelectColor={changeColor}
              />
            </div>

            {/* 重新上传 */}
            <div className="mt-4 text-center">
              <button
                onClick={() => {
                  setImageUrl(null);
                }}
                className="text-sm text-gray-400 underline hover:text-pink-400"
              >
                换一张照片
              </button>
            </div>
          </>
        )}

        {/* 使用提示 */}
        <div className="mt-6 p-4 bg-white/60 rounded-2xl border border-pink-50">
          <h4 className="text-xs font-semibold text-gray-500 mb-2">💡 使用提示</h4>
          <ul className="text-xs text-gray-400 space-y-1">
            <li>• 上传清晰的手部照片效果更好</li>
            <li>• 选择手指后涂抹对应指甲</li>
            <li>• 不同手指可以选不同颜色</li>
            <li>• 涂抹时可以拖动手指连续上色</li>
            <li>• 使用撤销按钮可以回退上一步</li>
            <li>• 所有处理在本地完成，照片不会上传</li>
          </ul>
        </div>
      </main>
    </div>
  );
}
