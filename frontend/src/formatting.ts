export function durationParts(minutes: number): { amount: string; unit: 's' | 'min' } {
  const seconds = minutes !== 0 && Math.abs(minutes) < 1
  return {
    amount: new Intl.NumberFormat('pl-PL', { maximumFractionDigits: 6 }).format(seconds ? minutes * 60 : minutes),
    unit: seconds ? 's' : 'min',
  }
}
export function figureState(margin: number | null): 'success' | 'edge' | 'missed' | 'idle' {
  if (margin === null || !Number.isFinite(margin)) return 'idle'
  return margin >= 2 ? 'success' : margin >= 0 ? 'edge' : 'missed'
}

