"use client";

import type {
  LengthAdvice,
  ManualLabor,
  NailCondition,
  Occasion,
  StylePreference,
  Undertone,
  UserScenario,
} from "@/lib/nail-personalization/types.ts";

const OCCASION_OPTIONS: ReadonlyArray<{ value: Occasion; label: string }> = [
  { value: "daily", label: "日常" },
  { value: "work", label: "职场通勤" },
  { value: "party", label: "派对" },
  { value: "wedding", label: "婚礼" },
  { value: "date", label: "约会" },
  { value: "vacation", label: "度假" },
];

const STYLE_OPTIONS: ReadonlyArray<{ value: StylePreference; label: string }> = [
  { value: "natural", label: "自然" },
  { value: "low-maintenance", label: "低维护" },
  { value: "elegant", label: "优雅" },
  { value: "bold", label: "夸张" },
  { value: "trendy", label: "流行" },
];

const LABOR_OPTIONS: ReadonlyArray<{ value: ManualLabor; label: string }> = [
  { value: "none", label: "很少" },
  { value: "light", label: "一般（键盘/家务）" },
  { value: "heavy", label: "较多（体力/手工）" },
];

const LENGTH_OPTIONS: ReadonlyArray<{ value: LengthAdvice; label: string }> = [
  { value: "short", label: "短甲" },
  { value: "medium", label: "中长甲" },
  { value: "long", label: "长甲" },
];

const UNDERTONE_OPTIONS: ReadonlyArray<{ value: Undertone; label: string }> = [
  { value: "warm", label: "暖调" },
  { value: "cool", label: "冷调" },
  { value: "neutral", label: "中性" },
  { value: "olive", label: "橄榄调" },
];

const CONDITION_OPTIONS: ReadonlyArray<{ value: NailCondition; label: string }> = [
  { value: "healthy", label: "正常" },
  { value: "thin-soft", label: "薄软" },
  { value: "brittle", label: "易断" },
];

const UNSET = "";

const fieldClass =
  "min-h-11 w-full rounded-2xl bg-[var(--surface)] px-3 py-2 text-sm text-[#292a27] shadow-sm outline-none transition focus:border-[#ac5145]";
const labelClass = "mb-1 block text-xs font-medium text-[#75766c]";

interface NailAnalysisFormProps {
  value: UserScenario;
  onChange: (next: UserScenario) => void;
  disabled?: boolean;
}

export function NailAnalysisForm({ value, onChange, disabled = false }: NailAnalysisFormProps) {
  function update<K extends keyof UserScenario>(key: K, next: UserScenario[K] | undefined) {
    const draft: UserScenario = { ...value };
    if (next === undefined) delete draft[key];
    else draft[key] = next;
    onChange(draft);
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <div>
        <label className={labelClass} htmlFor="na-occasion">使用场景（必填）</label>
        <select
          id="na-occasion"
          className={fieldClass}
          value={value.occasion}
          disabled={disabled}
          onChange={(event) => update("occasion", event.target.value as Occasion)}
        >
          {OCCASION_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
      </div>

      <div>
        <label className={labelClass} htmlFor="na-style">风格偏好（可不填）</label>
        <select
          id="na-style"
          className={fieldClass}
          value={value.style ?? UNSET}
          disabled={disabled}
          onChange={(event) =>
            update("style", event.target.value === UNSET ? undefined : (event.target.value as StylePreference))
          }
        >
          <option value={UNSET}>不指定</option>
          {STYLE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
      </div>

      <div>
        <label className={labelClass} htmlFor="na-labor">手部劳作强度（可不填）</label>
        <select
          id="na-labor"
          className={fieldClass}
          value={value.manualLabor ?? UNSET}
          disabled={disabled}
          onChange={(event) =>
            update("manualLabor", event.target.value === UNSET ? undefined : (event.target.value as ManualLabor))
          }
        >
          <option value={UNSET}>不指定</option>
          {LABOR_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
      </div>

      <div>
        <label className={labelClass} htmlFor="na-length">长度偏好（可不填）</label>
        <select
          id="na-length"
          className={fieldClass}
          value={value.lengthPreference ?? UNSET}
          disabled={disabled}
          onChange={(event) =>
            update("lengthPreference", event.target.value === UNSET ? undefined : (event.target.value as LengthAdvice))
          }
        >
          <option value={UNSET}>不指定</option>
          {LENGTH_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
      </div>

      <div>
        <label className={labelClass} htmlFor="na-undertone">自评底调（覆盖测量值）</label>
        <select
          id="na-undertone"
          className={fieldClass}
          value={value.selfReportedUndertone ?? UNSET}
          disabled={disabled}
          onChange={(event) =>
            update(
              "selfReportedUndertone",
              event.target.value === UNSET ? undefined : (event.target.value as Undertone)
            )
          }
        >
          <option value={UNSET}>使用照片测得值</option>
          {UNDERTONE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
      </div>

      <div>
        <label className={labelClass} htmlFor="na-condition">甲面状况（可不填）</label>
        <select
          id="na-condition"
          className={fieldClass}
          value={value.nailCondition ?? UNSET}
          disabled={disabled}
          onChange={(event) =>
            update("nailCondition", event.target.value === UNSET ? undefined : (event.target.value as NailCondition))
          }
        >
          <option value={UNSET}>不指定</option>
          {CONDITION_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
      </div>

      <div className="sm:col-span-2">
        <label className="flex min-h-11 items-center gap-2 text-xs text-[#75766c]">
          <input
            type="checkbox"
            className="h-5 w-5 rounded border-[#d9b3a6] text-[#ac5145]"
            checked={value.hasAllergyHistory ?? false}
            disabled={disabled}
            onChange={(event) => update("hasAllergyHistory", event.target.checked || undefined)}
          />
          我有美甲材料过敏史（仅用于提示，不影响推荐排序）
        </label>
        {value.hasAllergyHistory ? (
          <p className="mt-2 rounded-2xl border border-amber-200 bg-amber-50/80 px-3 py-2 text-xs text-amber-800">
            建议到店前与美甲师确认材料成分；本功能不做材料安全性判断。
          </p>
        ) : null}
      </div>
    </div>
  );
}
