"use client";

import { useState } from "react";
import { Header } from "@/components/Header";
import { ArView } from "@/components/ArView";
import { PRESET_COLORS } from "@/lib/utils";

const FINGER_NAMES = ["拇指", "食指", "中指", "无名指", "小指"];

export default function ArTryonPage() {
  const [nailColors, setNailColors] = useState(["#E8A0BF", "#E8A0BF", "#E8A0BF", "#E8A0BF", "#E8A0BF"]);
  const [activeFinger, setActiveFinger] = useState(0); // 当前正在选色的手指
  const [isStarted, setIsStarted] = useState(false);

  // 更新某个手指的颜色
  const changeColor = (color: string) => {
    const updated = [...nailColors];
    updated[activeFinger] = color;
    setNailColors(updated);
  };

  // 一键全部设为同色
  const applyToAll = () => {
    const same = Array(5).fill(nailColors[activeFinger]);
    setNailColors(same);
  };

  // 重置 AR 视图（重新开始）
  const resetView = () => {
    setIsStarted(false);
    setTimeout(() => setIsStarted(true), 100);
  };

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
        {isStarted && <ArView nailColors={nailColors} />}

        {/* 颜色选择面板（AR开启后显示） */}
        {isStarted && (
          <div className="mt-4 bg-white rounded-2xl p-4 shadow-sm border border-pink-100">
            {/* 手指选择 */}
            <div className="flex gap-2 mb-3 justify-center">
              {FINGER_NAMES.map((name, i) => (
                <button
                  key={i}
                  onClick={() => setActiveFinger(i)}
                  className={`px-3 py-1.5 rounded-full text-xs transition-all
                    ${activeFinger === i
                      ? "bg-[#E8A0BF] text-white shadow-sm"
                      : "bg-pink-50 text-gray-400 hover:bg-pink-100"
                    }`}
                >
                  {name}
                </button>
              ))}
            </div>

            {/* 当前选中的颜色预览 */}
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

            {/* 预设颜色 */}
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

            {/* 自定义取色 */}
            <div className="flex items-center justify-center gap-2 mt-3">
              <span className="text-xs text-gray-400">自定义:</span>
              <input
                type="color"
                value={nailColors[activeFinger]}
                onChange={(e) => changeColor(e.target.value)}
                className="w-9 h-9 rounded-full cursor-pointer border-0 p-0"
              />
            </div>
          </div>
        )}

        {/* 隐私与性能说明 */}
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
