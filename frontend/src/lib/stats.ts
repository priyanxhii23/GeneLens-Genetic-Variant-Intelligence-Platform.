/** Wilson score interval (95%) – same method as the backend; returns [estimate, lower, upper]. */
export function wilson(k: number, n: number): [number, number, number] | null {
  if (!n) return null;
  const z = 1.959963984540054, p = k / n, d = 1 + (z * z) / n;
  const c = (p + (z * z) / (2 * n)) / d, h = (z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n))) / d;
  return [p, Math.max(0, c - h), Math.min(1, c + h)];
}

