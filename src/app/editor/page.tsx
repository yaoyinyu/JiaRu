"use client";

import { useState } from "react";
import { Header } from "@/components/Header";
import { UploadButton } from "@/components/UploadButton";
import { NailCanvas } from "@/components/NailCanvas";
import { ColorPalette } from "@/components/ColorPalette";
import Link from "next/link";

export default function EditorPage() {
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [selectedColor, setSelectedColor] = useState("#E8A0BF");
  const [brushSize] = useState(15);

  // 处理图片上传
  const handleUpload = (file: File) => {
    const url = URL.createObjectURL(file);
    setImageUrl(url);
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
            <NailCanvas
              imageUrl={imageUrl}
              selectedColor={selectedColor}
              brushSize={brushSize}
            />

            <div className="mt-6">
              <p className="text-center text-xs text-gray-400 mb-3">
                选择颜色后，在指甲位置点击或涂抹
              </p>
              <ColorPalette
                selectedColor={selectedColor}
                onSelectColor={setSelectedColor}
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
            <li>• 点击指甲位置涂抹颜色</li>
            <li>• 涂抹时可以拖动手指连续上色</li>
            <li>• 使用撤销按钮可以回退上一步</li>
            <li>• 所有处理在本地完成，照片不会上传</li>
          </ul>
        </div>
      </main>
    </div>
  );
}
