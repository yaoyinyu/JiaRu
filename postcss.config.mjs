const config = {
  plugins: {
    // 正式站样式类均在src中，避免每次冷编译遍历训练和审核工作区。
    // base 必须写成相对路径（相对项目根）：Turbopack（Next 16 默认构建器）拿到绝对
    // 路径形式的 base 时不会报错，但扫描不到任何候选文件，产出不含 Tailwind 工具类的
    // CSS（构建成功、页面样式全丢）；而 `new URL("./src", import.meta.url)` 会被
    // Turbopack 静态分析成模块请求，目录无法解析，直接让生产构建失败
    // （Module not found: Can't resolve './src'）。
    "@tailwindcss/postcss": { base: "src" },
  },
};

export default config;
