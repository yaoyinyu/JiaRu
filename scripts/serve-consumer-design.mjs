import http from "node:http";
import { readFile, realpath } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

// 只服务设计提案及六张既有图库素材，不暴露工作区、账户数据库或环境文件。
const project = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const root = path.join(project, "design", "consumer-v1");
const portIndex = process.argv.indexOf("--port");
const port = portIndex === -1 ? 4318 : Number(process.argv[portIndex + 1]);
if (!Number.isInteger(port) || port < 1024 || port > 65535) throw new Error("端口必须在 1024–65535 之间");
const routes = new Map([
  ["/", [path.join(root, "index.html"), "text/html; charset=utf-8"]],
  ["/index.html", [path.join(root, "index.html"), "text/html; charset=utf-8"]],
  ["/style.css", [path.join(root, "style.css"), "text/css; charset=utf-8"]],
  ["/app.mjs", [path.join(root, "app.mjs"), "text/javascript; charset=utf-8"]],
  ["/assets/fonts/jiaru-editorial-serif.woff2", [path.join(root, "assets", "fonts", "jiaru-editorial-serif.woff2"), "font/woff2"]],
  ["/assets/hero-hand-v1.png", [path.join(root, "assets", "hero-hand-v1.png"), "image/png"]],
  ["/assets/hero-hand-collage-v2.png", [path.join(root, "assets", "hero-hand-collage-v2.png"), "image/png"]],
  ["/assets/hero-hand-diversity-v3.png", [path.join(root, "assets", "hero-hand-diversity-v3.png"), "image/png"]],
  ...Array.from({ length: 6 }, (_, i) => [`/assets/ai-look-${i + 1}.jpg`, [path.join(project, "public", "nail-gallery", `ai-look-${i + 1}.jpg`), "image/jpeg"]]),
]);
const server = http.createServer(async (request, response) => {
  response.setHeader("X-Content-Type-Options", "nosniff");
  response.setHeader("Cache-Control", "no-store");
  response.setHeader("Referrer-Policy", "no-referrer");
  response.setHeader("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; font-src 'self'; connect-src 'none'; base-uri 'none'; frame-ancestors 'self'; form-action 'none'");
  response.setHeader("Permissions-Policy", "camera=(), microphone=(), geolocation=()");
  if (!["GET", "HEAD"].includes(request.method)) {
    response.writeHead(405, { Allow: "GET, HEAD" }).end("只读设计预览");
    return;
  }
  const route = routes.get(new URL(request.url, "http://127.0.0.1").pathname);
  if (!route) { response.writeHead(404).end("未找到设计资源"); return; }
  try {
    const resolved = await realpath(route[0]);
    if (path.relative(project, resolved).startsWith("..") || path.isAbsolute(path.relative(project, resolved))) throw new Error("资源越界");
    const bytes = await readFile(resolved);
    response.writeHead(200, { "Content-Type": route[1], "Content-Length": bytes.length });
    response.end(request.method === "HEAD" ? undefined : bytes);
  } catch { response.writeHead(404).end("设计资源不可用"); }
});
server.on("error", (error) => { console.error(`预览启动失败：${error.message}`); process.exitCode = 1; });
server.listen(port, "127.0.0.1", () => console.log(`甲如消费者设计预览：http://127.0.0.1:${port}（独立本地原型，旧版未切换）`));
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => server.close());
