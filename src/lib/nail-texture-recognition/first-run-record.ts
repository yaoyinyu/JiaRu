export interface RealModelFirstRunRecord {
  version: "nail-real-model-first-run/v1";
  createdAt: string;
  model: {
    manifestPath: string;
    modelPath: string;
    version: string;
    backendPreferences: string[];
    artifactOk: boolean;
  };
  input: {
    imagePath: string;
    annotationPath: string | null;
    debugOutputDir: string;
    debugPrefix: string;
  };
  readiness: {
    ok: boolean;
    fixtureVerified: boolean | null;
    imageVerified: boolean | null;
    warnings: string[];
  };
  outputs: {
    debugJsonPath: string | null;
    debugOverlayPath: string | null;
    candidateMaskPath: string | null;
    skinMaskPath: string | null;
    modelOutputDumpPath: string | null;
    fixturePath: string | null;
  };
  observations: {
    backend: "model" | "fallback" | "unknown";
    candidateCount: number | null;
    maxCenterError: number | null;
    outputNames: string[];
    outputDims: number[][];
    newWarnings: string[];
    notes: string;
  };
  decision: {
    status: "pass" | "needs_adjustment" | "blocked";
    summary: string;
    nextActions: string[];
  };
}

export interface FirstRunRecordValidationResult {
  ok: boolean;
  errors: string[];
}

export interface RealModelUiReviewRecord {
  version: "nail-real-model-ui-review/v1";
  createdAt: string;
  pagePath: string;
  checks: {
    pickerOpened: boolean;
    modelOrFallbackBadgeVisible: boolean;
    pageResponsive: boolean;
    fallbackRecovered: boolean;
  };
  notes: string;
  decision: {
    status: "pass" | "needs_adjustment" | "blocked";
    summary: string;
  };
}

export interface UiReviewValidationResult {
  ok: boolean;
  errors: string[];
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function isNumberMatrix(value: unknown): value is number[][] {
  return (
    Array.isArray(value) &&
    value.every(
      (row) => Array.isArray(row) && row.every((cell) => typeof cell === "number")
    )
  );
}

export function validateRealModelFirstRunRecord(
  value: unknown
): FirstRunRecordValidationResult {
  const errors: string[] = [];
  const record = value as Partial<RealModelFirstRunRecord> | null;

  if (!record || typeof record !== "object") {
    return { ok: false, errors: ["record must be an object"] };
  }

  if (record.version !== "nail-real-model-first-run/v1") {
    errors.push("version must be nail-real-model-first-run/v1");
  }
  if (typeof record.createdAt !== "string" || record.createdAt.length === 0) {
    errors.push("createdAt must be a non-empty string");
  }

  if (!record.model || typeof record.model !== "object") {
    errors.push("model block is required");
  } else {
    if (typeof record.model.manifestPath !== "string" || !record.model.manifestPath) {
      errors.push("model.manifestPath is required");
    }
    if (typeof record.model.modelPath !== "string" || !record.model.modelPath) {
      errors.push("model.modelPath is required");
    }
    if (typeof record.model.version !== "string" || !record.model.version) {
      errors.push("model.version is required");
    }
    if (!isStringArray(record.model.backendPreferences)) {
      errors.push("model.backendPreferences must be a string array");
    }
    if (typeof record.model.artifactOk !== "boolean") {
      errors.push("model.artifactOk must be boolean");
    }
  }

  if (!record.input || typeof record.input !== "object") {
    errors.push("input block is required");
  } else {
    if (typeof record.input.imagePath !== "string" || !record.input.imagePath) {
      errors.push("input.imagePath is required");
    }
    if (
      record.input.annotationPath !== null &&
      typeof record.input.annotationPath !== "string"
    ) {
      errors.push("input.annotationPath must be string or null");
    }
    if (typeof record.input.debugOutputDir !== "string" || !record.input.debugOutputDir) {
      errors.push("input.debugOutputDir is required");
    }
    if (typeof record.input.debugPrefix !== "string" || !record.input.debugPrefix) {
      errors.push("input.debugPrefix is required");
    }
  }

  if (!record.readiness || typeof record.readiness !== "object") {
    errors.push("readiness block is required");
  } else {
    if (typeof record.readiness.ok !== "boolean") {
      errors.push("readiness.ok must be boolean");
    }
    for (const key of ["fixtureVerified", "imageVerified"] as const) {
      const value = record.readiness[key];
      if (value !== null && typeof value !== "boolean") {
        errors.push(`readiness.${key} must be boolean or null`);
      }
    }
    if (!isStringArray(record.readiness.warnings)) {
      errors.push("readiness.warnings must be a string array");
    }
  }

  if (!record.outputs || typeof record.outputs !== "object") {
    errors.push("outputs block is required");
  } else {
    for (const key of [
      "debugJsonPath",
      "debugOverlayPath",
      "candidateMaskPath",
      "skinMaskPath",
      "modelOutputDumpPath",
      "fixturePath",
    ] as const) {
      const value = record.outputs[key];
      if (value !== null && typeof value !== "string") {
        errors.push(`outputs.${key} must be string or null`);
      }
    }
  }

  if (!record.observations || typeof record.observations !== "object") {
    errors.push("observations block is required");
  } else {
    if (!["model", "fallback", "unknown"].includes(record.observations.backend ?? "")) {
      errors.push("observations.backend must be model, fallback, or unknown");
    }
    for (const key of ["candidateCount", "maxCenterError"] as const) {
      const value = record.observations[key];
      if (value !== null && typeof value !== "number") {
        errors.push(`observations.${key} must be number or null`);
      }
    }
    if (!isStringArray(record.observations.outputNames)) {
      errors.push("observations.outputNames must be a string array");
    }
    if (!isNumberMatrix(record.observations.outputDims)) {
      errors.push("observations.outputDims must be a number matrix");
    }
    if (!isStringArray(record.observations.newWarnings)) {
      errors.push("observations.newWarnings must be a string array");
    }
    if (typeof record.observations.notes !== "string") {
      errors.push("observations.notes must be a string");
    }
  }

  if (!record.decision || typeof record.decision !== "object") {
    errors.push("decision block is required");
  } else {
    if (!["pass", "needs_adjustment", "blocked"].includes(record.decision.status ?? "")) {
      errors.push("decision.status must be pass, needs_adjustment, or blocked");
    }
    if (typeof record.decision.summary !== "string") {
      errors.push("decision.summary must be a string");
    }
    if (!isStringArray(record.decision.nextActions)) {
      errors.push("decision.nextActions must be a string array");
    }
  }

  return {
    ok: errors.length === 0,
    errors,
  };
}

export function validateRealModelUiReviewRecord(
  value: unknown
): UiReviewValidationResult {
  const errors: string[] = [];
  const record = value as Partial<RealModelUiReviewRecord> | null;

  if (!record || typeof record !== "object") {
    return { ok: false, errors: ["record must be an object"] };
  }
  if (record.version !== "nail-real-model-ui-review/v1") {
    errors.push("version must be nail-real-model-ui-review/v1");
  }
  if (typeof record.createdAt !== "string" || !record.createdAt) {
    errors.push("createdAt must be a non-empty string");
  }
  if (typeof record.pagePath !== "string" || !record.pagePath) {
    errors.push("pagePath must be a non-empty string");
  }
  if (!record.checks || typeof record.checks !== "object") {
    errors.push("checks block is required");
  } else {
    for (const key of [
      "pickerOpened",
      "modelOrFallbackBadgeVisible",
      "pageResponsive",
      "fallbackRecovered",
    ] as const) {
      if (typeof record.checks[key] !== "boolean") {
        errors.push(`checks.${key} must be boolean`);
      }
    }
  }
  if (typeof record.notes !== "string") {
    errors.push("notes must be a string");
  }
  if (!record.decision || typeof record.decision !== "object") {
    errors.push("decision block is required");
  } else {
    if (!["pass", "needs_adjustment", "blocked"].includes(record.decision.status ?? "")) {
      errors.push("decision.status must be pass, needs_adjustment, or blocked");
    }
    if (typeof record.decision.summary !== "string") {
      errors.push("decision.summary must be a string");
    }
  }

  return {
    ok: errors.length === 0,
    errors,
  };
}
