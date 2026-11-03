"use client";

/**
 * 识别模式 hook（v1.2.216）：为三个识别站点（编辑器 / AR 选择器 / 个性化分析）
 * 提供「本地 | 云端」模式状态、云端后端可用性探测与一次性隐私确认。
 *
 * - 模式为会话级状态：默认本地，不持久化（本地优先口径）。
 * - 云端确认键 `jiaru.nail-detect-cloud-consent.v1`（见 nail-detect-mode.ts）。
 * - 可用性探测只读两个路由的 GET（不触发推理），失败一律按不可用处理。
 */
import { useCallback, useEffect, useState } from "react";

import {
  readNailCloudConsent,
  resolveDefaultCloudBackend,
  writeNailCloudConsent,
  type NailCloudAvailability,
  type NailCloudBackend,
  type NailDetectMode,
} from "@/lib/nail-detect-mode";

const ARK_DETECT_PROBE_ENDPOINT = "/api/nail-detect-ark";
const CLOUD_MATTE_PROBE_ENDPOINT = "/api/nail-matte-cloud";

async function probeEndpoint(
  endpoint: string,
  fetchImpl: typeof fetch
): Promise<boolean> {
  try {
    const response = await fetchImpl(endpoint, { cache: "no-store" });
    if (!response.ok) return false;
    const body = (await response.json()) as Record<string, unknown>;
    return body.enabled === true;
  } catch {
    return false;
  }
}

export interface NailDetectModeState {
  mode: NailDetectMode;
  /** 切换模式；云端是否可用与同意门由 NailDetectModeSwitch 把关。 */
  setMode: (mode: NailDetectMode) => void;
  backend: NailCloudBackend;
  setBackend: (backend: NailCloudBackend) => void;
  availability: NailCloudAvailability;
  /** 可用性探测是否已返回（未返回前云端 chip 保持可用，运行时判决兜底）。 */
  availabilityLoaded: boolean;
  consentGiven: boolean;
  /** 写入一次性隐私确认并刷新状态。 */
  acknowledgeCloudConsent: () => void;
}

export function useNailDetectMode(
  options: { fetchImpl?: typeof fetch } = {}
): NailDetectModeState {
  const fetchImpl = options.fetchImpl ?? fetch;
  const [mode, setMode] = useState<NailDetectMode>("local");
  const [backend, setBackend] = useState<NailCloudBackend>("ark");
  const [availability, setAvailability] = useState<NailCloudAvailability>({
    ark: false,
    cloudMatte: false,
  });
  const [availabilityLoaded, setAvailabilityLoaded] = useState(false);
  const [consentGiven, setConsentGiven] = useState(false);

  useEffect(() => {
    // 挂载路径不得同步 setState（react-hooks/set-state-in-effect）：确认读取
    // 与探测落库都经微任务/异步路径。
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      setConsentGiven(readNailCloudConsent(window.localStorage));
    });
    void (async () => {
      const [ark, cloudMatte] = await Promise.all([
        probeEndpoint(ARK_DETECT_PROBE_ENDPOINT, fetchImpl),
        probeEndpoint(CLOUD_MATTE_PROBE_ENDPOINT, fetchImpl),
      ]);
      if (!active) return;
      setAvailability({ ark, cloudMatte });
      setAvailabilityLoaded(true);
      setBackend(resolveDefaultCloudBackend({ ark, cloudMatte }) ?? "ark");
    })();
    return () => {
      active = false;
    };
  }, [fetchImpl]);

  const acknowledgeCloudConsent = useCallback(() => {
    writeNailCloudConsent(window.localStorage);
    setConsentGiven(true);
  }, []);

  return {
    mode,
    setMode,
    backend,
    setBackend,
    availability,
    availabilityLoaded,
    consentGiven,
    acknowledgeCloudConsent,
  };
}
