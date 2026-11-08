import { fileURLToPath } from "node:url";

const config = {
  plugins: {
    // 正式站样式类均在src中，避免每次冷编译遍历训练和审核工作区。
    "@tailwindcss/postcss": { base: fileURLToPath(new URL("./src", import.meta.url)) },
  },
};

export default config;
