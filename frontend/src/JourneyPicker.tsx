import { useEffect, useId, useRef, useState } from 'react'
import { request } from './api'
import { eventClock, fromIso, fullDate, timeHints } from './dates'
import { directionKey, journeyKey, lineKey, readJourneys, stopLabel } from './transitData'
import type { Journey, JourneysResponse, Leg, TransitSource, TransitStop } from './transitData'
import styles from './Transit.module.css'

export default function JourneyPicker({ leg, stop, source, selected, reference, linkId, onChoose, onClose }: {
  leg: Leg; stop: TransitStop; source: TransitSource; selected: Journey | null; reference?: string; linkId: string
  onChoose: (journey: Journey) => void; onClose: () => void
}) {
  const [day, setDay] = useState(() => fromIso((leg === 'arrival' ? selected?.arrival_at : selected?.departure_at) ?? reference ?? new Date().toISOString()).date)
  const [line, setLine] = useState(selected ? lineKey(selected) : '')
  const [direction, setDirection] = useState(selected ? directionKey(selected) : '')
  const [course, setCourse] = useState(selected ? journeyKey(selected) : '')
  const [attempt, setAttempt] = useState(0)
  const [response, setResponse] = useState<{ key: string; data?: JourneysResponse; error?: string } | null>(null)
  const dialog = useRef<HTMLDialogElement>(null)
  const id = useId()
  const query = new URLSearchParams({ leg, date: day, link_id: linkId })
  if (leg === 'departure' && reference) query.set('after', reference)
  const queryString = query.toString()
  const key = `${queryString}:${attempt}`
  const current = response?.key === key ? response : null
  const data = current?.data
  const loading = !current
  const journeys = (data?.journeys ?? []).filter(item => item.stop_id === stop.stop_id
    && (leg === 'arrival' ? !!item.arrival_at && item.drop_off_type === 0 : !!item.departure_at && item.pickup_type === 0))
  const lines = [...new Map(journeys.map(item => [lineKey(item), item.line])).entries()]
  const inLine = journeys.filter(item => lineKey(item) === line)
  const directions = [...new Map(inLine.map(item => [directionKey(item), item.direction ?? 'Kierunek niepodany w rozkładzie'])).entries()]
  const choices = inLine.filter(item => directionKey(item) === direction)
  const chosen = choices.find(item => journeyKey(item) === course)
  const times = choices.map(item => (leg === 'arrival' ? item.arrival_at : item.departure_at)!)

  useEffect(() => {
    if (!line && lines.length === 1) setLine(lines[0][0])
    if (!direction && directions.length === 1) setDirection(directions[0][0])
  }, [data, line, direction])

  useEffect(() => {
    const trigger = document.activeElement as HTMLElement | null
    const modal = dialog.current
    modal?.showModal()
    modal?.querySelector<HTMLButtonElement>('button')?.focus()
    return () => { modal?.close(); if (trigger?.isConnected) trigger.focus() }
  }, [])
  useEffect(() => {
    const controller = new AbortController()
    let disposed = false
    request<unknown>(`/api/transit/journeys?${queryString}`, { signal: controller.signal })
      .then(readJourneys)
      .then(data => { if (!disposed) setResponse({ key, data }) })
      .catch((error: Error) => { if (!disposed) setResponse({ key, error: error.message }) })
    return () => { disposed = true; controller.abort() }
  }, [queryString, key])

  return <dialog ref={dialog} className={styles.picker} aria-labelledby={`${id}-title`} onCancel={onClose}
    onKeyDown={event => {
      if (event.key !== 'Tab') return
      const controls = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled)'))
      const first = controls[0], last = controls.at(-1)
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
    }}>
    <div className={styles.pickerHeading}><div><p>{leg === 'arrival' ? 'Linia 1 / przyjazd' : 'Linia 2 / odjazd'}</p>
      <h2 id={`${id}-title`}>Wybierz kurs</h2></div><button onClick={onClose} aria-label="Zamknij wybór kursu">Zamknij</button></div>
    <p className={styles.help}>Rozkład planowany · {stopLabel(stop)}.</p>
    {leg === 'departure' && reference && <p className={styles.help}>Odjazdy w ciągu 6 godzin od planowanego przyjazdu. Dla kursu po północy wybierz następną datę.</p>}
    <div className={styles.pickerGrid}>
      <label>Data {leg === 'arrival' ? 'przyjazdu' : 'odjazdu'}<input type="date" required value={day}
        min={source.service_start_date} max={source.service_end_date}
        onChange={event => { setDay(event.target.value); setLine(''); setDirection(''); setCourse('') }} /></label>
      <label>Linia / trasa<select value={line} disabled={loading || !journeys.length} onChange={event => { setLine(event.target.value); setDirection(''); setCourse('') }}>
        <option value="">Wybierz linię</option>{lines.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select></label>
      <label>Kierunek<select value={direction} disabled={loading || !line} onChange={event => { setDirection(event.target.value); setCourse('') }}>
        <option value="">Wybierz kierunek</option>{directions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select></label>
      <label className={styles.wide}>Konkretny kurs<select value={course} disabled={loading || !direction} onChange={event => setCourse(event.target.value)}>
        <option value="">Wybierz godzinę i kurs</option>{choices.map(item => {
          const instant = (leg === 'arrival' ? item.arrival_at : item.departure_at)!
          const hints = timeHints(instant, reference ?? times[0] ?? instant, times)
          return <option key={journeyKey(item)} value={journeyKey(item)}>
            {eventClock(instant, times)}{hints.length ? ` (${hints.join(', ')})` : ''} — kurs {item.trip_id.split(':')[1]} / dzień kursowania {item.service_date}
          </option>
        })}
      </select></label>
    </div>
    <div className={styles.pickerNotice} role="status" aria-live="polite">
      {loading ? 'Wczytywanie kursów…' : current?.error ? <p role="alert">{current.error} <button onClick={() => setAttempt(value => value + 1)}>Ponów pobieranie</button></p>
        : !journeys.length ? 'Brak dostępnych kursów tego dnia. Wybierz inną datę z zakresu importu.'
          : data?.has_more ? 'Lista została ograniczona do 2000 kursów. Nie pokazuje całego dnia.'
            : chosen ? `${fullDate((leg === 'arrival' ? chosen.arrival_at : chosen.departure_at)!)}. Dzień kursowania: ${chosen.service_date}.`
              : 'Wybierz linię, kierunek i konkretny kurs. Godzinę pobierzemy z rozkładu.'}
    </div>
    <div className={styles.pickerActions}><button onClick={onClose}>Anuluj</button><button className={styles.primary} disabled={!chosen || loading || !!current?.error}
      onClick={() => { if (chosen) onChoose(chosen) }}>Wybierz kurs</button></div>
  </dialog>
}
