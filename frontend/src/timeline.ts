import type { Evaluation, ScenarioInput } from './types'

type EventKind = 'arrival' | 'departure' | 'ready' | 'alternative'

export interface TimelineEvent {
  key: string
  date: string
  kinds: EventKind[]
  label: string
  description: string
  symbol: string
}

function instantKey(iso: string): string {
  // Date.parse truncates microseconds; distinct API instants must stay distinct.
  const fraction = (iso.match(/\.(\d+)/)?.[1] ?? '').padEnd(6, '0')
  return `${new Date(iso).toISOString().slice(0, 19)}.${fraction}Z`
}

export function timelineEvents(scenario: ScenarioInput, result: Evaluation | null): TimelineEvent[] {
  const source: { kind: EventKind; date: string; label: string; description: string; symbol: string }[] = [
    { kind: 'arrival', date: scenario.arrival_at, label: 'przyjazd', description: 'Planowany przyjazd', symbol: '●' },
    { kind: 'departure', date: scenario.departure_at, label: 'odjazd', description: 'Planowany odjazd', symbol: '○' },
    ...(result ? [{ kind: 'ready' as const, date: result.expected_stop_arrival_at, label: 'dotarcie', description: 'Oczekiwane dotarcie na przystanek', symbol: '◆' }] : []),
    ...(result?.plan_b_departure_at ? [{ kind: 'alternative' as const, date: result.plan_b_departure_at, label: 'plan B', description: 'Odjazd planu B', symbol: '◈' }] : []),
  ]
  const groups = new Map<string, TimelineEvent>()
  for (const event of source) {
    const key = instantKey(event.date)
    const existing = groups.get(key)
    if (existing) {
      existing.kinds.push(event.kind)
      existing.label = existing.kinds.includes('ready') && existing.kinds.includes('departure')
        ? `${existing.kinds.includes('arrival') ? 'przyjazd, ' : ''}dotarcie i odjazd`
        : `${existing.label} i ${event.label}`
      existing.description += `. ${event.description}`
      existing.symbol = '◉'
    } else {
      groups.set(key, { key, date: event.date, kinds: [event.kind], label: event.kind === 'ready' ? 'dotarcie na przystanek' : event.label, description: event.description, symbol: event.symbol })
    }
  }
  return [...groups.values()].sort((a, b) => a.key.localeCompare(b.key))
}

export function markerLanes(positions: number[], width: number): number[] {
  const ends: number[] = []
  return positions.map(position => {
    const x = position * width / 100
    let lane = ends.findIndex(end => x - end >= 28)
    if (lane === -1) lane = ends.length
    ends[lane] = x
    return lane
  })
}

export function durationParts(minutes: number): { amount: string; unit: 's' | 'min' } {
  const seconds = minutes !== 0 && Math.abs(minutes) < 1
  return {
    amount: new Intl.NumberFormat('pl-PL', { maximumFractionDigits: 6 }).format(seconds ? minutes * 60 : minutes),
    unit: seconds ? 's' : 'min',
  }
}
