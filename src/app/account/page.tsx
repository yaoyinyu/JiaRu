"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";

type MeResponse = {
  user: {
    id: string;
    phone: string | null;
    email: string | null;
    nickname: string;
    avatar: string | null;
    ageGroup: string | null;
    status: string;
    createdAt: number;
  };
  identities: Array<{ provider: "phone" | "email" | "wechat" | "github"; identifier: string; lastUsedAt: number }>;
  consent: { improvementEnabled: boolean; agreementVersion: string | null };
};

const PROVIDER_LABEL: Record<string, string> = {
  phone: "手机号",
  email: "邮箱",
  wechat: "微信",
  github: "GitHub",
};

const IMPROVEMENT_KEY = "jiaru-improvement-program";

/**
 * /account 账号中心（登录后可访问）
 * 展示档案、登录方式管理（§5.2）、账号级改进计划偏好（§5.6）、退出登录。
 */
export default function AccountPage() {
  const router = useRouter();
  const [me, setMe] = useState<MeResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [notLoggedIn, setNotLoggedIn] = useState(false);
  const [nickname, setNickname] = useState("");
  const [savingNickname, setSavingNickname] = useState(false);
  const [notice, setNotice] = useState("");
  const [improvementEnabled, setImprovementEnabled] = useState(true);

  // 绑定手机号
  const [bindPhone, setBindPhone] = useState("");
  const [bindCode, setBindCode] = useState("");
  const [bindDevCode, setBindDevCode] = useState<string | null>(null);
  const [bindCountdown, setBindCountdown] = useState(0);
  const [bindCaptchaId, setBindCaptchaId] = useState("");
  const [bindCaptchaUrl, setBindCaptchaUrl] = useState("");
  const [bindCaptchaInput, setBindCaptchaInput] = useState("");
  const [bindCaptchaVisible, setBindCaptchaVisible] = useState(false);
  const [binding, setBinding] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/me")
      .then(async (resp) => {
        if (resp.status === 401) {
          if (!cancelled) setNotLoggedIn(true);
          return null;
        }
        if (!resp.ok) throw new Error(`加载失败 (${resp.status})`);
        const data = (await resp.json()) as { user: MeResponse };
        if (cancelled) return null;
        setMe(data.user);
        setNickname(data.user.user.nickname);
        setImprovementEnabled(data.user.consent.improvementEnabled);
        // 账号偏好同步写回设备 localStorage（§5.6）
        try {
          localStorage.setItem(IMPROVEMENT_KEY, data.user.consent.improvementEnabled ? "on" : "off");
        } catch {
          // localStorage 不可用时忽略
        }
        return null;
      })
      .catch((err: unknown) => {
        if (!cancelled) setNotice(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSaveNickname = async () => {
    if (!me) return;
    setSavingNickname(true);
    setNotice("");
    try {
      const resp = await fetch("/api/me", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nickname }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data?.error || "保存失败");
      setMe(data.user);
      setNotice("昵称已保存");
    } catch (err) {
      setNotice(err instanceof Error ? err.message : String(err));
    } finally {
      setSavingNickname(false);
    }
  };

  const handleToggleImprovement = async (enabled: boolean) => {
    setImprovementEnabled(enabled);
    setNotice("");
    try {
      const resp = await fetch("/api/me/improvement", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled }),
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => null);
        throw new Error(data?.error || "设置失败");
      }
      if (typeof window !== "undefined") {
        try {
          localStorage.setItem(IMPROVEMENT_KEY, enabled ? "on" : "off");
        } catch {
          // ignore
        }
      }
      setNotice(enabled ? "已开启「用户改进计划」" : "已关闭「用户改进计划」，不再上传数据");
    } catch (err) {
      setImprovementEnabled(!enabled);
      setNotice(err instanceof Error ? err.message : String(err));
    }
  };

  const handleUnbind = async (provider: string) => {
    if (!me) return;
    if (me.identities.length <= 1) {
      setNotice("至少需要保留一种登录方式");
      return;
    }
    if (!window.confirm(`确定解绑「${PROVIDER_LABEL[provider] ?? provider}」登录方式吗？`)) return;
    setNotice("");
    try {
      const resp = await fetch(`/api/me/identities/${provider}`, { method: "DELETE" });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data?.error || "解绑失败");
      setMe((prev) => (prev ? { ...prev, identities: data.identities } : prev));
      setNotice("已解绑");
    } catch (err) {
      setNotice(err instanceof Error ? err.message : String(err));
    }
  };

  const handleLogout = async () => {
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } finally {
      router.push("/");
      router.refresh();
    }
  };

  // ── 绑定手机号（微信新用户合规补绑，§5.1）──
  const fetchBindCaptcha = useCallback(async () => {
    setBindCaptchaInput("");
    try {
      const resp = await fetch("/api/auth/captcha");
      const data = await resp.json();
      if (!resp.ok || !data?.id || !data?.dataUrl) throw new Error("人机验证加载失败");
      setBindCaptchaId(data.id);
      setBindCaptchaUrl(data.dataUrl);
      setBindCaptchaVisible(true);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : String(err));
    }
  }, []);

  const handleRequestBindCode = async () => {
    if (binding || bindCountdown > 0) return;
    if (!/^1[3-9]\d{9}$/.test(bindPhone)) {
      setNotice("请输入正确的手机号");
      return;
    }
    if (!bindCaptchaVisible) {
      setNotice("");
      await fetchBindCaptcha();
      return;
    }
    if (!bindCaptchaInput.trim()) {
      setNotice("请先输入图形验证码");
      return;
    }
    setNotice("");
    try {
      const resp = await fetch("/api/auth/request-code", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone: bindPhone, captchaId: bindCaptchaId, captchaAnswer: bindCaptchaInput }),
      });
      const data = await resp.json();
      if (!resp.ok) {
        if (resp.status === 400 && data?.error?.includes("人机验证")) {
          await fetchBindCaptcha();
        }
        throw new Error(data?.error || `请求失败 (${resp.status})`);
      }
      if (data?.devCode) setBindDevCode(data.devCode as string);
      setBindCaptchaVisible(false);
      setBindCountdown(60);
      const timer = setInterval(() => {
        setBindCountdown((c) => {
          if (c <= 1) {
            clearInterval(timer);
            return 0;
          }
          return c - 1;
        });
      }, 1000);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : String(err));
    }
  };

  const handleBindPhone = async () => {
    if (binding || !/^1[3-9]\d{9}$/.test(bindPhone) || !/^\d{6}$/.test(bindCode)) {
      setNotice("请输入正确的手机号和 6 位验证码");
      return;
    }
    setBinding(true);
    setNotice("");
    try {
      const resp = await fetch("/api/auth/bind-phone", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone: bindPhone, code: bindCode }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data?.error || "绑定失败");
      setMe(data.user);
      setNotice("手机号绑定成功");
      setBindPhone("");
      setBindCode("");
    } catch (err) {
      setNotice(err instanceof Error ? err.message : String(err));
    } finally {
      setBinding(false);
    }
  };

  const cardCls = "rounded-3xl border border-pink-100 bg-white/75 p-6 shadow-[0_16px_48px_rgba(159,95,122,.08)] backdrop-blur-sm";

  if (loading) {
    return (
      <AppShell eyebrow="会员中心" title="账号中心" description="加载中…">
        <p className="text-center text-sm text-[#b9a8ae]">正在读取账号信息…</p>
      </AppShell>
    );
  }

  if (notLoggedIn || !me) {
    return (
      <AppShell eyebrow="会员中心" title="账号中心" description="登录后查看云端作品、收藏与配额">
        <div className={`${cardCls} mx-auto max-w-md text-center`}>
          <p className="mb-4 text-[15px] text-[#6a5f64]">你还没有登录</p>
          <Link
            href="/login"
            className="inline-block rounded-xl bg-gradient-to-r from-pink-400 to-pink-500 px-8 py-3 text-[15px] font-semibold text-white shadow-lg shadow-pink-200/60 transition hover:opacity-90"
          >
            去登录 / 注册
          </Link>
          <p className="mt-4 text-xs text-[#b9a8ae]">不登录也能继续使用试色、AI 生图与 AR 试戴</p>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell eyebrow="会员中心" title="账号中心" description={`你好，${me.user.nickname}！管理你的账号信息与登录方式。`}>
      <div className="mx-auto grid w-full max-w-2xl gap-5">
        {notice && (
          <p className="rounded-xl border border-pink-100 bg-pink-50/80 px-4 py-2.5 text-sm text-[#cf6f99]">{notice}</p>
        )}

        {/* 档案 */}
        <section className={cardCls}>
          <h2 className="mb-4 text-base font-bold text-[#403b3e]">账号档案</h2>
          <dl className="mb-5 grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
            <div>
              <dt className="mb-0.5 text-xs text-[#b9a8ae]">昵称</dt>
              <dd className="font-medium text-[#4A4A4A]">{me.user.nickname}</dd>
            </div>
            <div>
              <dt className="mb-0.5 text-xs text-[#b9a8ae]">手机号</dt>
              <dd className="font-medium text-[#4A4A4A]">{me.user.phone ?? "未绑定"}</dd>
            </div>
            <div>
              <dt className="mb-0.5 text-xs text-[#b9a8ae]">邮箱</dt>
              <dd className="font-medium text-[#4A4A4A]">{me.user.email ?? "未绑定"}</dd>
            </div>
            <div>
              <dt className="mb-0.5 text-xs text-[#b9a8ae]">注册时间</dt>
              <dd className="font-medium text-[#4A4A4A]">{new Date(me.user.createdAt).toLocaleDateString("zh-CN")}</dd>
            </div>
          </dl>
          <div className="flex flex-wrap items-end gap-3">
            <div className="min-w-[180px] flex-1">
              <label htmlFor="nickname" className="mb-1 block text-xs text-[#b9a8ae]">修改昵称</label>
              <input
                id="nickname"
                value={nickname}
                onChange={(e) => setNickname(e.target.value)}
                maxLength={30}
                className="w-full rounded-xl border border-pink-200 bg-white/80 px-3 py-2 text-sm outline-none transition focus:border-pink-400 focus:ring-2 focus:ring-pink-100"
              />
            </div>
            <button
              type="button"
              onClick={handleSaveNickname}
              disabled={savingNickname || !nickname.trim()}
              className="rounded-xl bg-pink-400 px-5 py-2 text-sm font-semibold text-white transition hover:bg-pink-500 disabled:opacity-50"
            >
              {savingNickname ? "保存中…" : "保存"}
            </button>
          </div>
        </section>

        {/* 绑定手机号（微信新用户合规补绑，§5.1） */}
        {!me.user.phone && (
          <section className={`${cardCls} border-amber-200`}>
            <h2 className="mb-1 text-base font-bold text-[#403b3e]">绑定手机号</h2>
            <p className="mb-4 text-xs leading-relaxed text-[#b9a8ae]">
              你的微信账号还没有绑定手机号。绑定后可用手机号登录，也是找回账号的重要凭证（合规要求）。
            </p>
            <div className="space-y-3">
              <input
                type="tel"
                value={bindPhone}
                onChange={(e) => setBindPhone(e.target.value)}
                placeholder="11 位手机号"
                inputMode="numeric"
                className="w-full rounded-xl border border-pink-200 bg-white/80 px-3 py-2.5 text-sm outline-none transition focus:border-pink-400"
              />
              <div className="flex gap-2">
                <input
                  type="text"
                  value={bindCode}
                  onChange={(e) => setBindCode(e.target.value)}
                  placeholder="6 位验证码"
                  inputMode="numeric"
                  maxLength={6}
                  className="min-w-0 flex-1 rounded-xl border border-pink-200 bg-white/80 px-3 py-2.5 text-sm outline-none transition focus:border-pink-400"
                />
                <button
                  type="button"
                  onClick={handleRequestBindCode}
                  disabled={bindCountdown > 0 || binding}
                  className="shrink-0 rounded-xl border border-pink-200 bg-pink-50 px-4 text-sm font-semibold text-[#cf6f99] transition hover:bg-pink-100 disabled:opacity-50"
                >
                  {bindCountdown > 0 ? `${bindCountdown}s` : "获取验证码"}
                </button>
              </div>
              {bindCaptchaVisible && (
                <div className="rounded-xl border border-pink-100 bg-pink-50/60 p-3">
                  <div className="mb-2 flex items-center justify-between">
                    <p className="text-xs font-medium text-[#6a5f64]">人机验证：请输入图中的字符</p>
                    <button
                      type="button"
                      onClick={fetchBindCaptcha}
                      className="text-xs text-[#cf6f99] underline-offset-2 hover:underline"
                    >
                      换一张
                    </button>
                  </div>
                  <div className="flex items-center gap-3">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={bindCaptchaUrl} alt="人机验证码" width={140} height={48} className="rounded-lg border border-pink-200 bg-white" />
                    <input
                      type="text"
                      value={bindCaptchaInput}
                      onChange={(e) => setBindCaptchaInput(e.target.value)}
                      placeholder="输入字符"
                      maxLength={6}
                      className="min-w-0 flex-1 rounded-xl border border-pink-200 bg-white/80 px-3 py-2 text-sm uppercase outline-none transition focus:border-pink-400"
                    />
                  </div>
                </div>
              )}
              {bindDevCode && (
                <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700">
                  开发模式：验证码为 <b>{bindDevCode}</b>
                </p>
              )}
              <button
                type="button"
                onClick={handleBindPhone}
                disabled={binding}
                className="w-full rounded-xl bg-gradient-to-r from-amber-400 to-pink-500 py-2.5 text-sm font-semibold text-white transition hover:opacity-90 disabled:opacity-50"
              >
                {binding ? "绑定中…" : "确认绑定"}
              </button>
            </div>
          </section>
        )}

        {/* 登录方式管理（§5.2） */}
        <section className={cardCls}>
          <h2 className="mb-1 text-base font-bold text-[#403b3e]">登录方式</h2>
          <p className="mb-4 text-xs text-[#b9a8ae]">任一方式均可登录同一账号，至少保留一种</p>
          <ul className="space-y-2.5">
            {me.identities.map((id) => (
              <li key={id.provider} className="flex items-center justify-between rounded-xl border border-pink-100 bg-white/70 px-4 py-3">
                <div>
                  <p className="text-sm font-semibold text-[#4A4A4A]">{PROVIDER_LABEL[id.provider] ?? id.provider}</p>
                  <p className="text-xs text-[#b9a8ae]">{id.identifier}</p>
                </div>
                <button
                  type="button"
                  onClick={() => handleUnbind(id.provider)}
                  disabled={me.identities.length <= 1}
                  className="rounded-lg border border-pink-200 px-3 py-1.5 text-xs font-medium text-[#cf6f99] transition hover:bg-pink-50 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  解绑
                </button>
              </li>
            ))}
          </ul>
        </section>

        {/* 改进计划偏好（§5.6，账号级，联动 localStorage） */}
        <section className={cardCls}>
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="mb-1 text-base font-bold text-[#403b3e]">用户改进计划</h2>
              <p className="text-xs leading-relaxed text-[#b9a8ae]">
                开启时手部照片等数据可能被用于产品改进（去标识化后使用）；关闭后不会上传任何数据。
                此偏好以账号为准，并同步到当前设备。
              </p>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={improvementEnabled}
              onClick={() => handleToggleImprovement(!improvementEnabled)}
              className={`relative h-7 w-12 shrink-0 rounded-full transition ${improvementEnabled ? "bg-pink-400" : "bg-gray-300"}`}
            >
              <span
                className={`absolute top-0.5 h-6 w-6 rounded-full bg-white shadow transition-all ${improvementEnabled ? "left-[22px]" : "left-0.5"}`}
              />
            </button>
          </div>
        </section>

        {/* 退出登录 */}
        <section className={cardCls}>
          <button
            type="button"
            onClick={handleLogout}
            className="w-full rounded-xl border border-red-100 bg-red-50/70 py-3 text-sm font-semibold text-red-500 transition hover:bg-red-50"
          >
            退出登录
          </button>
        </section>
      </div>
    </AppShell>
  );
}
