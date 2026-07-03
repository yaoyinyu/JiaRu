export function inferSuggestedFingers(candidateCount: number): Array<number | null> {
  if (candidateCount <= 0) return [];
  if (candidateCount <= 3) {
    return Array.from({ length: candidateCount }, () => null);
  }
  if (candidateCount === 4) return [1, 2, 3, 4];
  return [0, 1, 2, 3, 4, ...Array.from({ length: Math.max(0, candidateCount - 5) }, () => null)];
}
