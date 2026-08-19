"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { AppShell } from "@/components/AppShell";

type Status = "idle" | "loading" | "error";

const ERROR_HINT: Record<string, string> = {
  state_mismatch: "登录状态校验失败，请重试",
  wechat_canceled: "已取消微信登录",
  wechat_not_configured: "微信登录尚未配置",
  wechat_failed: "微信登录失败，请重试",
};

/**
 * /login 登录/注册页（登录即注册，文档 §5.1）
 * 支持：手机号+验证码（发码前需人机验证，60s 节流）、微信扫码登录
 * （微信首次登录后需在账号页补绑手机号）。
 */
export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [status, setStatus] = useState<Status>("idle");
  const [errorMsg, setErrorMsg] = useState("");

  // 手机号方式
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [devCode, setDevCode] = useState<string | null>(null);
  const [countdown, setCountdown] = useState(0);
  const countdownTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  // 人机验证（图形验证码）
  const [captchaId, setCaptchaId] = useState("");
  const [captchaUrl, setCaptchaUrl] = useState("");
  const [captchaInput, setCaptchaInput] = useState("");
  const [captchaVisible, setCaptchaVisible] = useState(false);
  const [captchaLoading, setCaptchaLoading] = useState(false);

  // 微信登录配置状态（挂载时探测一次）
  const [wechatConfigured, setWechatConfigured] = useState<boolean | null>(null);

  // 从回调参数读取错误提示（如微信登录失败）：渲染期派生，不写 state
  const callbackError = searchParams.get("error");
  const shownError = callbackError && ERROR_HINT[callbackError] ? ERROR_HINT[callbackError] : null;

  useEffect(() => {
    // 探测微信登录配置状态
    let cancelled = false;
    fetch("/api/auth/oauth/wechat/status")
      .then((resp) => resp.json())
      .then((data) => {
        if (!cancelled) setWechatConfigured(Boolean(data?.configured));
      })
      .catch(() => {
        if (!cancelled) setWechatConfigured(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const startCountdown = useCallback(() => {
    setCountdown(60);
    if (countdownTimer.current) clearInterval(countdownTimer.current);
    countdownTimer.current = setInterval(() => {
      setCountdown((c) => {
        if (c <= 1) {
          if (countdownTimer.current) clearInterval(countdownTimer.current);
          return 0;
        }
        return c - 1;
      });
    }, 1000);
  }, []);

  const fetchCaptcha = useCallback(async () => {
    setCaptchaLoading(true);
    setCaptchaInput("");
    try {
      const resp = await fetch("/api/auth/captcha");
      const data = await resp.json();
      if (!resp.ok || !data?.id || !data?.dataUrl) throw new Error("人机验证加载失败");
      setCaptchaId(data.id);
      setCaptchaUrl(data.dataUrl);
      setCaptchaVisible(true);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : String(err));
    } finally {
      setCaptchaLoading(false);
    }
  }, []);

  const handleRequestCode = async () => {
    if (status === "loading" || countdown > 0) return;
    // 第一步：弹出人机验证
    if (!captchaVisible) {
      setErrorMsg("");
      await fetchCaptcha();
      return;
    }
    if (!captchaInput.trim()) {
      setErrorMsg("请先输入图形验证码");
      return;
    }
    setStatus("loading");
    setErrorMsg("");
    try {
      const resp = await fetch("/api/auth/request-code", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone, captchaId, captchaAnswer: captchaInput }),
      });
      const data = await resp.json();
      if (!resp.ok) {
        // 人机验证失败：刷新图形验证码重新输入
        if (resp.status === 400 && data?.error?.includes("人机验证")) {
          await fetchCaptcha();
        }
        throw new Error(data?.error || `请求失败 (${resp.status})`);
      }
      if (data?.devCode) setDevCode(data.devCode as string);
      setCaptchaVisible(false);
      startCountdown();
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : String(err));
    } finally {
      setStatus("idle");
    }
  };

  const handlePhoneLogin = async () => {
    if (status === "loading") return;
    setStatus("loading");
    setErrorMsg("");
    try {
      const resp = await fetch("/api/auth/verify-code", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone, code }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data?.error || `请求失败 (${resp.status})`);
      router.push("/account");
      router.refresh();
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : String(err));
      setStatus("error");
    }
  };

  const handleWechatLogin = () => {
    window.location.href = "/api/auth/oauth/wechat";
  };

  const inputCls =
    "w-full rounded-xl border border-pink-200 bg-white/80 px-4 py-3 text-[15px] text-[#4A4A4A] outline-none transition placeholder:text-[#c9bfc3] focus:border-pink-400 focus:ring-2 focus:ring-pink-100";

  return (
    <AppShell eyebrow="会员中心" title="登录 / 注册" description="登录即注册：首次使用任一方式登录会自动创建账号。登录后解锁云端作品、收藏与 AI 配额。">
      <div className="mx-auto w-full max-w-md">
        <div className="rounded-3xl border border-pink-100 bg-white/75 p-6 shadow-[0_16px_48px_rgba(159,95,122,.08)] backdrop-blur-sm sm:p-8">
          <div className="space-y-4">
            <div>
              <label htmlFor="phone" className="mb-1.5 block text-sm font-medium text-[#6a5f64]">手机号</label>
              <input
                id="phone"
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="11 位手机号"
                className={inputCls}
                autoComplete="tel"
                inputMode="numeric"
              />
            </div>
            <div>
              <label htmlFor="code" className="mb-1.5 block text-sm font-medium text-[#6a5f64]">验证码</label>
              <div className="flex gap-2">
                <input
                  id="code"
                  type="text"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  placeholder="6 位验证码"
                  className={inputCls}
                  inputMode="numeric"
                  maxLength={6}
                />
                <button
                  type="button"
                  onClick={handleRequestCode}
                  disabled={countdown > 0 || status === "loading" || !/^1[3-9]\d{9}$/.test(phone)}
                  className="shrink-0 rounded-xl border border-pink-200 bg-pink-50 px-4 text-sm font-semibold text-[#cf6f99] transition hover:bg-pink-100 disabled:opacity-50"
                >
                  {countdown > 0 ? `${countdown}s` : "获取验证码"}
                </button>
              </div>
            </div>

            {/* 人机验证区：先通过图形验证码才允许发送短信 */}
            {captchaVisible && (
              <div className="rounded-xl border border-pink-100 bg-pink-50/60 p-3">
                <div className="mb-2 flex items-center justify-between">
                  <p className="text-xs font-medium text-[#6a5f64]">人机验证：请输入图中的字符</p>
                  <button
                    type="button"
                    onClick={fetchCaptcha}
                    disabled={captchaLoading}
                    className="text-xs text-[#cf6f99] underline-offset-2 hover:underline disabled:opacity-50"
                  >
                    {captchaLoading ? "加载中…" : "换一张"}
                  </button>
                </div>
                <div className="flex items-center gap-3">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={captchaUrl} alt="人机验证码" width={140} height={48} className="rounded-lg border border-pink-200 bg-white" />
                  <input
                    type="text"
                    value={captchaInput}
                    onChange={(e) => setCaptchaInput(e.target.value)}
                    placeholder="输入字符"
                    maxLength={6}
                    className="min-w-0 flex-1 rounded-xl border border-pink-200 bg-white/80 px-3 py-2 text-sm uppercase outline-none transition focus:border-pink-400"
                  />
                </div>
              </div>
            )}

            <button
              type="button"
              onClick={handlePhoneLogin}
              disabled={status === "loading"}
              className="w-full rounded-xl bg-gradient-to-r from-pink-400 to-pink-500 py-3 text-[15px] font-semibold text-white shadow-lg shadow-pink-200/60 transition hover:opacity-90 disabled:opacity-50"
            >
              {status === "loading" ? "请稍候…" : "手机号登录 / 注册"}
            </button>
          </div>

          {devCode && (
            <p className="mt-4 rounded-lg bg-amber-50 px-3 py-2 text-xs leading-relaxed text-amber-700">
              开发模式：验证码为 <b>{devCode}</b>（未配置短信服务商时自动生成）
            </p>
          )}
          {(errorMsg || shownError) && (
            <p className="mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{errorMsg || shownError}</p>
          )}

          {/* 微信登录 */}
          <div className="mt-6">
            <div className="mb-3 flex items-center gap-3 text-xs text-[#b9a8ae]">
              <span className="h-px flex-1 bg-pink-100" />
              其他方式
              <span className="h-px flex-1 bg-pink-100" />
            </div>
            <button
              type="button"
              onClick={handleWechatLogin}
              disabled={wechatConfigured === false}
              title={
                wechatConfigured === false
                  ? "微信登录需要微信开放平台企业认证（300 元/年），配置后开放"
                  : "使用微信扫码登录"
              }
              className="w-full rounded-xl border border-[#22ac38]/40 bg-[#22ac38]/5 px-3 py-2.5 text-sm font-semibold text-[#1d9e31] transition hover:bg-[#22ac38]/10 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {wechatConfigured === false ? "微信登录（未配置）" : wechatConfigured === null ? "微信登录…" : "微信扫码登录"}
            </button>
          </div>
        </div>

        <p className="mt-5 text-center text-xs leading-relaxed text-[#b9a8ae]">
          登录即表示你同意 <Link href="/privacy" className="text-[#cf6f99] underline-offset-2 hover:underline">隐私政策</Link>
          ；微信首次登录后需补绑手机号；注册时选择年龄区间，14 岁以下默认不参与「用户改进计划」数据收集。
        </p>
      </div>
    </AppShell>
  );
}
