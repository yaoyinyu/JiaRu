"use client";

import Link from "next/link";
import { buildAnalysisBridgeParams } from "@/lib/nail-personalization/bridge.ts";
import {
  describeWarning,
  presentRecommendation,
  summarizeHandProfile,
  summarizeNailHealth,
  summarizeSkinTone,
} from "@/lib/nail-personalization/present.ts";
import type { PersonalizationResult, Recommendation } from "@/lib/nail-personalization/types.ts";

const SEVERITY_CLASS: Record<"ok" | "review" | "info", string> = {
  ok: "border-emerald-200 bg-emerald-50/70 text-emerald-800",
  review: "border-amber-200 bg-amber-50/80 text-amber-900",
  info: "border-slate-200 bg-[var(--surface)] text-[#67685f]",
};

function SummaryCard({
  title,
  severity,
  messages,
  stats,
}: {
  title: string;
  severity: "ok" | "review" | "info";
  messages: string[];
  stats?: Array<{ label: string; value: string }>;
}) {
  return (
    <section className={`rounded-[24px] border px-4 py-3 ${SEVERITY_CLASS[severity]}`}>
      <h3 className="text-sm font-semibold">{title}</h3>
      <ul className="mt-2 space-y-1 text-xs leading-5">
        {messages.map((message) => (
          <li key={message}>{message}</li>
        ))}
      </ul>
      {stats && stats.length > 0 ? (
        <dl className="mt-3 grid grid-cols-2 gap-2 text-[11px] sm:grid-cols-3">
          {stats.map((stat) => (
            <div key={stat.label} className="rounded-xl bg-[var(--surface)] px-2 py-1">
              <dt className="text-[#75766c]">{stat.label}</dt>
              <dd className="font-medium">{stat.value}</dd>
            </div>
          ))}
        </dl>
      ) : null}
    </section>
  );
}

interface NailAnalysisResultProps {
  result: PersonalizationResult;
}

export function NailAnalysisResult({ result }: NailAnalysisResultProps) {
  const handProfile = summarizeHandProfile(result.handProfile);
  const skinTone = summarizeSkinTone(result.skinTone);
  const nailHealth = summarizeNailHealth(result.nailHealth);
  const auxiliary = result.notices.includes("auxiliary_analysis_notice");

  return (
    <div className="space-y-4">
      {auxiliary ? (
        <p role="status" className="rounded-[20px] border border-amber-300 bg-amber-50 px-4 py-3 text-xs leading-5 text-amber-900">
          {describeWarning("auxiliary_analysis_notice")}
        </p>
      ) : null}

      {result.noCandidates ? (
        <p role="alert" className="rounded-[20px] border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          {describeWarning("no_candidates_no_recommendation")}
        </p>
      ) : null}

      {result.notices
        .filter((code) => code !== "auxiliary_analysis_notice")
        .map((code) => (
          <p key={code} className="rounded-2xl border border-slate-200 bg-[var(--surface)] px-4 py-2 text-xs text-[#67685f]">
            {describeWarning(code)}
          </p>
        ))}

      <SummaryCard
        title={handProfile.title}
        severity={handProfile.severity}
        messages={handProfile.messages}
        stats={handProfile.stats}
      />

      {skinTone ? (
        <SummaryCard
          title={skinTone.title}
          severity={skinTone.severity}
          messages={skinTone.messages}
          stats={skinTone.stats}
        />
      ) : (
        <p className="rounded-2xl border border-slate-200 bg-[var(--surface)] px-4 py-2 text-xs text-[#75766c]">
          肤色采样质量不足，已隐藏肤色分析，颜色建议改用场合与风格规则。
        </p>
      )}

      {nailHealth ? (
        <SummaryCard title={nailHealth.title} severity={nailHealth.severity} messages={nailHealth.messages} />
      ) : (
        <p className="rounded-2xl border border-slate-200 bg-[var(--surface)] px-4 py-2 text-xs text-[#75766c]">
          {describeWarning("nail_health_requires_mask")}
        </p>
      )}

      {result.recommendations.length > 0 ? (
        <div className="space-y-3">
          <h3 className="text-sm font-semibold text-[#292a27]">推荐方案</h3>
          {result.recommendations.map((rec: Recommendation) => {
            const summary = presentRecommendation(rec);
            const params = buildAnalysisBridgeParams(rec);
            return (
              <article
                key={rec.id}
                className={`rounded-[24px] border px-4 py-3 ${SEVERITY_CLASS[summary.severity]}`}
              >
                <header className="flex flex-wrap items-baseline justify-between gap-2">
                  <h4 className="text-sm font-semibold">{summary.messages[0]}</h4>
                  <span className="text-[11px] opacity-80">组合分 {rec.score.toFixed(2)}</span>
                </header>
                <ul className="mt-2 space-y-1 text-xs leading-5">
                  {summary.messages.slice(1).map((message) => (
                    <li key={message}>{message}</li>
                  ))}
                </ul>
                <div className="mt-3 flex flex-wrap gap-2">
                  {rec.colors.presetNames.map((name) => (
                    <Link
                      key={name}
                      href={`/editor?preset=${encodeURIComponent(name)}`}
                      className="rounded-full bg-[var(--surface)] px-3 py-1.5 text-xs font-medium shadow-sm transition hover:bg-[var(--surface)]"
                    >
                      用「{name}」去试色
                    </Link>
                  ))}
                  <span className="sr-only">桥接参数：{params.shape}</span>
                </div>
              </article>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
