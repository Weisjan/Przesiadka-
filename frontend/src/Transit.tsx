import { useEffect, useId, useMemo, useState } from 'react'
import { request } from './api'
import { calendarDate, clock, fullDate, timeHints } from './dates'
import { durationParts } from './timeline'
import { readSearch, readSetup, searchInput, transportName } from './transitData'
import { applyWalkingEstimate, readWalking, selectWalkingPair } from './walkingData'
import type { WalkingInput, WalkingResponse } from './walkingData'
import type { Journey, Leg, SearchResponse, TransferLink, TransitSource } from './transitData'
import type { FigureState } from './TransitFigure'
import type { ScenarioInput } from './types'
import TransitFigure from './TransitFigure'
import JourneyPicker from './JourneyPicker'
import { Timeline } from './TransferAnalysis'
import styles from './Transit.module.css'

const states: Record<string, FigureState> = { 'Zdążysz': 'success', 'Na styk': 'edge', 'Nie zdążysz': 'missed' }

function CourseCard({ leg, journey, reference, delay, manual, disabled, onChoose }: {
  leg: Leg; journey: Journey | null; reference?: string; delay: number; manual: boolean; disabled: boolean; onChoose: () => void
}) {
  const instant = leg === 'arrival' ? journey?.arrival_at : journey?.departure_at
  const hints = instant ? timeHints(instant, reference ?? instant, [instant, ...(reference ? [reference] : [])]) : []
  return <section className={`${styles.courseCard} ${leg === 'arrival' ? styles.arrivalCard : styles.departureCard}`} aria-label={leg === 'arrival' ? 'Linia 1 — przyjazd' : 'Linia 2 — odjazd'}>
    <div className={styles.cardHeading}><h2>Linia {leg === 'arrival' ? '1' : '2'}</h2><button disabled={disabled} onClick={onChoose}>
      {journey ? 'Zmień kurs' : 'Wybierz kurs'} <span aria-hidden="true">↗</span></button></div>
    <p className={styles.line}>{journey ? <>{journey.line} <span>{journey.operator === 'skm' ? journey.line === 'SKM' ? '' : 'SKM' : transportName(journey.route_type)}</span></> : leg === 'arrival' ? 'SKM Trójmiasto' : 'ZTM Gdańsk'}</p>
    <p className={styles.stop}>{journey?.stop_name ?? (leg === 'arrival' ? 'Gdańsk Główny' : 'Dworzec Główny 01')}</p>
    <p className={styles.direction}>{journey ? `Kierunek: ${journey.direction ?? 'niepodany w rozkładzie'}` : 'Wybierz przejazd z lokalnego rozkładu'}</p>
    <div className={styles.cardTime}><span>{leg === 'arrival' ? 'Przyjazd' : 'Odjazd'}</span>
      {instant ? <details><summary aria-label={`${leg === 'arrival' ? 'Planowany przyjazd' : 'Planowany odjazd'} ${clock(instant)}. ${hints.join(', ')}`}><time dateTime={instant}>{clock(instant)}</time></summary>
        <p>{fullDate(instant)}<br />Dzień kursowania: {journey?.service_date}</p></details> : <span className={styles.unsetTime}>—:—</span>}
    </div>
    {hints.length > 0 && <p className={styles.timeHint}>{hints.join(' / ')}</p>}
    {journey && leg === 'arrival' && <p className={styles.delayHint}>+{delay} min · {manual ? 'ręczna korekta' : 'symulacja'}</p>}
  </section>
}

export default function Transit() {
  const [setup, setSetup] = useState<{ link?: TransferLink; sources?: TransitSource[]; error?: string } | null>(null)
  const [attempt, setAttempt] = useState(0)
  const [arrival, setArrival] = useState<Journey | null>(null)
  const [departure, setDeparture] = useState<Journey | null>(null)
  const [picker, setPicker] = useState<Leg | null>(null)
  const [walkingInput, setWalkingInput] = useState<WalkingInput>({ pair: '', value: '', manual: false })
  const [walkingResponse, setWalkingResponse] = useState<{ pair: string; data?: WalkingResponse; error?: string } | null>(null)
  const [delay, setDelay] = useState(0)
  const [manual, setManual] = useState(false)
  const [retry, setRetry] = useState(0)
  const [response, setResponse] = useState<{ key: string; base: string; data?: SearchResponse; error?: string } | null>(null)
  const id = useId()
  const walking = walkingInput.value
  const fromStop = setup?.link?.arrival_stop.stop_id ?? ''
  const toStop = setup?.link?.departure_stop.stop_id ?? ''
  const walkingPair = fromStop && toStop ? JSON.stringify([fromStop, toStop]) : ''
  const currentWalking = walkingResponse?.pair === walkingPair ? walkingResponse : null
  const walkingEstimate = currentWalking?.data?.estimate
  const walkingMinutes = walking.trim() === '' ? null : Number(walking)
  const validWalking = walkingMinutes !== null && Number.isInteger(walkingMinutes) && walkingMinutes >= 0 && walkingMinutes <= 180
  const payload = setup?.link && arrival && departure && validWalking ? searchInput(setup.link, arrival, departure, walkingMinutes!, delay) : null
  const selection = { arrival_at: arrival?.arrival_at, departure_at: departure?.departure_at }
  const base = payload ? JSON.stringify({ ...payload, ...selection, delay_minutes: 0 }) : ''
  const key = payload ? JSON.stringify({ ...payload, ...selection, retry }) : ''
  const current = key && response?.key === key ? response : null
  const data = current?.data
  const result = data?.results[0]?.evaluation ?? null
  const error = current?.error
  const state: FigureState = error ? 'error' : result ? states[result.status] : payload ? 'loading' : 'idle'
  const margin = result ? durationParts(result.margin_minutes) : null
  const threshold = response?.base === base ? response.data?.results[0]?.evaluation.delay_threshold_minutes : undefined
  const sliderMax = Math.min(180, Math.max(30, Math.ceil((threshold ?? 0) + 10), delay))
  const scenario = useMemo<ScenarioInput | null>(() => arrival?.arrival_at && departure?.departure_at && validWalking ? {
    name: 'Przesiadka z rozkładu', interchange: arrival.stop_name, arrival_line: arrival.line, departure_line: departure.line,
    direction: departure.direction ?? 'Kierunek niepodany', arrival_at: arrival.arrival_at, departure_at: departure.departure_at,
    walking_minutes: walkingMinutes!, next_departures: [],
  } : null, [arrival, departure, validWalking, walkingMinutes])

  useEffect(() => {
    const controller = new AbortController()
    let disposed = false
    setSetup(null)
    Promise.all([
      request<unknown>('/api/transit/sources', { signal: controller.signal }),
      request<unknown>('/api/transit/transfer-links', { signal: controller.signal }),
    ]).then(([sources, links]) => {
      const data = readSetup(sources, links)
      if (!disposed) setSetup(data)
    }).catch((error: Error) => { if (!disposed) setSetup({ error: error.message }) })
    return () => { disposed = true; controller.abort() }
  }, [attempt])

  useEffect(() => {
    if (!walkingPair) return
    const controller = new AbortController()
    let disposed = false
    setWalkingInput(current => selectWalkingPair(current, walkingPair))
    request<unknown>(`/api/transit/walking-transfers?${new URLSearchParams({ from_stop_id: fromStop, to_stop_id: toStop })}`, { signal: controller.signal })
      .then(value => readWalking(value, fromStop, toStop))
      .then(data => {
        if (disposed) return
        setWalkingResponse({ pair: walkingPair, data })
        setWalkingInput(current => applyWalkingEstimate(current, walkingPair, data))
      })
      .catch((error: Error) => {
        if (disposed) return
        setWalkingResponse({ pair: walkingPair, error: error.message })
        setWalkingInput(current => current.pair === walkingPair && !current.manual ? { ...current, value: '' } : current)
      })
    return () => { disposed = true; controller.abort() }
  }, [walkingPair, fromStop, toStop])

  useEffect(() => {
    if (!payload) return
    const controller = new AbortController()
    let disposed = false
    const timer = window.setTimeout(() => {
      request<unknown>('/api/transit/transfers/search', { method: 'POST', signal: controller.signal, body: JSON.stringify(payload) })
        .then(value => readSearch(value, departure!, arrival!))
        .then(data => { if (!disposed) setResponse({ key, base, data }) })
        .catch((error: Error) => { if (!disposed) setResponse({ key, base, error: error.message }) })
    }, 150)
    return () => { disposed = true; controller.abort(); window.clearTimeout(timer) }
    // The serialized key includes every input, including the exact service-day occurrence.
  }, [key])

  function choose(leg: Leg, journey: Journey) {
    if (leg === 'arrival') { setArrival(journey); setDeparture(null) }
    else setDeparture(journey)
    setDelay(0)
    setManual(false)
    setPicker(null)
  }

  return <section className={styles.transit} aria-label="Przesiadka z rozkładu">
    <h1 className={styles.srOnly}>Sprawdź przesiadkę SKM → ZTM</h1>
    {(!setup || setup.error) && <div className={styles.setupNotice} role={setup?.error ? 'alert' : 'status'}>
      {setup?.error ? <><p>{setup.error}</p><button onClick={() => setAttempt(value => value + 1)}>Sprawdź rozkłady ponownie</button></> : 'Sprawdzanie lokalnych rozkładów…'}
    </div>}
    <div className={styles.board}>
      <CourseCard leg="arrival" journey={arrival} delay={delay} manual={manual} disabled={!setup?.link} onChoose={() => setPicker('arrival')} />
      <CourseCard leg="departure" journey={departure} reference={arrival?.arrival_at ?? undefined} delay={delay} manual={manual} disabled={!setup?.link || !arrival} onChoose={() => setPicker('departure')} />
      <div className={`${styles.result} ${styles[state]}`} aria-busy={state === 'loading'}>
        <TransitFigure state={state} />
        <div role="status" aria-live="polite" aria-atomic="true" className={styles.resultText}>
          <p className={styles.status}>{result?.status ?? (error ? 'Nie można ocenić' : payload ? 'Przeliczanie…' : 'Twoja przesiadka')}</p>
          <output className={styles.margin} aria-label={result ? `Zapas czasu: ${result.margin_minutes} minut` : 'Brak wyniku'}>
            {margin ? <>{result!.margin_minutes > 0 ? '+' : ''}{margin.amount}<span> {margin.unit}</span></> : <span className={styles.waiting}>—</span>}
          </output>
          <p className={styles.resultHint}>{result ? `Zapas po ${walking} min dojścia` : error ? 'Sprawdź komunikat błędu poniżej.' : payload ? 'Sprawdzamy wybrane kursy…'
            : !arrival ? 'Wybierz kurs, którym przyjeżdżasz.' : !departure ? 'Wybierz kurs, na który się przesiadasz.' : 'Podaj szacowany czas dojścia.'}</p>
        </div>
      </div>
      <div className={styles.delayControl}>
        <div className={styles.sliderHeading}><label htmlFor={`${id}-delay`}>Opóźnienie pierwszej linii</label><output htmlFor={`${id}-delay`}>+{delay} min</output></div>
        <div className={styles.slider}><input id={`${id}-delay`} type="range" min="0" max={sliderMax} step="1" value={delay}
          aria-valuetext={`${delay} minut, ${manual ? 'ręczna korekta' : 'symulacja'}`} aria-describedby={`${id}-delay-source ${id}-threshold`}
          disabled={!arrival} onChange={event => { setDelay(Number(event.target.value)); setManual(true) }} />
          {threshold !== undefined && threshold >= 0 && threshold <= sliderMax && <span aria-hidden="true" className={styles.thresholdMarker} style={{ left: `calc(8px + (100% - 16px) * ${threshold / sliderMax})` }} />}
        </div>
        <div className={styles.sliderLimits} aria-hidden="true"><span>0 min</span><span>{sliderMax} min</span></div>
        <p id={`${id}-delay-source`} className={styles.delaySource}>{manual && <strong>Ręczna korekta. </strong>}Brak danych o aktualnym opóźnieniu — symulacja.
          {manual && <button onClick={() => { setDelay(0); setManual(false) }}>Przywróć 0 min</button>}</p>
        <p id={`${id}-threshold`} className={styles.threshold}>{threshold === undefined ? 'Próg pojawi się po wybraniu kursów i podaniu dojścia.'
          : threshold <= 0 ? 'Brak bezpiecznego marginesu już bez opóźnienia.' : `Próg opóźnienia: ${durationParts(threshold).amount} ${durationParts(threshold).unit}. Przy tej wartości jesteś na styk.`}</p>
      </div>
    </div>
    {error && <div className={styles.error} role="alert"><p>{error}</p><p>Wybierz inny kurs lub datę. Obsługiwane okno to 6 godzin od planowanego przyjazdu.</p><button onClick={() => setRetry(value => value + 1)}>Ponów analizę</button></div>}
    <div className={styles.contextRow}>
      <div><p className={styles.contextTitle}>{arrival?.arrival_at ? calendarDate(arrival.arrival_at) : 'SKM Gdańsk Główny → ZTM Dworzec Główny 01'}</p>
        <p>Rozkład planowany · czas Warszawy · bez danych na żywo</p></div>
      <label className={styles.walking}>Szacowany czas dojścia<div><input aria-label="Szacowany czas dojścia" type="number" inputMode="numeric" min="0" max="180" step="1" placeholder="Podaj" value={walking}
        aria-invalid={walking !== '' && !validWalking} onChange={event => setWalkingInput(current => ({ ...current, value: event.target.value, manual: true }))} /><span>min</span></div></label>
    </div>
    {walking !== '' && !validWalking && <p className={styles.error} role="alert">Podaj całkowitą liczbę minut od 0 do 180.</p>}
    <div className={styles.walkingNote} aria-live="polite">
      {currentWalking?.data?.status === 'available' && walkingEstimate ? <>
        <p>{walkingInput.manual ? 'Ręczna korekta czasu dojścia.' : 'Szacowany czas dojścia na podstawie OpenRouteService.'}
          {' '}Szacunek ORS: {walkingEstimate.walking_minutes} min, {new Intl.NumberFormat('pl-PL', { maximumFractionDigits: 1 }).format(walkingEstimate.distance_m!)} m.
          {' '}Czas zaokrąglono w górę do pełnej minuty. Wyliczono: {fullDate(walkingEstimate.calculated_at)}.</p>
      </> : <p>{currentWalking?.error ? `Nie udało się odczytać szacunku dojścia: ${currentWalking.error} Podaj czas ręcznie.`
        : currentWalking?.data?.status === 'no_route' ? 'OpenRouteService nie wyznaczył trasy dla tej pary. Możesz podać własny czas dojścia.'
          : currentWalking?.data?.status === 'stale' ? 'Zapisany szacunek dojścia jest nieaktualny. Podaj własny czas; odświeżenie wymaga jawnego importu.'
            : !currentWalking && walkingPair ? 'Sprawdzanie zapisanego szacunku dojścia… Możesz podać czas ręcznie.'
              : 'Brak zapisanego szacunku dojścia. Podaj własny czas w minutach.'}</p>}
      {walkingEstimate && <p>{walkingEstimate.attribution}. <a href="https://openrouteservice.org/" target="_blank" rel="noreferrer">OpenRouteService / HeiGIT</a>
        {' · '}<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a>
        {' · '}<a href={walkingEstimate.license_url} target="_blank" rel="noreferrer">CC BY-SA 4.0</a></p>}
      <p>Dojście pozostaje szacunkiem. Rozkład SKM nie określa peronu, a model ORS nie potwierdza dostępności przejścia.</p>
    </div>
    <div className={styles.detailsGrid}>
      <details className={styles.disclosure}><summary>Szczegóły przesiadki <span aria-hidden="true">+</span></summary>
        {scenario ? <Timeline scenario={scenario} result={result} maxDelay={sliderMax} /> : <p>Wybierz oba kursy i uzupełnij dojście, aby zobaczyć oś czasu.</p>}
      </details>
      <details key={`${base}:${result?.status === 'Nie zdążysz'}`} className={styles.disclosure} open={result?.status === 'Nie zdążysz'}>
        <summary>Plan B <span aria-hidden="true">+</span></summary>
        {!result ? <p>Plan B pojawi się po poprawnej analizie.</p> : result.plan_b_status === 'not_needed' ? <p>Wybrany kurs jest osiągalny. Plan B nie jest potrzebny.</p>
          : data?.results[0]?.plan_b ? <div className={styles.planB}>
            <time dateTime={data.results[0].plan_b.departure_at!}>{clock(data.results[0].plan_b.departure_at!)}</time>
            <p>Linia {data.results[0].plan_b.line} · {data.results[0].plan_b.direction}<br />{data.results[0].plan_b.stop_name}</p>
            <p>{fullDate(data.results[0].plan_b.departure_at!)}<br />Źródło: lokalny rozkład ZTM Gdańsk. Kurs tego samego wariantu trasy.</p>
          </div> : <p>Brak osiągalnego kolejnego kursu tego wariantu w przeszukanym oknie 6 godzin. To nie oznacza braku innych połączeń.</p>}
        {data && <p className={styles.help}>Przeszukane okno: {fullDate(data.search_window.start_at)} — {fullDate(data.search_window.end_at_exclusive)} (koniec wyłączony).</p>}
      </details>
    </div>
    <details className={styles.sources}><summary>Źródła i zakres rozkładów</summary>
      {setup?.sources?.map(source => <div key={source.operator}><p><a href={source.documentation_url} target="_blank" rel="noreferrer">{source.name}</a></p>
        <p>{source.attribution}</p><p>Dni kursowania: {source.service_start_date} — {source.service_end_date}.
          {source.downloaded_at && ` Pobrano: ${fullDate(source.downloaded_at)}.`} Nie jest to potwierdzenie aktualnego ruchu.</p></div>)}
      <p>Inne pary przystanków nie są jeszcze obsługiwane. Data poza zakresem importu wymaga ręcznego zaimportowania właściwego rozkładu.</p>
    </details>
    {picker && setup?.link && setup.sources && <JourneyPicker leg={picker} stop={picker === 'arrival' ? setup.link.arrival_stop : setup.link.departure_stop}
      source={setup.sources.find(source => source.operator === (picker === 'arrival' ? 'skm' : 'ztm'))!}
      selected={picker === 'arrival' ? arrival : departure} reference={arrival?.arrival_at ?? undefined}
      onClose={() => setPicker(null)} onChoose={journey => choose(picker, journey)} />}
  </section>
}
