import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    // 此ESM审核器的局部WebAssembly.Module变量不属于Next.js模块运行时。
    files: ["model/runtime/audit-mask-f64-synthetic.mjs"],
    rules: { "@next/next/no-assign-module-variable": "off" },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    ".next-deploy/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // Project-specific ignores:
    "backup_ar_working/**",
    ".archive/**",
    "docs/**",
    "dev-log/**",
    // 本地冻结证据与一次性审核脚本单独验真，不作为业务lint输入。
    "model/reviews/**",
    "model/training/oneoff/**",
    "scripts/**",
    "public/vendor/**",
    "辅助材料/**",
    // 本地机器产物与变更前备份：均由 .gitignore 隔离、从不入库，但默认 `eslint`
    // 无参数运行时会扫描整个工作区。此前它们贡献了 2654 条问题中的绝大多数
    // （.backup-consumer-*/restored-app/.next 下的构建产物与 vendor bundle），
    // 既让 `npm run lint` 长期退出码 1、无法作为 CI 门禁，也把 src 下唯一一条
    // 真实警告淹没在噪音里。这里与 .gitignore 边界对齐。
    "output/**",
    ".backup-consumer-*/**",
  ]),
]);

export default eslintConfig;
