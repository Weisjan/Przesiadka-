export interface LocalDateTime {
  date: string
  time: string
  offset: string
}

const partsFormat = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Europe/Warsaw', year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
})

function localParts(date: Date) {
  const parts = Object.fromEntries(partsFormat.formatToParts(date).map(part => [part.type, part.value]))
  return { date: `${parts.year}-${parts.month}-${parts.day}`, time: `${parts.hour}:${parts.minute}`, seconds: parts.second }
}

export function fromIso(iso: string): LocalDateTime {
  const parts = localParts(new Date(iso))
  return { date: parts.date, time: parts.time, offset: iso.slice(-6) }
}

export function dateTimeOptions(value: LocalDateTime): string[] {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value.date) || !/^\d{2}:\d{2}$/.test(value.time)) return []
  const wall = `${value.date}T${value.time}:00`
  const timestamp = Date.parse(`${wall}Z`)
  if (!Number.isFinite(timestamp)) return []
  // Sampling both sides of a transition discovers offsets without using the device's zone.
  const offsets = new Set<number>()
  for (const hours of [-36, 0, 36]) {
    const instant = new Date(timestamp + hours * 3600000)
    const parts = localParts(instant)
    offsets.add((Date.parse(`${parts.date}T${parts.time}:${parts.seconds}Z`) - instant.getTime()) / 60000)
  }
  return [...offsets].sort((a, b) => b - a).flatMap(minutes => {
    if (!Number.isInteger(minutes)) return []
    const candidate = new Date(timestamp - minutes * 60000)
    const parts = localParts(candidate)
    if (parts.date !== value.date || parts.time !== value.time) return []
    const absolute = Math.abs(minutes)
    const offset = `${minutes >= 0 ? '+' : '-'}${String(Math.floor(absolute / 60)).padStart(2, '0')}:${String(absolute % 60).padStart(2, '0')}`
    return [`${wall}${offset}`]
  })
}

export const clock = (iso: string) => new Intl.DateTimeFormat('pl-PL', {
  timeZone: 'Europe/Warsaw', hour: '2-digit', minute: '2-digit',
}).format(new Date(iso))

export const fullDate = (iso: string) => new Intl.DateTimeFormat('pl-PL', {
  timeZone: 'Europe/Warsaw', day: 'numeric', month: 'long', year: 'numeric',
  hour: '2-digit', minute: '2-digit', timeZoneName: 'shortOffset',
}).format(new Date(iso))

export const calendarDate = (iso: string) => new Intl.DateTimeFormat('pl-PL', {
  timeZone: 'Europe/Warsaw', day: 'numeric', month: 'long', year: 'numeric',
}).format(new Date(iso))

export function timeHints(iso: string, reference: string, context: string[]): string[] {
  const local = fromIso(iso)
  const first = fromIso(reference)
  const days = Math.round((Date.parse(`${local.date}T00:00:00Z`) - Date.parse(`${first.date}T00:00:00Z`)) / 86400000)
  const day = days === 0 ? '' : days === 1 ? 'następnego dnia' : days === -1 ? 'poprzedniego dnia' : calendarDate(iso)
  const offsetNeeded = dateTimeOptions(local).length > 1 || context.some(date => {
    const other = fromIso(date)
    return other.date === local.date && other.offset !== local.offset
  })
  return [day, offsetNeeded ? `UTC${local.offset}` : ''].filter(Boolean)
}

export function eventClock(iso: string, context: string[]): string {
  const local = fromIso(iso)
  const fraction = (date: string) => (date.match(/\.(\d+)/)?.[1] ?? '').padEnd(6, '0')
  const close = context.some(date => {
    const other = fromIso(date)
    return other.date === local.date && other.time === local.time && other.offset === local.offset
      && (Date.parse(date) !== Date.parse(iso) || fraction(date) !== fraction(iso))
  })
  if (!close) return clock(iso)
  const seconds = String(new Date(iso).getUTCSeconds()).padStart(2, '0')
  const decimal = fraction(iso).replace(/0+$/, '')
  return `${clock(iso)}:${seconds}${decimal ? `,${decimal}` : ''}`
}
