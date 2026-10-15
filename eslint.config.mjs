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
    "scripts/**",
    "public/vendor/**",
    "辅助材料/**",
  ]),
]);

export default eslintConfig;
