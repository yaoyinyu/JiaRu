import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import type {
  NailTextureCandidate,
  NailTextureCandidateConfidence,
  NailTextureCandidateSource,
  NailTextureModelBackend,
} from "./nail-texture-recognition/types.ts";

export const NAIL_TEXTURE_DATASET_VERSION = "nail-texture-dataset/v1";

export type FingerHint =
  | "thumb"
  | "index"
  | "middle"
  | "ring"
  | "pinky"
  | "unknown";

export type NailShape =
  | "square"
  | "round"
  | "almond"
  | "coffin"
  | "stiletto"
  | "unknown";

export interface Point {
  x: number;
  y: number;
}

export interface NailTexturePolygonAnnotation {
  id: string;
  label: "nail_texture";
  polygon: Point[];
  attributes?: {
    fingerHint?: FingerHint;
    shape?: NailShape;
    quality?: number;
    occluded?: boolean;
    artificialTip?: boolean;
    debug?: {
      candidateId?: string;
      source?: NailTextureCandidateSource;
      confidence?: NailTextureCandidateConfidence;
      warnings?: string[];
      extractionQualityOk?: boolean;
      extractionQualityWarnings?: string[];
      highlightPixels?: number;
      repairedPixels?: number;
      highlightRatio?: number;
    };
  };
}

export interface NailTextureAnnotationDocument {
  version: typeof NAIL_TEXTURE_DATASET_VERSION;
  image: {
    id: string;
    fileName: string;
    width: number;
    height: number;
    sourceGroup?: string;
    negative?: boolean;
    debug?: {
      detectionBackend?: "model" | "fallback";
      modelVersion?: string;
      modelBackend?: NailTextureModelBackend;
      elapsedMs?: number;
      workerElapsedMs?: number;
      warnings?: string[];
    };
  };
  annotations: NailTexturePolygonAnnotation[];
}

export interface BuildInitialAnnotationOptions {
  sourceGroup?: string;
  negative?: boolean;
}

export interface AuditIssue {
  code:
    | "invalid_version"
    | "invalid_image_size"
    | "invalid_file_name"
    | "missing_annotations"
    | "empty_negative_sample"
    | "non_empty_negative_sample"
    | "invalid_label"
    | "duplicate_annotation_id"
    | "polygon_too_short"
    | "polygon_out_of_bounds"
    | "polygon_zero_area"
    | "invalid_quality";
  severity: "error" | "warning";
  message: string;
  annotationId?: string;
}

export interface AuditResult {
  ok: boolean;
  issues: AuditIssue[];
  polygonCount: number;
}

export interface DatasetSplit {
  train: string[];
  val: string[];
  test: string[];
}

export interface SourceRecord {
  imageId: string;
  fileName: string;
  sourceGroup: string;
  originType: "reference" | "web" | "user" | "merchant" | "negative" | "other";
  originRef: string;
  license: string;
  notes: string;
  negative: boolean;
  annotationPath: string;
  imagePath: string;
  annotationCount: number;
  createdAt: string;
  updatedAt: string;
}

export interface SourceAuditIssue {
  code:
    | "missing_image_id"
    | "invalid_file_name"
    | "missing_source_group"
    | "invalid_origin_type"
    | "missing_origin_ref"
    | "missing_license"
    | "invalid_annotation_path"
    | "invalid_image_path"
    | "invalid_annotation_count"
    | "negative_origin_mismatch"
    | "invalid_timestamp";
  severity: "error" | "warning";
  message: string;
  imageId?: string;
  fileName?: string;
}

export interface SourceAuditResult {
  ok: boolean;
  issues: SourceAuditIssue[];
}

export interface NailTextureIntakeBatchItem {
  fileName: string;
  originRef?: string;
  notes?: string;
}

export interface NailTextureIntakeBatchManifest {
  version: "nail-texture-intake-batch/v1";
  sourceGroup: string;
  originType: SourceRecord["originType"];
  license: string;
  defaultOriginRef: string;
  copyImagesToDataset: boolean;
  items: NailTextureIntakeBatchItem[];
}

export interface IntakeBatchValidationIssue {
  code:
    | "invalid_version"
    | "missing_source_group"
    | "invalid_origin_type"
    | "missing_license"
    | "missing_default_origin_ref"
    | "empty_items"
    | "missing_file_name"
    | "duplicate_file_name";
  severity: "error" | "warning";
  message: string;
  fileName?: string;
}

export interface IntakeBatchValidationResult {
  ok: boolean;
  issues: IntakeBatchValidationIssue[];
}

const FINGER_HINTS: FingerHint[] = [
  "thumb",
  "index",
  "middle",
  "ring",
  "pinky",
];

export async function readAnnotationDocument(
  filePath: string
): Promise<NailTextureAnnotationDocument> {
  return JSON.parse(await readFile(filePath, "utf8")) as NailTextureAnnotationDocument;
}

function escapeCsvCell(value: string | number | boolean): string {
  const text = String(value);
  return /[,"\n]/.test(text) ? `"${text.replaceAll("\"", "\"\"")}"` : text;
}

function parseCsvLine(line: string): string[] {
  const values: string[] = [];
  let current = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const char = line[i];
    if (char === "\"") {
      if (inQuotes && line[i + 1] === "\"") {
        current += "\"";
        i++;
      } else {
        inQuotes = !inQuotes;
      }
      continue;
    }
    if (char === "," && !inQuotes) {
      values.push(current);
      current = "";
      continue;
    }
    current += char;
  }
  values.push(current);
  return values;
}

export const SOURCE_CSV_HEADERS = [
  "imageId",
  "fileName",
  "sourceGroup",
  "originType",
  "originRef",
  "license",
  "notes",
  "negative",
  "annotationPath",
  "imagePath",
  "annotationCount",
  "createdAt",
  "updatedAt",
] as const;

const SOURCE_ORIGIN_TYPES: SourceRecord["originType"][] = [
  "reference",
  "web",
  "user",
  "merchant",
  "negative",
  "other",
];

export function stringifySourceRecords(records: SourceRecord[]): string {
  const lines = [
    SOURCE_CSV_HEADERS.join(","),
    ...records.map((record) =>
      [
        record.imageId,
        record.fileName,
        record.sourceGroup,
        record.originType,
        record.originRef,
        record.license,
        record.notes,
        record.negative,
        record.annotationPath,
        record.imagePath,
        record.annotationCount,
        record.createdAt,
        record.updatedAt,
      ]
        .map(escapeCsvCell)
        .join(",")
    ),
  ];
  return `${lines.join("\n")}\n`;
}

export function parseSourceRecords(csvText: string): SourceRecord[] {
  const trimmed = csvText.trim();
  if (!trimmed) return [];
  const lines = trimmed.split(/\r?\n/);
  if (lines.length === 0) return [];
  const header = parseCsvLine(lines[0]);
  const expectedHeader = [...SOURCE_CSV_HEADERS];
  if (header.join(",") !== expectedHeader.join(",")) {
    throw new Error(
      `Unexpected sources.csv header: ${header.join(",")}`
    );
  }

  return lines.slice(1).filter(Boolean).map((line) => {
    const cells = parseCsvLine(line);
    const record = Object.fromEntries(
      expectedHeader.map((key, index) => [key, cells[index] ?? ""])
    ) as Record<(typeof SOURCE_CSV_HEADERS)[number], string>;
    return {
      imageId: record.imageId,
      fileName: record.fileName,
      sourceGroup: record.sourceGroup,
      originType: record.originType as SourceRecord["originType"],
      originRef: record.originRef,
      license: record.license,
      notes: record.notes,
      negative: record.negative === "true",
      annotationPath: record.annotationPath,
      imagePath: record.imagePath,
      annotationCount: Number(record.annotationCount || "0"),
      createdAt: record.createdAt,
      updatedAt: record.updatedAt,
    };
  });
}

export function upsertSourceRecord(
  records: SourceRecord[],
  incoming: SourceRecord
): SourceRecord[] {
  const next = [...records];
  const index = next.findIndex(
    (record) => record.imageId === incoming.imageId || record.fileName === incoming.fileName
  );
  if (index >= 0) {
    next[index] = {
      ...next[index],
      ...incoming,
      createdAt: next[index].createdAt || incoming.createdAt,
      updatedAt: incoming.updatedAt,
    };
  } else {
    next.push(incoming);
  }
  return next.sort((a, b) => a.fileName.localeCompare(b.fileName));
}

function isIsoTimestamp(value: string): boolean {
  if (!value) return false;
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp);
}

export function auditSourceRecord(record: SourceRecord): SourceAuditIssue[] {
  const issues: SourceAuditIssue[] = [];

  if (!record.imageId.trim()) {
    issues.push({
      code: "missing_image_id",
      severity: "error",
      message: "imageId is required",
      imageId: record.imageId,
      fileName: record.fileName,
    });
  }

  if (!record.fileName || /[\\/]/.test(record.fileName)) {
    issues.push({
      code: "invalid_file_name",
      severity: "error",
      message: "fileName must be a base file name without directory separators",
      imageId: record.imageId,
      fileName: record.fileName,
    });
  }

  if (!record.sourceGroup.trim()) {
    issues.push({
      code: "missing_source_group",
      severity: "error",
      message: "sourceGroup is required",
      imageId: record.imageId,
      fileName: record.fileName,
    });
  }

  if (!SOURCE_ORIGIN_TYPES.includes(record.originType)) {
    issues.push({
      code: "invalid_origin_type",
      severity: "error",
      message: `originType must be one of: ${SOURCE_ORIGIN_TYPES.join(", ")}`,
      imageId: record.imageId,
      fileName: record.fileName,
    });
  }

  if (!record.originRef.trim()) {
    issues.push({
      code: "missing_origin_ref",
      severity: "warning",
      message: "originRef should record the source URL, album, batch name, or user authorization note",
      imageId: record.imageId,
      fileName: record.fileName,
    });
  }

  if (!record.license.trim()) {
    issues.push({
      code: "missing_license",
      severity: "warning",
      message: "license should describe the image usage permission or internal authorization status",
      imageId: record.imageId,
      fileName: record.fileName,
    });
  }

  if (!/^annotations\/raw-json\/[^/]+\.json$/i.test(record.annotationPath)) {
    issues.push({
      code: "invalid_annotation_path",
      severity: "error",
      message: "annotationPath must look like annotations/raw-json/<file>.json",
      imageId: record.imageId,
      fileName: record.fileName,
    });
  }

  if (!/^images\/raw\/[^/]+\.(png|jpg|jpeg|webp)$/i.test(record.imagePath)) {
    issues.push({
      code: "invalid_image_path",
      severity: "error",
      message: "imagePath must look like images/raw/<file>.(png|jpg|jpeg|webp)",
      imageId: record.imageId,
      fileName: record.fileName,
    });
  }

  if (!Number.isInteger(record.annotationCount) || record.annotationCount < 0) {
    issues.push({
      code: "invalid_annotation_count",
      severity: "error",
      message: "annotationCount must be a non-negative integer",
      imageId: record.imageId,
      fileName: record.fileName,
    });
  }

  if (record.negative && record.originType !== "negative") {
    issues.push({
      code: "negative_origin_mismatch",
      severity: "warning",
      message: "negative samples are recommended to use originType=negative for easier filtering",
      imageId: record.imageId,
      fileName: record.fileName,
    });
  }

  if (!isIsoTimestamp(record.createdAt) || !isIsoTimestamp(record.updatedAt)) {
    issues.push({
      code: "invalid_timestamp",
      severity: "error",
      message: "createdAt and updatedAt must be valid ISO timestamps",
      imageId: record.imageId,
      fileName: record.fileName,
    });
  }

  return issues;
}

export function auditSourceRecords(records: SourceRecord[]): SourceAuditResult {
  const issues = records.flatMap((record) => auditSourceRecord(record));
  return {
    ok: issues.every((issue) => issue.severity !== "error"),
    issues,
  };
}

export function validateIntakeBatchManifest(
  manifest: NailTextureIntakeBatchManifest
): IntakeBatchValidationResult {
  const issues: IntakeBatchValidationIssue[] = [];

  if (manifest.version !== "nail-texture-intake-batch/v1") {
    issues.push({
      code: "invalid_version",
      severity: "error",
      message: "version must be nail-texture-intake-batch/v1",
    });
  }
  if (!manifest.sourceGroup?.trim()) {
    issues.push({
      code: "missing_source_group",
      severity: "error",
      message: "sourceGroup is required",
    });
  }
  if (!SOURCE_ORIGIN_TYPES.includes(manifest.originType)) {
    issues.push({
      code: "invalid_origin_type",
      severity: "error",
      message: `originType must be one of: ${SOURCE_ORIGIN_TYPES.join(", ")}`,
    });
  }
  if (!manifest.license?.trim()) {
    issues.push({
      code: "missing_license",
      severity: "warning",
      message: "license should not be empty for a batch intake manifest",
    });
  }
  if (!manifest.defaultOriginRef?.trim()) {
    issues.push({
      code: "missing_default_origin_ref",
      severity: "warning",
      message:
        "defaultOriginRef should describe the album, merchant set, URL list, or authorization note",
    });
  }
  if (!Array.isArray(manifest.items) || manifest.items.length === 0) {
    issues.push({
      code: "empty_items",
      severity: "error",
      message: "items must contain at least one image entry",
    });
  }

  const seen = new Set<string>();
  for (const item of manifest.items ?? []) {
    if (!item.fileName?.trim()) {
      issues.push({
        code: "missing_file_name",
        severity: "error",
        message: "each item must include fileName",
      });
      continue;
    }
    if (seen.has(item.fileName)) {
      issues.push({
        code: "duplicate_file_name",
        severity: "error",
        message: `duplicate fileName in manifest: ${item.fileName}`,
        fileName: item.fileName,
      });
    }
    seen.add(item.fileName);
  }

  return {
    ok: issues.every((issue) => issue.severity !== "error"),
    issues,
  };
}

export function polygonArea(points: Point[]): number {
  let sum = 0;
  for (let i = 0; i < points.length; i++) {
    const current = points[i];
    const next = points[(i + 1) % points.length];
    sum += current.x * next.y - next.x * current.y;
  }
  return Math.abs(sum) * 0.5;
}

export function normalizePolygonToYolo(
  points: Point[],
  width: number,
  height: number
): number[] {
  return points.flatMap((point) => [point.x / width, point.y / height]);
}

export function toYoloSegmentationLines(
  document: NailTextureAnnotationDocument
): string[] {
  return document.annotations.map((annotation) => {
    const normalized = normalizePolygonToYolo(
      annotation.polygon,
      document.image.width,
      document.image.height
    );
    return ["0", ...normalized.map((value) => value.toFixed(6))].join(" ");
  });
}

export function rotatePoint(
  point: Point,
  angle: number
): Point {
  const c = Math.cos(angle);
  const s = Math.sin(angle);
  return {
    x: point.x * c - point.y * s,
    y: point.x * s + point.y * c,
  };
}

export function createInitialPolygonFromCandidate(
  candidate: Pick<NailTextureCandidate, "cx" | "cy" | "length" | "width" | "angle">
): Point[] {
  const halfWidth = candidate.width * 0.5;
  const halfLength = candidate.length * 0.5;
  const localPoints: Point[] = [
    { x: -halfWidth * 0.45, y: -halfLength },
    { x: halfWidth * 0.45, y: -halfLength },
    { x: halfWidth * 0.9, y: -halfLength * 0.45 },
    { x: halfWidth, y: halfLength * 0.7 },
    { x: 0, y: halfLength },
    { x: -halfWidth, y: halfLength * 0.7 },
    { x: -halfWidth * 0.9, y: -halfLength * 0.45 },
  ];

  return localPoints.map((point) => {
    const rotated = rotatePoint(point, candidate.angle);
    return {
      x: candidate.cx + rotated.x,
      y: candidate.cy + rotated.y,
    };
  });
}

function clampPoint(point: Point, width: number, height: number): Point {
  return {
    x: Math.max(0, Math.min(width, point.x)),
    y: Math.max(0, Math.min(height, point.y)),
  };
}

export function candidateToInitialAnnotation(
  candidate: NailTextureCandidate,
  width: number,
  height: number,
  index: number
): NailTexturePolygonAnnotation {
  const fingerHint =
    candidate.suggestedFinger == null
      ? "unknown"
      : FINGER_HINTS[candidate.suggestedFinger] ?? "unknown";
  const quality = candidate.confidence === "high" ? 4 : candidate.confidence === "medium" ? 3 : 2;

  return {
    id: `n${index + 1}`,
    label: "nail_texture",
    polygon: createInitialPolygonFromCandidate(candidate).map((point) =>
      clampPoint(point, width, height)
    ),
    attributes: {
      fingerHint,
      shape: "unknown",
      quality,
      occluded: false,
      artificialTip: true,
    },
  };
}

export function buildInitialAnnotationDocument(
  image: {
    id: string;
    fileName: string;
    width: number;
    height: number;
  },
  candidates: NailTextureCandidate[],
  options: BuildInitialAnnotationOptions = {}
): NailTextureAnnotationDocument {
  const negative = options.negative ?? candidates.length === 0;
  return {
    version: NAIL_TEXTURE_DATASET_VERSION,
    image: {
      ...image,
      sourceGroup: options.sourceGroup,
      negative,
    },
    annotations: negative
      ? []
      : candidates.map((candidate, index) =>
          candidateToInitialAnnotation(candidate, image.width, image.height, index)
        ),
  };
}

export function auditAnnotationDocument(
  document: NailTextureAnnotationDocument
): AuditResult {
  const issues: AuditIssue[] = [];
  if (document.version !== NAIL_TEXTURE_DATASET_VERSION) {
    issues.push({
      code: "invalid_version",
      severity: "error",
      message: `Expected version ${NAIL_TEXTURE_DATASET_VERSION}, received ${document.version}`,
    });
  }

  const { fileName, width, height, negative } = document.image;
  if (!fileName || /[\\/]/.test(fileName)) {
    issues.push({
      code: "invalid_file_name",
      severity: "error",
      message: "image.fileName must be a base file name without directory separators",
    });
  }
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
    issues.push({
      code: "invalid_image_size",
      severity: "error",
      message: "image.width and image.height must be positive numbers",
    });
  }

  if (!negative && document.annotations.length === 0) {
    issues.push({
      code: "missing_annotations",
      severity: "error",
      message: "non-negative samples must contain at least one annotation",
    });
  }
  if (negative && document.annotations.length === 0) {
    issues.push({
      code: "empty_negative_sample",
      severity: "warning",
      message: "negative sample contains no nail polygons, which is allowed",
    });
  }
  if (negative && document.annotations.length > 0) {
    issues.push({
      code: "non_empty_negative_sample",
      severity: "error",
      message: "negative sample cannot contain nail polygons",
    });
  }

  const seenIds = new Set<string>();
  for (const annotation of document.annotations) {
    if (annotation.label !== "nail_texture") {
      issues.push({
        code: "invalid_label",
        severity: "error",
        message: `Unsupported label ${annotation.label}`,
        annotationId: annotation.id,
      });
    }
    if (seenIds.has(annotation.id)) {
      issues.push({
        code: "duplicate_annotation_id",
        severity: "error",
        message: `Duplicate annotation id ${annotation.id}`,
        annotationId: annotation.id,
      });
    }
    seenIds.add(annotation.id);

    if (annotation.polygon.length < 3) {
      issues.push({
        code: "polygon_too_short",
        severity: "error",
        message: "polygon must contain at least 3 points",
        annotationId: annotation.id,
      });
      continue;
    }

    let outOfBounds = false;
    for (const point of annotation.polygon) {
      if (
        !Number.isFinite(point.x) ||
        !Number.isFinite(point.y) ||
        point.x < 0 ||
        point.y < 0 ||
        point.x > width ||
        point.y > height
      ) {
        outOfBounds = true;
        break;
      }
    }
    if (outOfBounds) {
      issues.push({
        code: "polygon_out_of_bounds",
        severity: "error",
        message: "polygon contains points outside image bounds",
        annotationId: annotation.id,
      });
    }

    if (polygonArea(annotation.polygon) <= 1) {
      issues.push({
        code: "polygon_zero_area",
        severity: "error",
        message: "polygon area must be greater than 1 pixel",
        annotationId: annotation.id,
      });
    }

    const quality = annotation.attributes?.quality;
    if (
      quality != null &&
      (!Number.isInteger(quality) || quality < 1 || quality > 5)
    ) {
      issues.push({
        code: "invalid_quality",
        severity: "error",
        message: "quality must be an integer between 1 and 5",
        annotationId: annotation.id,
      });
    }
  }

  const ok = issues.every((issue) => issue.severity !== "error");
  return { ok, issues, polygonCount: document.annotations.length };
}

function stableBucket(seed: string): number {
  const hash = createHash("sha1").update(seed).digest();
  return hash.readUInt32BE(0) % 100;
}

function pushProportionalSplit(files: string[], split: DatasetSplit): void {
  const sorted = [...files].sort((a, b) => a.localeCompare(b));
  const total = sorted.length;
  const trainEnd = Math.max(1, Math.floor(total * 0.7));
  const valEnd = Math.max(trainEnd, Math.floor(total * 0.85));

  for (let index = 0; index < sorted.length; index++) {
    const fileName = sorted[index]!;
    if (index < trainEnd) split.train.push(fileName);
    else if (index < valEnd) split.val.push(fileName);
    else split.test.push(fileName);
  }
}

export function buildDatasetSplit(
  documents: NailTextureAnnotationDocument[]
): DatasetSplit {
  const groups = new Map<string, string[]>();
  for (const document of documents) {
    const groupKey =
      document.image.sourceGroup?.trim() ||
      document.image.id.trim() ||
      document.image.fileName.trim();
    const current = groups.get(groupKey) ?? [];
    current.push(document.image.fileName);
    groups.set(groupKey, current);
  }

  const split: DatasetSplit = { train: [], val: [], test: [] };
  if (groups.size <= 1) {
    pushProportionalSplit(
      documents.map((document) => document.image.fileName),
      split
    );
  } else {
    for (const [groupKey, files] of groups) {
      const bucket = stableBucket(groupKey);
      const target =
        bucket < 70 ? split.train : bucket < 85 ? split.val : split.test;
      target.push(...files.sort());
    }
  }

  split.train.sort();
  split.val.sort();
  split.test.sort();
  return split;
}
