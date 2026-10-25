/**
 * 个人档案字段契约（浏览器与服务端共用，纯函数、不依赖 Node/DOM 专有 API）。
 *
 * 昵称、简介、联系方式与头像 Data URL 的规范化与校验口径集中在此：
 * 前端实时校验、服务端 PATCH /api/me 校验复用同一实现，避免两端规则漂移。
 * 头像最终以压缩后的 data URL 存入 users.avatar（见 `/account` 资料编辑卡片）。
 */

/** 档案字段上限与头像规格（前后端同源口径） */
export const PROFILE_LIMITS = {
  nicknameMin: 1,
  nicknameMax: 30,
  bioMax: 120,
  contactMax: 40,
  /** 存档头像 Data URL 解码后的字节上限 */
  avatarMaxBytes: 300 * 1024,
  /** 用户选择原图的文件字节上限（压缩前） */
  avatarMaxFileBytes: 5 * 1024 * 1024,
  /** 客户端压缩后的正方形边长（CSS px） */
  avatarSize: 256,
} as const;

export type ContactType = "wechat" | "email" | "phone" | "other";

export const CONTACT_TYPE_OPTIONS: ReadonlyArray<{
  value: ContactType;
  label: string;
  placeholder: string;
}> = [
  { value: "wechat", label: "微信号", placeholder: "例如 jiaru_nails" },
  { value: "email", label: "邮箱", placeholder: "例如 hello@jiaru.app" },
  { value: "phone", label: "手机号", placeholder: "11 位手机号" },
  { value: "other", label: "其他", placeholder: "例如 小红书 @甲如" },
];

export type ProfileField = "nickname" | "bio" | "contact";

export type ProfileFieldErrors = Partial<Record<ProfileField, string>>;

export interface ProfileInput {
  nickname: string;
  bio: string;
  contactType: ContactType;
  contact: string;
}

export interface ProfileValidation {
  ok: boolean;
  errors: ProfileFieldErrors;
  value: ProfileInput;
}

/** 字符数按码点计算，避免 emoji 被算作 2 个字符 */
export function countChars(value: string): number {
  return Array.from(value).length;
}

export function isContactType(value: unknown): value is ContactType {
  return typeof value === "string" && CONTACT_TYPE_OPTIONS.some((option) => option.value === value);
}

export function contactTypeLabel(value: string | null | undefined): string {
  return CONTACT_TYPE_OPTIONS.find((option) => option.value === value)?.label ?? "联系方式";
}

export function contactTypePlaceholder(value: string | null | undefined): string {
  return CONTACT_TYPE_OPTIONS.find((option) => option.value === value)?.placeholder ?? "联系方式";
}

const CONTROL_CHAR_RE = /[\u0000-\u001f\u007f]/;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
const CN_MOBILE_RE = /^1[3-9]\d{9}$/;
const WECHAT_ID_RE = /^(?:wxid_[A-Za-z0-9_-]{4,30}|[A-Za-z][A-Za-z0-9_-]{5,19})$/;

/** 手机号归一：去掉空格/连字符与 +86 前缀，便于同一号码只存一种写法 */
export function normalizeContactValue(type: ContactType, raw: string): string {
  const trimmed = raw.trim();
  if (type !== "phone") return trimmed;
  const compact = trimmed.replace(/[\s-]/g, "");
  return compact.replace(/^\+?86(?=1[3-9]\d{9}$)/, "");
}

/** 单个联系方式的值校验；返回 null 表示通过 */
export function validateContactValue(type: ContactType, raw: string): string | null {
  const value = normalizeContactValue(type, raw);
  if (!value) return null; // 空值表示不填写，由调用方决定是否允许
  if (countChars(value) > PROFILE_LIMITS.contactMax) {
    return `联系方式最多 ${PROFILE_LIMITS.contactMax} 个字符`;
  }
  if (CONTROL_CHAR_RE.test(value)) return "联系方式不能包含换行或控制字符";
  switch (type) {
    case "wechat":
      return WECHAT_ID_RE.test(value) ? null : "微信号需以字母开头，6-20 位字母、数字、下划线或减号";
    case "email":
      return EMAIL_RE.test(value) ? null : "请填写有效邮箱地址";
    case "phone":
      return CN_MOBILE_RE.test(value) ? null : "请填写 11 位手机号";
    default:
      return countChars(value) >= 2 ? null : "请至少填写 2 个字符";
  }
}

/**
 * 完整档案校验（昵称必填、简介选填、联系方式选填但填了必须符合所选类型）。
 * 返回规范化后的值，调用方以此写库，避免把首尾空格写进档案。
 */
export function validateProfileInput(input: {
  nickname: string;
  bio?: string | null;
  contactType?: string | null;
  contact?: string | null;
}): ProfileValidation {
  const nickname = (input.nickname ?? "").trim();
  const bio = (input.bio ?? "").trim();
  const contactType: ContactType = isContactType(input.contactType) ? input.contactType : "wechat";
  const contact = normalizeContactValue(contactType, input.contact ?? "");
  const errors: ProfileFieldErrors = {};

  const nicknameLength = countChars(nickname);
  if (nicknameLength < PROFILE_LIMITS.nicknameMin) {
    errors.nickname = "请填写昵称";
  } else if (nicknameLength > PROFILE_LIMITS.nicknameMax) {
    errors.nickname = `昵称最多 ${PROFILE_LIMITS.nicknameMax} 个字符`;
  } else if (CONTROL_CHAR_RE.test(nickname)) {
    errors.nickname = "昵称不能包含换行或控制字符";
  }

  if (countChars(bio) > PROFILE_LIMITS.bioMax) {
    errors.bio = `简介最多 ${PROFILE_LIMITS.bioMax} 个字符`;
  }

  if (contact) {
    const contactError = validateContactValue(contactType, contact);
    if (contactError) errors.contact = contactError;
  }

  return {
    ok: Object.keys(errors).length === 0,
    errors,
    value: { nickname, bio, contactType, contact },
  };
}

/** 按固定顺序返回第一条错误，供服务端 `{error}` 文案使用 */
export function firstProfileError(errors: ProfileFieldErrors): string | null {
  for (const field of ["nickname", "bio", "contact"] as const) {
    if (errors[field]) return errors[field] ?? null;
  }
  return null;
}

export type AvatarParseResult =
  | { ok: true; dataUrl: string | null }
  | { ok: false; error: string };

const AVATAR_DATA_URL_RE = /^data:image\/(png|jpeg|webp);base64,([A-Za-z0-9+/]+={0,2})$/;

function base64ByteLength(base64: string): number {
  const padding = base64.endsWith("==") ? 2 : base64.endsWith("=") ? 1 : 0;
  return Math.floor((base64.length * 3) / 4) - padding;
}

function signatureMatches(mime: string, head: string): boolean {
  if (mime === "png") return head.startsWith("\u0089PNG");
  if (mime === "jpeg") {
    return head.length >= 3 && head.charCodeAt(0) === 0xff && head.charCodeAt(1) === 0xd8 && head.charCodeAt(2) === 0xff;
  }
  return head.slice(0, 4) === "RIFF" && head.slice(8, 12) === "WEBP";
}

/**
 * 头像 Data URL 校验：只接受 PNG/JPEG/WebP，限制解码后字节数，
 * 并核对文件签名，防止把任意字符串写进档案字段后当作图片渲染。
 * `null` / 空串表示清除头像。
 */
export function parseAvatarDataUrl(value: unknown): AvatarParseResult {
  if (value === null || value === undefined) return { ok: true, dataUrl: null };
  if (typeof value !== "string") return { ok: false, error: "头像数据格式不正确" };
  const trimmed = value.trim();
  if (!trimmed) return { ok: true, dataUrl: null };

  const match = AVATAR_DATA_URL_RE.exec(trimmed);
  if (!match) return { ok: false, error: "头像仅支持 PNG、JPEG 或 WebP 图片" };

  const mime = match[1];
  const base64 = match[2];
  if (base64ByteLength(base64) > PROFILE_LIMITS.avatarMaxBytes) {
    return { ok: false, error: "头像图片过大，请重新选择（压缩后上限 300KB）" };
  }

  let head: string;
  try {
    head = atob(base64.slice(0, 16));
  } catch {
    return { ok: false, error: "头像数据无法解码，请重新选择图片" };
  }
  if (!signatureMatches(mime, head)) {
    return { ok: false, error: "头像图片内容与格式不一致，请重新选择图片" };
  }
  return { ok: true, dataUrl: trimmed };
}

/** `GET/PATCH /api/me` 返回的档案字段（与 src/lib/auth/types.ts 的 MeResult.user 对应） */
export interface ProfileUser {
  id: string;
  phone: string | null;
  email: string | null;
  nickname: string;
  avatar: string | null;
  bio: string | null;
  contact: string | null;
  contactType: string | null;
  ageGroup: string | null;
  status: string;
  createdAt: number;
}

/** 从档案对象取出可编辑字段（缺失字段按空值处理） */
export function toProfileInput(user: Pick<ProfileUser, "nickname" | "bio" | "contact" | "contactType">): ProfileInput {
  return {
    nickname: user.nickname ?? "",
    bio: user.bio ?? "",
    contactType: isContactType(user.contactType) ? user.contactType : "wechat",
    contact: user.contact ?? "",
  };
}

/** 档案之间的脏值比较：只列实际变化的字段，保存时据此只提交变更项 */
export function diffProfileFields(before: ProfileInput, after: ProfileInput): Array<keyof ProfileInput> {
  const changed: Array<keyof ProfileInput> = [];
  if (before.nickname !== after.nickname) changed.push("nickname");
  if (before.bio !== after.bio) changed.push("bio");
  if (before.contact !== after.contact || before.contactType !== after.contactType) changed.push("contact");
  return changed;
}
