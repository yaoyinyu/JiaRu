/** 当前发布要求不能通过删除文档行或降为历史来绕过。 */
export const CURRENT_RELEASE_REQUIREMENTS = [
  "REL-CURRENT-AUDIT-V3-001", "REL-CURRENT-DEVELOPMENT-002",
  "REL-CURRENT-CALIBRATION-003", "REL-CURRENT-POSITIVE-HOLDOUT-004",
  "REL-CURRENT-NEGATIVE-HOLDOUT-005", "REL-CURRENT-RUNTIME-006",
  "REL-CURRENT-PRODUCT-007",
] as const;

export interface ProgressMarker { id: string; task: string; status: string; evidence: string }

export function auditReleaseProgress(markers: ProgressMarker[]) {
  const errors: string[] = [];
  const seen = new Set<string>();
  const records = markers.map((marker) => {
    if (seen.has(marker.id)) errors.push(`duplicate marker: ${marker.id}`);
    seen.add(marker.id);
    const fields: Record<string, string> = {};
    for (const match of marker.evidence.matchAll(/\b(lifecycle|outcome|gateRole|required)=([^;`\s]+)/g)) {
      if (fields[match[1]!]) errors.push(`${marker.id}: duplicate ${match[1]}`);
      fields[match[1]!] = match[2]!;
    }
    const requiredId = (CURRENT_RELEASE_REQUIREMENTS as readonly string[]).includes(marker.id);
    const structured = Object.keys(fields).length > 0;
    if (structured || requiredId || marker.id.startsWith("REL-CURRENT-")) {
      for (const [key, values] of Object.entries({
        lifecycle: ["planned", "running", "closed"],
        outcome: ["pending", "pass", "rejected", "hold", "not-applicable"],
        gateRole: ["current-release", "historical", "superseded"],
        required: ["true", "false"],
      })) if (!values.includes(fields[key]!)) errors.push(`${marker.id}: invalid ${key}`);
      if (requiredId && (fields.gateRole !== "current-release" || fields.required !== "true"))
        errors.push(`${marker.id}: required release requirement cannot be demoted`);
      if (fields.gateRole === "current-release" && fields.required !== "true")
        errors.push(`${marker.id}: current release requirement must be required`);
      if (fields.outcome === "pass" && (fields.lifecycle !== "closed" ||
          !/^(?:✅\s*)?PASS(?:\s|（|\(|$)/i.test(marker.status) ||
          /FAIL|REJECT|HOLD|否决|拒绝/i.test(marker.status)))
        errors.push(`${marker.id}: contradictory passing outcome`);
    }
    return { ...marker, lifecycle: fields.lifecycle ?? "legacy-recorded",
      outcome: fields.outcome ?? "legacy-unclassified", gateRole: fields.gateRole ?? "historical",
      required: fields.required === "true" };
  });
  for (const id of CURRENT_RELEASE_REQUIREMENTS) if (!seen.has(id)) errors.push(`missing requirement: ${id}`);
  const current = records.filter((row) => row.gateRole === "current-release" && row.required);
  const incompleteMarkers = current.filter((row) => row.lifecycle !== "closed" || row.outcome !== "pass");
  return { ok: errors.length === 0 && incompleteMarkers.length === 0,
    markerCount: markers.length, currentRequirementCount: current.length,
    passMarkerCount: current.length - incompleteMarkers.length,
    historicalMarkerCount: records.length - current.length,
    incompleteMarkers, records, errors };
}
