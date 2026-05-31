export function fmt(value, digits) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return "-";
  const abs = Math.abs(parsed);
  if (abs !== 0 && abs < 0.001) return parsed.toExponential(3);
  return parsed.toFixed(digits);
}
