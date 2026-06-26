/**
 * HTTPS 开发服务器代理
 * 解决手机浏览器摄像头权限问题（HTTPS 要求）
 * 使用方式: node https-dev.mjs
 */
import { createServer } from "node:https";
import { readFileSync, existsSync } from "node:fs";
import { createProxy } from "node:http-proxy";
import { execSync } from "node:child_process";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const CERT_DIR = join(__dirname, ".cert");
const KEY = join(CERT_DIR, "key.pem");
const CERT = join(CERT_DIR, "cert.pem");
const TARGET = 3000;

// 生成自签名证书
if (!existsSync(KEY) || !existsSync(CERT)) {
  console.log("生成自签名证书...");
  try {
    execSync(
      `openssl req -x509 -newkey rsa:2048 -keyout "${KEY}" -out "${CERT}" -days 365 -nodes -subj "/CN=192.168.1.100"`,
      { stdio: "pipe" }
    );
    console.log("证书已生成");
  } catch {
    console.error("请安装 openssl: https://slproweb.com/products/Win32OpenSSL.html");
    process.exit(1);
  }
}

const server = createServer({
  key: readFileSync(KEY),
  cert: readFileSync(CERT),
}, (req, res) => {
  // 代理到 Next.js dev server
  const proxy = createProxy();
  proxy.web(req, res, { target: "http://localhost:" + TARGET, changeOrigin: true });
});

const PORT = 3443;
server.listen(PORT, () => {
  console.log(`\n🔒 HTTPS 服务器已启动:`);
  console.log(`   https://localhost:${PORT}`);
  console.log(`   https://192.168.1.100:${PORT}`);
  console.log(`\n📱 手机访问上面的 HTTPS 地址即可使用摄像头`);
  console.log(`⚠️  首次访问会提示"不安全"，点击"高级"→"继续前往"即可\n`);
});
