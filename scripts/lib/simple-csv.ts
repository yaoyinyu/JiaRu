export function parseCsvLine(line: string): string[] {
  const values: string[] = [];
  let current = "";
  let quoted = false;
  for (let index = 0; index < line.length; index += 1) {
    const char = line[index]!;
    if (char === '"') {
      if (quoted && line[index + 1] === '"') {
        current += '"';
        index += 1;
      } else quoted = !quoted;
    } else if (char === "," && !quoted) {
      values.push(current);
      current = "";
    } else current += char;
  }
  if (quoted) throw new Error("CSV contains an unterminated quoted field");
  values.push(current);
  return values;
}

export function parseCsv(text: string, expectedHeader: string[]): Array<Record<string, string>> {
  const lines = text.replace(/^\uFEFF/, "").split(/\r?\n/).filter((line) => line.trim());
  if (lines.length === 0) throw new Error("CSV is empty");
  const header = parseCsvLine(lines[0]!).map((cell) => cell.trim());
  if (header.length !== expectedHeader.length || header.some((cell, index) => cell !== expectedHeader[index])) {
    throw new Error(`Unexpected CSV header: ${header.join(",")}`);
  }
  return lines.slice(1).map((line, rowIndex) => {
    const cells = parseCsvLine(line);
    if (cells.length !== expectedHeader.length) {
      throw new Error(`CSV row ${rowIndex + 2} has ${cells.length} columns; expected ${expectedHeader.length}`);
    }
    return Object.fromEntries(expectedHeader.map((key, index) => [key, cells[index]!.trim()]));
  });
}
