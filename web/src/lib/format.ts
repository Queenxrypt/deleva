// Display-only formatting. Never mutates or re-derives the underlying value
// -- every function here takes the exact string the backend returned and
// only changes how it is rendered. Full precision always remains available
// via the raw prop/title attribute wherever these are used.

/** Rounds a numeric string for display. Returns "--" for null/unparseable
 * input rather than fabricating a value. */
export function formatNumber(value: string | null | undefined, decimals: number): string {
  if (value === null || value === undefined) return "--";
  const n = Number(value);
  if (Number.isNaN(n)) return "--";
  return n.toFixed(decimals);
}

/** Truncates a hex address/hash for display: 0x0216...f8f7F. The full value
 * remains available via the element's title attribute wherever this is used. */
export function truncateHex(value: string, lead = 6, trail = 4): string {
  if (value.length <= lead + trail + 3) return value;
  return `${value.slice(0, lead)}...${value.slice(-trail)}`;
}
