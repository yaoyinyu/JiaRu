"use client";

import { useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import {
  CONTACT_TYPE_OPTIONS,
  PROFILE_LIMITS,
  contactTypeLabel,
  contactTypePlaceholder,
  countChars,
  diffProfileFields,
  firstProfileError,
  parseAvatarDataUrl,
  toProfileInput,
  validateProfileInput,
  type ProfileFieldErrors,
  type ProfileInput,
  type ProfileUser,
} from "@/lib/profile/profile";
import { AVATAR_ACCEPT, createAvatarDataUrl } from "@/lib/profile/avatar-image";

type ProfileEditorProps = {
  user: ProfileUser;
  /** 保存成功后回传最新档案，供页面同步其它区块（如标题问候语） */
  onSaved: (user: ProfileUser) => void;
};

type Feedback = { kind: "success" | "error"; message: string } | null;

const CARD =
  "rounded-3xl border border-pink-100 bg-white/75 p-6 shadow-[0_16px_48px_rgba(159,95,122,.08)] backdrop-blur-sm";
const INPUT_BASE =
  "rounded-xl border bg-white/80 px-3 py-2.5 text-sm text-[#4A4A4A] outline-none transition placeholder:text-[#c3b6bb] focus:ring-2 disabled:cursor-not-allowed disabled:opacity-60";
/** 独占整行的输入控件；联系方式行里由 flex-1 决定宽度，不能再叠加 w-full，否则会撑出栅格列 */
const INPUT_FULL = `${INPUT_BASE} w-full`;
const INPUT_OK = "border-pink-200 focus:border-pink-400 focus:ring-pink-100";
const INPUT_BAD = "border-red-300 bg-red-50/50 focus:border-red-400 focus:ring-red-100";
const LABEL = "mb-1.5 block text-xs font-medium text-[#938b90]";

function avatarInitial(nickname: string): string {
  const first = Array.from(nickname.trim())[0];
  return first ? first.toUpperCase() : "甲";
}

/** 头像展示：有图用图片，无图用渐变首字，保持与页面同色系 */
function AvatarView({ avatar, nickname, size }: { avatar: string | null; nickname: string; size: number }) {
  const dimension = { width: size, height: size };
  if (avatar) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={avatar}
        alt={`${nickname || "用户"}的头像`}
        width={size}
        height={size}
        style={dimension}
        className="h-full w-full rounded-full object-cover shadow-[0_10px_26px_rgba(159,95,122,.18)]"
      />
    );
  }
  return (
    <span
      aria-hidden
      style={dimension}
      className="flex items-center justify-center rounded-full bg-gradient-to-br from-pink-200 via-pink-100 to-purple-100 text-2xl font-semibold text-[#b95f87] shadow-[inset_0_1px_0_rgba(255,255,255,.9),0_10px_26px_rgba(159,95,122,.12)]"
    >
      {avatarInitial(nickname)}
    </span>
  );
}

/** 资料卡片骨架：与真实内容保持相同的卡片高度节奏，避免加载完成时跳动 */
export function ProfileSkeleton() {
  return (
    <section className={`${CARD} animate-pulse`} aria-busy="true" aria-live="polite">
      <div className="flex items-center gap-4" aria-hidden>
        <span className="h-[72px] w-[72px] shrink-0 rounded-full bg-pink-100/80" />
        <div className="min-w-0 flex-1 space-y-2">
          <span className="block h-4 w-32 rounded-full bg-pink-100/80" />
          <span className="block h-3 w-48 rounded-full bg-pink-50" />
        </div>
      </div>
      <div className="mt-5 space-y-2">
        <span className="block h-3 w-3/4 rounded-full bg-pink-50" />
        <span className="block h-3 w-1/2 rounded-full bg-pink-50" />
      </div>
      <div className="mt-5 flex gap-3">
        <span className="h-9 w-24 rounded-xl bg-pink-100/70" />
        <span className="h-9 w-24 rounded-xl bg-pink-50" />
      </div>
      <span className="sr-only">正在加载个人资料</span>
    </section>
  );
}

/**
 * 个人资料查看 / 编辑卡片。
 * - 查看态展示头像、昵称、简介、公开联系方式，并为空字段提供补充入口；
 * - 编辑态支持头像替换与移除、字段实时校验、保存与取消（未保存修改需确认）；
 * - 保存成功或失败在卡片内给出可读反馈（role=status / role=alert）。
 */
export function ProfileEditor({ user, onSaved }: ProfileEditorProps) {
  const [editing, setEditing] = useState(false);
  const baseline = toProfileInput(user);
  const [draft, setDraft] = useState<ProfileInput>(baseline);
  const [avatar, setAvatar] = useState<string | null>(user.avatar);
  const [errors, setErrors] = useState<ProfileFieldErrors>({});
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [saving, setSaving] = useState(false);
  const [avatarBusy, setAvatarBusy] = useState(false);

  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const nicknameRef = useRef<HTMLInputElement | null>(null);
  const bioRef = useRef<HTMLTextAreaElement | null>(null);
  const contactRef = useRef<HTMLInputElement | null>(null);
  const errorPrefix = useId();

  // 成功提示自动收起，错误提示保留到用户下一次操作
  useEffect(() => {
    if (feedback?.kind !== "success") return;
    const timer = window.setTimeout(() => setFeedback(null), 4000);
    return () => window.clearTimeout(timer);
  }, [feedback]);

  const changedFields = diffProfileFields(baseline, draft);
  const avatarChanged = avatar !== user.avatar;
  const dirty = changedFields.length > 0 || avatarChanged;

  const updateField = <K extends keyof ProfileInput>(key: K, value: ProfileInput[K]) => {
    setDraft((prev) => ({ ...prev, [key]: value }));
    const field = key === "contactType" ? "contact" : (key as keyof ProfileFieldErrors);
    if (errors[field]) setErrors((prev) => ({ ...prev, [field]: undefined }));
    if (feedback?.kind === "error") setFeedback(null);
  };

  const handleAvatarPick = async (file: File | undefined) => {
    if (!file) return;
    setAvatarBusy(true);
    setFeedback(null);
    try {
      const dataUrl = await createAvatarDataUrl(file);
      const parsed = parseAvatarDataUrl(dataUrl);
      if (!parsed.ok) throw new Error(parsed.error);
      setAvatar(parsed.dataUrl);
    } catch (err) {
      setFeedback({ kind: "error", message: err instanceof Error ? err.message : String(err) });
    } finally {
      setAvatarBusy(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const startEditing = () => {
    setDraft(baseline);
    setAvatar(user.avatar);
    setErrors({});
    setFeedback(null);
    setEditing(true);
    window.setTimeout(() => nicknameRef.current?.focus(), 0);
  };

  const cancelEditing = () => {
    if (saving) return;
    if (dirty && !window.confirm("放弃未保存的修改？")) return;
    setDraft(baseline);
    setAvatar(user.avatar);
    setErrors({});
    setFeedback(null);
    setEditing(false);
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (saving || avatarBusy) return;

    const validation = validateProfileInput(draft);
    setErrors(validation.errors);
    if (!validation.ok) {
      setFeedback({ kind: "error", message: firstProfileError(validation.errors) ?? "请检查填写内容" });
      if (validation.errors.nickname) nicknameRef.current?.focus();
      else if (validation.errors.contact) contactRef.current?.focus();
      else if (validation.errors.bio) bioRef.current?.focus();
      return;
    }

    const changed = diffProfileFields(baseline, validation.value);
    const payload: Record<string, unknown> = {};
    if (changed.includes("nickname")) payload.nickname = validation.value.nickname;
    if (changed.includes("bio")) payload.bio = validation.value.bio;
    if (changed.includes("contact")) {
      payload.contact = validation.value.contact;
      payload.contactType = validation.value.contactType;
    }
    if (avatarChanged) payload.avatar = avatar;

    if (Object.keys(payload).length === 0) {
      setEditing(false);
      setFeedback({ kind: "success", message: "没有需要保存的修改" });
      return;
    }

    setSaving(true);
    setFeedback(null);
    try {
      const resp = await fetch("/api/me", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = (await resp.json().catch(() => null)) as
        | { user?: { user?: ProfileUser }; error?: string }
        | null;
      if (!resp.ok) throw new Error(data?.error || `保存失败（${resp.status}）`);
      const updated = data?.user?.user;
      if (!updated) throw new Error("保存响应缺少档案数据，请刷新后确认");
      onSaved(updated);
      setDraft(toProfileInput(updated));
      setAvatar(updated.avatar);
      setErrors({});
      setEditing(false);
      setFeedback({ kind: "success", message: "个人资料已保存" });
    } catch (err) {
      setFeedback({ kind: "error", message: err instanceof Error ? err.message : String(err) });
    } finally {
      setSaving(false);
    }
  };

  const handleFormKeyDown = (event: KeyboardEvent<HTMLFormElement>) => {
    if (event.key !== "Escape") return;
    event.stopPropagation();
    cancelEditing();
  };

  const feedbackNode = feedback ? (
    <p
      role={feedback.kind === "error" ? "alert" : "status"}
      aria-live="polite"
      className={`rounded-xl border px-4 py-2.5 text-sm ${
        feedback.kind === "error"
          ? "border-red-200 bg-red-50/80 text-red-600"
          : "border-pink-200 bg-pink-50/80 text-[#cf6f99]"
      }`}
    >
      {feedback.message}
    </p>
  ) : null;

  const bioCount = countChars(draft.bio);
  const nicknameCount = countChars(draft.nickname);

  return (
    <section className={CARD} aria-labelledby={`${errorPrefix}-profile-heading`} aria-busy={saving}>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id={`${errorPrefix}-profile-heading`} className="text-base font-bold text-[#403b3e]">
            个人资料
          </h2>
          <p className="mt-1 text-xs leading-relaxed text-[#b9a8ae]">
            头像、昵称、简介与联系方式会展示在你的个人主页；联系方式仅用于对外联系，不参与登录。
          </p>
        </div>
        {!editing && (
          <button
            type="button"
            onClick={startEditing}
            className="shrink-0 rounded-xl border border-pink-200 bg-pink-50 px-4 py-2 text-sm font-semibold text-[#cf6f99] transition hover:bg-pink-100"
          >
            编辑资料
          </button>
        )}
      </div>

      {feedbackNode && <div className="mb-4">{feedbackNode}</div>}

      {editing ? (
        <form onSubmit={handleSubmit} onKeyDown={handleFormKeyDown} noValidate>
          <fieldset disabled={saving} className="min-w-0 space-y-5 disabled:opacity-80">
            {/* 头像 */}
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
              <span className="relative h-[76px] w-[76px] shrink-0">
                <AvatarView avatar={avatar} nickname={draft.nickname || user.nickname} size={76} />
                {avatarBusy && (
                  <span className="absolute inset-0 flex items-center justify-center rounded-full bg-white/70 text-[10px] font-medium text-[#cf6f99]">
                    处理中…
                  </span>
                )}
              </span>
              <div className="min-w-0">
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={avatarBusy}
                    className="rounded-xl border border-pink-200 bg-white/80 px-4 py-2 text-sm font-medium text-[#cf6f99] transition hover:bg-pink-50 disabled:opacity-50"
                  >
                    {avatar ? "更换头像" : "上传头像"}
                  </button>
                  {avatar && (
                    <button
                      type="button"
                      onClick={() => setAvatar(null)}
                      disabled={avatarBusy}
                      className="rounded-xl border border-[#eee3e8] bg-white/70 px-4 py-2 text-sm font-medium text-[#938b90] transition hover:bg-white disabled:opacity-50"
                    >
                      移除头像
                    </button>
                  )}
                </div>
                <p className="mt-2 text-xs leading-relaxed text-[#b9a8ae]">
                  支持 JPG / PNG / WebP，单张不超过 5MB；保存时会自动裁切为 {PROFILE_LIMITS.avatarSize}×
                  {PROFILE_LIMITS.avatarSize} 后再存储。
                </p>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept={AVATAR_ACCEPT}
                  className="sr-only"
                  aria-label="选择头像图片"
                  onChange={(event) => void handleAvatarPick(event.target.files?.[0])}
                />
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              {/* 昵称 */}
              <div className="min-w-0">
                <label htmlFor={`${errorPrefix}-nickname`} className={LABEL}>
                  昵称 <span className="text-[#cf6f99]">*</span>
                </label>
                <input
                  id={`${errorPrefix}-nickname`}
                  ref={nicknameRef}
                  value={draft.nickname}
                  onChange={(event) => updateField("nickname", event.target.value)}
                  maxLength={PROFILE_LIMITS.nicknameMax}
                  autoComplete="nickname"
                  aria-required
                  aria-invalid={Boolean(errors.nickname)}
                  aria-describedby={`${errorPrefix}-nickname-hint`}
                  className={`${INPUT_FULL} ${errors.nickname ? INPUT_BAD : INPUT_OK}`}
                  placeholder="给自己取个名字"
                />
                <p
                  id={`${errorPrefix}-nickname-hint`}
                  className={`mt-1 text-xs ${errors.nickname ? "text-red-500" : "text-[#b9a8ae]"}`}
                >
                  {errors.nickname ?? `${nicknameCount}/${PROFILE_LIMITS.nicknameMax} 个字符`}
                </p>
              </div>

              {/* 联系方式 */}
              <div className="min-w-0">
                <label htmlFor={`${errorPrefix}-contact`} className={LABEL}>
                  联系方式
                </label>
                <div className="flex min-w-0 gap-2">
                  <select
                    aria-label="联系方式类型"
                    value={draft.contactType}
                    onChange={(event) => updateField("contactType", event.target.value as ProfileInput["contactType"])}
                    className={`${INPUT_BASE} ${INPUT_OK} w-[88px] shrink-0`}
                  >
                    {CONTACT_TYPE_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                  <input
                    id={`${errorPrefix}-contact`}
                    ref={contactRef}
                    value={draft.contact}
                    onChange={(event) => updateField("contact", event.target.value)}
                    maxLength={PROFILE_LIMITS.contactMax}
                    aria-invalid={Boolean(errors.contact)}
                    aria-describedby={`${errorPrefix}-contact-hint`}
                    className={`${INPUT_BASE} ${errors.contact ? INPUT_BAD : INPUT_OK} min-w-0 flex-1`}
                    placeholder={contactTypePlaceholder(draft.contactType)}
                  />
                </div>
                <p
                  id={`${errorPrefix}-contact-hint`}
                  className={`mt-1 text-xs ${errors.contact ? "text-red-500" : "text-[#b9a8ae]"}`}
                >
                  {errors.contact ?? "选填，留空则不在主页展示"}
                </p>
              </div>
            </div>

            {/* 简介 */}
            <div>
              <label htmlFor={`${errorPrefix}-bio`} className={LABEL}>
                简介
              </label>
              <textarea
                id={`${errorPrefix}-bio`}
                ref={bioRef}
                value={draft.bio}
                onChange={(event) => updateField("bio", event.target.value)}
                maxLength={PROFILE_LIMITS.bioMax}
                rows={3}
                aria-invalid={Boolean(errors.bio)}
                aria-describedby={`${errorPrefix}-bio-hint`}
                className={`${INPUT_FULL} ${errors.bio ? INPUT_BAD : INPUT_OK} resize-y leading-relaxed`}
                placeholder="说说你的审美偏好，例如：偏爱奶咖色系、短圆甲型，日常通勤为主。"
              />
              <p
                id={`${errorPrefix}-bio-hint`}
                className={`mt-1 text-xs ${errors.bio ? "text-red-500" : "text-[#b9a8ae]"}`}
              >
                {errors.bio ?? `${bioCount}/${PROFILE_LIMITS.bioMax} 个字符`}
              </p>
            </div>
          </fieldset>

          <div className="mt-5 flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-end">
            <button
              type="button"
              onClick={cancelEditing}
              disabled={saving}
              className="rounded-xl border border-[#eee3e8] bg-white/70 px-5 py-2.5 text-sm font-medium text-[#6a5f64] transition hover:bg-white disabled:opacity-50"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={saving || avatarBusy || !dirty}
              className="rounded-xl bg-gradient-to-r from-pink-400 to-pink-500 px-6 py-2.5 text-sm font-semibold text-white shadow-lg shadow-pink-200/60 transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {saving ? "保存中…" : "保存"}
            </button>
          </div>
          {!dirty && (
            <p className="mt-2 text-right text-xs text-[#c3b6bb]">修改内容后可保存，按 Esc 可退出编辑</p>
          )}
        </form>
      ) : (
        <div className="space-y-4">
          <div className="flex items-center gap-4">
            <span className="h-[72px] w-[72px] shrink-0">
              <AvatarView avatar={user.avatar} nickname={user.nickname} size={72} />
            </span>
            <div className="min-w-0">
              <h3 className="truncate text-lg font-semibold text-[#403b3e]">{user.nickname}</h3>
              <p className="mt-0.5 text-xs text-[#b9a8ae]">
                加入于 {new Date(user.createdAt).toLocaleDateString("zh-CN")}
              </p>
            </div>
          </div>

          <div>
            <p className="mb-1 text-xs text-[#b9a8ae]">简介</p>
            {user.bio ? (
              <p className="whitespace-pre-line break-words text-sm leading-relaxed text-[#4A4A4A]">{user.bio}</p>
            ) : (
              <p className="rounded-xl border border-dashed border-pink-200/70 bg-pink-50/40 px-4 py-3 text-sm text-[#b9a8ae]">
                还没有填写简介，
                <button type="button" onClick={startEditing} className="font-medium text-[#cf6f99] underline-offset-2 hover:underline">
                  补充一句
                </button>
                让主页更有辨识度。
              </p>
            )}
          </div>

          <div>
            <p className="mb-1 text-xs text-[#b9a8ae]">联系方式</p>
            {user.contact ? (
              <p className="inline-flex max-w-full items-center gap-2 rounded-full border border-pink-100 bg-pink-50/70 px-3.5 py-1.5 text-sm text-[#4A4A4A]">
                <span className="shrink-0 text-xs text-[#cf6f99]">{contactTypeLabel(user.contactType)}</span>
                <span className="truncate">{user.contact}</span>
              </p>
            ) : (
              <p className="text-sm text-[#b9a8ae]">未填写，点击「编辑资料」添加</p>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
