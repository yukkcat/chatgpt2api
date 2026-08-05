function compactDurationNumber(value: number, digits: number): string {
  return Number(value.toFixed(digits)).toString()
}

export function formatRequestDuration(value: unknown): string {
  if (value === '' || value === null || value === undefined) return ''
  const parsed = Number(value)
  if (!Number.isFinite(parsed) || parsed < 0) return ''
  if (parsed < 1000) return `${Math.round(parsed)}ms`
  if (parsed < 10000) return `${compactDurationNumber(parsed / 1000, 2)}s`
  if (parsed < 60000) return `${compactDurationNumber(parsed / 1000, 1)}s`
  return `${compactDurationNumber(parsed / 60000, 1)}m`
}
