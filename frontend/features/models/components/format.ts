// Presentation-only formatting for /models. No scientific derivation:
// fixed-decimal display strings and fixed-scale bar widths against stated
// scale constants. Means, rankings, and shares are never computed here.
export function fmt4(value: number): string {
  return value.toFixed(4);
}

export function fmtFull(value: number): string {
  return String(value);
}

export function abbrHash(hash: string): string {
  return `${hash.slice(0, 12)}…`;
}
