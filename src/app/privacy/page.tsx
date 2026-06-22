"use client";

import { Header } from "@/components/Header";

export default function PrivacyPage() {
  return (
    <div className="min-h-dvh flex flex-col">
      <Header />

      <main className="flex-1 pt-20 pb-8 px-4 max-w-md mx-auto w-full">
        <h2 className="text-lg font-semibold text-center mb-4">🔒 隐私政策</h2>

        <div className="space-y-4 text-sm text-gray-500 leading-relaxed">
          <section className="bg-white rounded-2xl p-4 border border-pink-50">
            <h3 className="font-semibold text-gray-600 mb-2">我们重视你的隐私</h3>
            <p>"甲如" 将用户隐私放在首位。我们采用"本地优先"的设计理念，尽可能在浏览器中完成所有数据处理。</p>
          </section>

          <section className="bg-white rounded-2xl p-4 border border-pink-50">
            <h3 className="font-semibold text-gray-600 mb-2">📷 照片处理</h3>
            <p>你上传的手部照片 <strong>全部在浏览器本地处理</strong>，不会被发送到任何服务器。抠图、涂色等操作均在本地完成。</p>
          </section>

          <section className="bg-white rounded-2xl p-4 border border-pink-50">
            <h3 className="font-semibold text-gray-600 mb-2">✨ AI 生成</h3>
            <p>AI生成功能 <strong>仅发送你输入的风格描述文字</strong>，不会发送你的照片或图片。AI服务商无法获取你的个人图像数据。</p>
          </section>

          <section className="bg-white rounded-2xl p-4 border border-pink-50">
            <h3 className="font-semibold text-gray-600 mb-2">📱 AR 摄像头</h3>
            <p>AR模式调用摄像头时，画面数据 <strong>仅在内存中实时处理</strong>，不会被录制、存储或上传到任何服务器。</p>
          </section>

          <section className="bg-white rounded-2xl p-4 border border-pink-50">
            <h3 className="font-semibold text-gray-600 mb-2">📄 数据存储</h3>
            <p>你保存的试戴效果图默认存储在 <strong>你的设备本地</strong>。我们不会收集、存储或分析你的个人使用数据。</p>
          </section>

          <section className="bg-white rounded-2xl p-4 border border-pink-50">
            <h3 className="font-semibold text-gray-600 mb-2">🔐 联系我们</h3>
            <p>如果你对隐私有任何疑问或顾虑，随时可以联系我们。我们承诺用最通俗的语言解释数据流向，不隐藏任何信息。</p>
          </section>
        </div>

        <p className="text-center text-xs text-gray-300 mt-6">最后更新：2025年6月</p>
      </main>
    </div>
  );
}
