import { useEffect, useId, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { request } from './api'
import { calendarDate, clock, eventClock, fullDate, timeHints } from './dates'
import { durationParts, markerLanes, timelineEvents } from './timeline'
import { readEvaluation } from './types'
import type { Evaluation, ScenarioInput } from './types'
import StatusFace from './StatusFace'
import type { FaceEmotion } from './StatusFace'
import styles from './TransferAnalysis.module.css'

const emotions: Record<Evaluation['status'], FaceEmotion> = { 'Zdążysz': 'success', 'Na styk': 'edge', 'Nie zdążysz': 'missed' }
const minutes = (value: number) => new Intl.NumberFormat('pl-PL', { maximumFractionDigits: 2 }).format(value)
const durationText = (value: number) => { const parts = durationParts(value); return `${parts.amount} ${parts.unit}` }

function Timeline({ scenario, result, maxDelay }: { scenario: ScenarioInput; result: Evaluation | null; maxDelay: number }) {
  const events = timelineEvents(scenario, result)
  const context = events.map(event => event.date)
  const rail = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(800)
  useEffect(() => {
    const element = rail.current
    if (!element) return
    const observer = new ResizeObserver(entries => setWidth(entries[0].contentRect.width))
    observer.observe(element)
    return () => observer.disconnect()
  }, [])
  const start = Math.min(Date.parse(scenario.arrival_at), Date.parse(scenario.departure_at))
  // The scale must remain renderable while the API rejects an overflowing delay.
  const end = Math.min(8640000000000000 - 86400000,
    Math.max(Date.parse(scenario.departure_at), Date.parse(scenario.arrival_at) + (maxDelay + scenario.walking_minutes) * 60000, start + 60000))
  const position = (date: string) => 3 + 94 * (Date.parse(date) - start) / (end - start)
  const markers = events.filter(event => position(event.date) <= 97)
  const lanes = markerLanes(markers.map(event => position(event.date)), width)
  const color = result ? styles[emotions[result.status]] : ''
  const ready = result ? position(result.expected_stop_arrival_at) : 0
  const departure = position(scenario.departure_at)
  return <section className={`${styles.timeline} ${color}`} aria-labelledby="timeline-title">
    <div className={styles.timelineHeading}><h2 id="timeline-title">Oś przesiadki</h2><span>Dojście {scenario.walking_minutes} min</span></div>
    <div ref={rail} className={styles.rail} style={{ height: 96 + Math.max(0, ...lanes) * 28 }} aria-hidden="true">
      <div className={styles.track} />
      {result && <div className={styles.marginTrack} style={{ left: `${Math.min(ready, departure)}%`, width: `${Math.abs(departure - ready)}%` }} />}
      {markers.map((event, index) => <div key={event.key}>
        {lanes[index] > 0 && <span className={styles.markerStem} style={{ left: `${position(event.date)}%`, height: lanes[index] * 28 }} />}
        <span data-event-kinds={event.kinds.join(' ')} className={`${styles.marker} ${event.kinds.includes('ready') ? styles.readyMarker : ''}`}
          style={{ left: `${position(event.date)}%`, top: 16 + lanes[index] * 28 }}>{event.symbol}</span>
      </div>)}
      <span className={styles.startTick} style={{ top: 60 + Math.max(0, ...lanes) * 28 }}>{clock(new Date(start).toISOString())}</span>
      <span className={styles.endTick} style={{ top: 60 + Math.max(0, ...lanes) * 28 }}>{clock(new Date(end).toISOString())}</span>
    </div>
    <ol className={styles.events} style={{ '--events': events.length } as CSSProperties}>
      {events.map(event => {
        const hints = timeHints(event.date, scenario.arrival_at, context)
        const time = eventClock(event.date, context)
        return <li key={event.key} className={event.kinds.includes('ready') ? styles.readyEvent : undefined}>
          <details><summary aria-label={`${time} — ${event.description}${hints.length ? '. ' + hints.join(', ') : ''}`}>
            <span className={styles.eventSymbol} aria-hidden="true">{event.symbol}</span>
            <span className={styles.eventCaption}><time dateTime={event.date}>{time}</time><span> — {event.label}</span></span>
            {hints.length > 0 && <span className={styles.eventHint}>{hints.join(' / ')}</span>}
          </summary><p>{fullDate(event.date)}</p></details>
        </li>
      })}
    </ol>
    <p className={styles.timelineHint}>Wybierz zdarzenie, aby zobaczyć datę i offset czasu.
      {events.some(event => position(event.date) > 97) && ' Plan B jest poza zakresem skali.'}</p>
  </section>
}

function JourneyTime({ label, date, reference, context }: { label: string; date: string; reference: string; context: string[] }) {
  const hints = timeHints(date, reference, context)
  return <details className={styles.journeyTime}>
    <summary aria-label={`${label}, ${clock(date)}${hints.length ? ', ' + hints.join(', ') : ''}`}>
      <span>{label}</span><time dateTime={date}>{clock(date)}</time>
      {hints.length > 0 && <small>{hints.join(' / ')}</small>}
    </summary>
    <p>{fullDate(date)}</p>
  </details>
}

export default function TransferAnalysis({ scenario }: { scenario: ScenarioInput }) {
  const [delay, setDelay] = useState(0)
  const [attempt, setAttempt] = useState(0)
  const [response, setResponse] = useState<{ scenario: ScenarioInput; delay: number; attempt: number; data?: Evaluation; error?: string } | null>(null)
  const id = useId()
  const current = response?.scenario === scenario && response.delay === delay && response.attempt === attempt ? response : null
  const result = current?.data ?? null
  const margin = durationParts(result?.margin_minutes ?? 0)
  const error = current?.error ?? ''
  const threshold = response?.scenario === scenario ? response.data?.delay_threshold_minutes : undefined
  const sliderMax = Math.max(30, Math.ceil(Math.max(0, threshold ?? 0) / 10) * 10 + 10, Math.ceil(delay / 10) * 10)
  const emotion: FaceEmotion = error ? 'error' : result ? result.plan_b_status === 'unavailable' ? 'unavailable' : emotions[result.status] : 'loading'
  const context = [scenario.arrival_at, scenario.departure_at, ...(result ? [result.expected_stop_arrival_at] : []), ...(result?.plan_b_departure_at ? [result.plan_b_departure_at] : [])]

  useEffect(() => {
    const controller = new AbortController()
    let disposed = false
    const timer = window.setTimeout(() => {
      const { arrival_at, departure_at, walking_minutes, next_departures } = scenario
      request<unknown>('/api/transfers/evaluate', {
        method: 'POST', signal: controller.signal,
        body: JSON.stringify({ arrival_at, departure_at, walking_minutes, next_departures, delay_minutes: delay }),
      }).then(readEvaluation)
        .then(data => { if (!disposed) setResponse({ scenario, delay, attempt, data }) })
        .catch((error: Error) => { if (!disposed) setResponse({ scenario, delay, attempt, error: error.message }) })
    }, 150)
    return () => { disposed = true; controller.abort(); window.clearTimeout(timer) }
  }, [scenario, delay, attempt])

  function changeDelay(value: number) {
    if (Number.isFinite(value) && value >= 0) setDelay(value)
  }

  return <div className={styles.analysis}>
    <div className={styles.journey}>
      <p className={styles.date}>{calendarDate(scenario.arrival_at)} <span>/</span> czas Warszawy</p>
      <h1>{scenario.interchange}</h1>
      <div className={styles.route}><span>{scenario.arrival_line}</span><span className={styles.routeConnector} aria-hidden="true">→</span><span>{scenario.departure_line}</span><p>Kierunek: {scenario.direction}</p></div>
      <div className={styles.times}>
        <JourneyTime label="Planowany przyjazd" date={scenario.arrival_at} reference={scenario.arrival_at} context={context} />
        <JourneyTime label="Planowany odjazd" date={scenario.departure_at} reference={scenario.arrival_at} context={context} />
      </div>
      <Timeline scenario={scenario} result={result} maxDelay={sliderMax} />
      <section className={styles.planB} aria-labelledby="plan-b-title">
        <h2 id="plan-b-title">Plan B</h2>
        {!result ? <p>{error ? 'Plan B będzie dostępny po ponowieniu analizy.' : 'Sprawdzanie kolejnego kursu…'}</p>
          : result.plan_b_status === 'available' && result.plan_b_departure_at ? <div className={styles.alternative}>
            <JourneyTime label="Kolejny odjazd" date={result.plan_b_departure_at} reference={scenario.arrival_at} context={context} />
            <div><p>Linia {scenario.departure_line}, kierunek {scenario.direction}</p></div>
          </div>
            : result.plan_b_status === 'unavailable' ? <div className={styles.noAlternative}><p>Brak osiągalnego kolejnego odjazdu w tym scenariuszu.</p></div>
              : <p>Pierwotny kurs jest osiągalny. Plan B nie jest potrzebny.</p>}
      </section>
    </div>
    <aside className={styles.panel} aria-label="Wynik i opóźnienie">
      <div className={`${styles.result} ${styles[emotion]}`} aria-busy={!result && !error}>
        <div className={styles.resultHeading}><span>Zapas czasu</span><StatusFace emotion={emotion} /></div>
        <div className={styles.resultCopy} role="status" aria-live="polite" aria-atomic="true">
          {result ? <><output className={`${styles.margin} ${margin.amount.length > 5 ? styles.preciseMargin : ''}`}>{result.margin_minutes > 0 ? '+' : ''}{margin.amount}<span> {margin.unit}</span></output><h2>{result.status}</h2></>
            : <><span className={styles.pending}>—</span><h2>{error ? 'Nie można ocenić' : 'Przeliczanie…'}</h2></>}
        </div>
        {error && <div className={styles.error} role="alert"><p>{error}</p><button onClick={() => setAttempt(value => value + 1)}>Ponów analizę</button></div>}
      </div>
      <div className={styles.delayControl}>
        <label htmlFor={`${id}-number`}>Opóźnienie przyjazdu</label>
        <div className={styles.delayNumber}>
          <button aria-label="Zmniejsz opóźnienie o minutę" disabled={delay === 0} onClick={() => changeDelay(Math.max(0, delay - 1))}>−</button>
          <div><input id={`${id}-number`} type="number" inputMode="numeric" min="0" step="1" value={delay} onChange={event => changeDelay(Number(event.target.value))} /><span>min</span></div>
          <button aria-label="Zwiększ opóźnienie o minutę" onClick={() => changeDelay(delay + 1)}>+</button>
        </div>
        <div className={styles.slider}>
          <input aria-label="Opóźnienie przyjazdu — suwak" aria-valuetext={`${minutes(delay)} min opóźnienia`} aria-describedby={`${id}-threshold`}
            type="range" min="0" max={sliderMax} step="1" value={delay} onChange={event => changeDelay(Number(event.target.value))} />
          {threshold !== undefined && threshold >= 0 && <span className={styles.thresholdMarker} style={{ left: `calc(12px + (100% - 24px) * ${threshold / sliderMax})` }} aria-hidden="true" />}
        </div>
        <div className={styles.sliderLimits} aria-hidden="true"><span>0 min</span><span>{minutes(sliderMax)} min</span></div>
        <p id={`${id}-threshold`} className={styles.threshold}>{threshold === undefined ? 'Próg opóźnienia pojawi się po analizie.'
          : threshold > 0 ? <>Próg opóźnienia: <strong>{durationText(threshold)}</strong>.<br />Przy tej wartości jesteś na styk.</>
            : threshold === 0 ? 'Już bez opóźnienia jesteś na styk. Scenariusz nie ma bezpiecznego marginesu.'
              : `Brakuje ${durationText(Math.abs(threshold))} już bez opóźnienia. Scenariusz nie ma bezpiecznego marginesu.`}</p>
      </div>
      <p className={styles.note}>Symulacja na podstawie zapisanego rozkładu. Bez danych o ruchu na żywo.</p>
    </aside>
  </div>
}
