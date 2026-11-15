import { useEffect, useId, useRef, useState } from 'react'
import type { CSSProperties, FormEvent } from 'react'
import { request } from './api'
import { clock, dateTimeOptions, fromIso, fullDate, timeHints } from './dates'
import { readAvailability } from './demoData'
import type { Availability, DemoExample } from './demoData'
import { durationParts, figureState } from './formatting'
import { planIdentity, readPlan, readPlannedEvaluation } from './plannerData'
import type { PlanInput, PlannedJourney, PlanResponse, StopGroup } from './plannerData'
import { searchInput, transportName } from './transitData'
import type { SearchResponse } from './transitData'
import StopPicker from './StopPicker'
import TransitFigure from './TransitFigure'
import styles from './Transit.module.css'
import layout from './Planner.module.css'

const notices: Record<string, string> = {
  no_skm: 'Brak odjazdów SKM z tej stacji w ciągu 6 godzin. Wybierz inną godzinę.',
  no_transfer_link: 'Na dalszej trasie tych pociągów nie ma obsługiwanej, zatwierdzonej przesiadki ZTM.',
  walking_unavailable: 'Brak aktualnego szacunku dojścia na dostępnych przesiadkach. Wybierz inną podróż lub zaktualizuj lokalne dane.',
  no_destination_service: 'Nie znaleziono kursu do tego celu wśród obsługiwanych przesiadek i w oknie 6 godzin.',
  no_reachable: 'Nie ma osiągalnej przesiadki do tego celu w oknie 6 godzin. Spróbuj wcześniejszej godziny.',
}
const labels = { success: 'Masz zapas', edge: 'Na styk', missed: 'Nie zdążysz', idle: 'Twoja przesiadka' }

function EventTime({ value, reference }: { value: string; reference: string }) {
  const hints = timeHints(value, reference, [value, reference])
  return <details><summary aria-label={`Szczegóły godziny ${clock(value)}`}><time dateTime={value}>{clock(value)}</time>
    {hints.length > 0 && <span className={styles.timeHint}> {hints.join(' / ')}</span>}</summary><p>{fullDate(value)}</p></details>
}

function JourneyCard({ plan, arrival, reference }: { plan: PlannedJourney | null; arrival: boolean; reference: string }) {
  const start = arrival ? plan?.origin : plan?.departure
  const finish = arrival ? plan?.arrival : plan?.destination
  return <section className={`${styles.courseCard} ${arrival ? styles.arrivalCard : styles.departureCard} ${layout.journeyCard}`}
    aria-label={arrival ? 'Twój przejazd SKM' : 'Twój przejazd ZTM'}>
    <div className={`${styles.cardHeading} ${layout.legHeading}`}><h2>{arrival ? 'SKM Trójmiasto' : 'ZTM Gdańsk'}</h2></div>
    <p className={styles.line}>{start ? <>{start.line} {arrival ? '' : transportName(start.route_type)}</> : '—'}</p>
    <p className={styles.direction}>{start ? `Kierunek: ${start.direction ?? 'niepodany w rozkładzie'}` : arrival ? 'Wskaż skąd i kiedy wyruszasz.' : 'Wybierz cel podróży.'}</p>
    <div className={layout.legStart}><span>{arrival ? 'Wsiadasz' : 'Po dojściu wsiadasz'}</span>
      <p>{start?.stop_name ?? '—'}</p>{start?.departure_at && <EventTime value={start.departure_at} reference={reference} />}</div>
    <div className={`${styles.cardTime} ${layout.endTime}`}><span>{arrival ? 'Przesiadasz się' : 'Docierasz do celu'}<br />{finish?.stop_name}</span>
      {finish?.arrival_at ? <EventTime value={finish.arrival_at} reference={reference} /> : <span className={styles.unsetTime}>—:—</span>}</div>
  </section>
}

export default function Transit() {
  const initial = fromIso(new Date().toISOString())
  const [origin, setOrigin] = useState<StopGroup | null>(null)
  const [destination, setDestination] = useState<StopGroup | null>(null)
  const [day, setDay] = useState(initial.date)
  const [time, setTime] = useState(initial.time)
  const [offset, setOffset] = useState('')
  const [submitted, setSubmitted] = useState<{ key: string; input: PlanInput; attempt: number } | null>(null)
  const [reply, setReply] = useState<{ key: string; data?: PlanResponse; error?: string } | null>(null)
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [alternatives, setAlternatives] = useState(false)
  const [delay, setDelay] = useState(0)
  const [evaluation, setEvaluation] = useState<{ key: string; course: string; data?: SearchResponse; error?: string } | null>(null)
  const [availability, setAvailability] = useState<Availability | null>(null)
  const [availabilityError, setAvailabilityError] = useState('')
  const [availabilityAttempt, setAvailabilityAttempt] = useState(0)
  const [exampleVersion, setExampleVersion] = useState(0)
  const [examplesOpen, setExamplesOpen] = useState(false)
  const [editing, setEditing] = useState(true)
  const resultSummary = useRef<HTMLDivElement>(null)
  const userEdited = useRef(false)
  const id = useId()
  const options = dateTimeOptions({ date: day, time, offset: '' })
  const input: PlanInput | null = origin && destination && options.length && (options.length === 1 || offset)
    ? { origin_stop_ids: origin.stops.map(s => s.stop_id).sort(), destination_stop_ids: destination.stops.map(s => s.stop_id).sort(),
      departure_date: day, departure_time: time, departure_offset: options.length > 1 ? offset : options[0].slice(-6), max_results: 3 } : null
  const inputKey = input ? JSON.stringify(input) : ''
  const current = submitted?.key === inputKey && reply?.key === submitted.key ? reply : null
  const data = current?.data
  const plan = data?.results[selectedIndex] ?? null
  const course = plan ? `${inputKey}:${planIdentity(plan)}` : ''
  const payload = plan ? searchInput(plan.link, plan.arrival, plan.departure, delay) : null
  const evaluationKey = payload ? JSON.stringify({ course, ...payload }) : ''
  const evaluated = evaluation?.key === evaluationKey ? evaluation : null
  const result = evaluated?.data?.results[0]?.evaluation
  const error = evaluated?.error
  const pending = !!plan && !evaluated
  const figureMargin = error ? null : result?.margin_minutes
    ?? (evaluation?.course === course ? evaluation.data?.results[0]?.evaluation.margin_minutes : null) ?? null
  const margin = result ? durationParts(result.margin_minutes) : null
  const state = figureState(result?.margin_minutes ?? null)
  const searching = !!submitted && submitted.key === inputKey && !current

  function invalidate() {
    userEdited.current = true
    setSubmitted(null); setReply(null); setSelectedIndex(0); setAlternatives(false); setEvaluation(null)
    setEditing(true)
  }
  useEffect(() => {
    const controller = new AbortController()
    let disposed = false
    setAvailabilityError('')
    request<unknown>('/api/transit/sources', { signal: controller.signal }).then(readAvailability).then(data => {
      if (disposed) return
      setAvailability(data)
      if (data.demo && !userEdited.current) { setDay(data.demo.departure_date); setTime('17:00'); setOffset('') }
    }).catch((error: Error) => { if (!disposed) setAvailabilityError(error.message) })
    return () => { disposed = true; controller.abort() }
  }, [availabilityAttempt])
  useEffect(() => {
    if (!data?.results.length) return
    setEditing(false)
  }, [data])
  useEffect(() => {
    if (!data?.results.length || editing || !window.matchMedia('(max-width: 1000px)').matches) return
    const frame = window.requestAnimationFrame(() => {
      resultSummary.current?.focus({ preventScroll: true })
      resultSummary.current?.scrollIntoView({ block: 'start', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' })
    })
    return () => window.cancelAnimationFrame(frame)
  }, [data, editing])
  useEffect(() => {
    if (!submitted || submitted.key !== inputKey) return
    const controller = new AbortController()
    let disposed = false
    request<unknown>('/api/transit/journeys/plan', { method: 'POST', body: JSON.stringify(submitted.input), signal: controller.signal })
      .then(value => readPlan(value, submitted.input))
      .then(data => { if (!disposed) setReply({ key: submitted.key, data }) })
      .catch((error: Error) => { if (!disposed) setReply({ key: submitted.key, error: error.message }) })
    return () => { disposed = true; controller.abort() }
  }, [submitted, inputKey])
  useEffect(() => {
    if (!plan || !payload || !data) return
    const controller = new AbortController()
    let disposed = false
    request<unknown>('/api/transit/transfers/search', { method: 'POST', body: JSON.stringify(payload), signal: controller.signal })
      .then(value => readPlannedEvaluation(value, plan, data.sources))
      .then(data => { if (!disposed) setEvaluation({ key: evaluationKey, course, data }) })
      .catch((error: Error) => { if (!disposed) setEvaluation({ key: evaluationKey, course, error: error.message }) })
    return () => { disposed = true; controller.abort() }
  }, [evaluationKey])
  function submit(event: FormEvent) {
    event.preventDefault()
    if (!input) return
    setReply(null); setSelectedIndex(0); setAlternatives(false); setEvaluation(null)
    setSubmitted({ key: inputKey, input, attempt: (submitted?.attempt ?? 0) + 1 })
  }
  function chooseExample(example: DemoExample) {
    userEdited.current = true
    const value: PlanInput = { origin_stop_ids: example.origin.stops.map(s => s.stop_id).sort(), destination_stop_ids: example.destination.stops.map(s => s.stop_id).sort(),
      departure_date: example.departure_date, departure_time: example.departure_time,
      departure_offset: dateTimeOptions({ date: example.departure_date, time: example.departure_time, offset: '' })[0].slice(-6), max_results: 3 }
    setOrigin(example.origin); setDestination(example.destination); setDay(example.departure_date); setTime(example.departure_time); setOffset('')
    setDelay(0); setReply(null); setEvaluation(null); setSelectedIndex(0); setAlternatives(false); setExamplesOpen(false)
    setExampleVersion(x => x + 1)
    setSubmitted({ key: JSON.stringify(value), input: value, attempt: (submitted?.attempt ?? 0) + 1 })
  }

  return <section className={`${styles.transit} ${layout.planner} ${data?.results.length && !editing ? layout.compact : ''}`} aria-label="Zaplanuj podróż SKM i ZTM">
    <h1 className={styles.srOnly}>Zaplanuj podróż SKM → ZTM</h1>
    {availability?.demo && <div className={layout.demo}><p>{availability.demo.label}</p>
      <button type="button" aria-expanded={examplesOpen} onClick={() => setExamplesOpen(x => !x)}>Zobacz przykład</button>
      {examplesOpen && <div role="group" aria-label="Przykłady archiwalnego demo" className={layout.demoExamples}>{availability.demo.examples.map(example =>
        <button key={example.id} type="button" onClick={() => chooseExample(example)}><strong>{example.name}</strong><span>{example.description}</span></button>)}</div>}
    </div>}
    {availabilityError && <p role="alert" className={layout.notice}>{availabilityError} <button type="button" onClick={() => setAvailabilityAttempt(x => x + 1)}>Sprawdź dane ponownie</button></p>}
    <form className={layout.form} onSubmit={submit}>
      <StopPicker key={`origin-${exampleVersion}`} label="Skąd jedziesz?" operator="skm" initialValue={origin} onChange={value => { setOrigin(value); invalidate() }} />
      <fieldset className={layout.when}><legend>Kiedy wyruszasz?</legend><div className={layout.dateTime}>
        <label><span className={styles.srOnly}>Data wyjazdu</span><input type="date" required value={day} min={availability?.first} max={availability?.last}
          onChange={e => { setDay(e.target.value); setOffset(''); invalidate() }} /></label>
        <label><span className={styles.srOnly}>Godzina wyjazdu</span><input type="time" required value={time} min={availability?.demo?.min_departure_time} max={availability?.demo?.max_departure_time}
          onChange={e => { setTime(e.target.value); setOffset(''); invalidate() }} /></label></div>
        <p className={layout.fieldHint}>Czas lokalny: Europe/Warsaw.{availability && <> Dane: {availability.first.split('-').reverse().join('.')}{availability.first !== availability.last && <>–{availability.last.split('-').reverse().join('.')}</>}.
          {availability.demo && <> Wyjazd {availability.demo.min_departure_time}–{availability.demo.max_departure_time}.</>}</>}</p>
        {!options.length && <p role="alert" className={layout.fieldHint}>Wybierz poprawną godzinę. Ta pora może nie istnieć przy zmianie czasu.</p>}
        {options.length > 1 && <label>Godzina występuje dwukrotnie<select required value={offset} onChange={e => { setOffset(e.target.value); invalidate() }}>
          <option value="">Wybierz wystąpienie</option>{options.map((value, index) => <option key={value} value={value.slice(-6)}>{index + 1}. wystąpienie · UTC{value.slice(-6)}</option>)}
        </select></label>}
      </fieldset>
      <StopPicker key={`destination-${exampleVersion}`} label="Dokąd jedziesz?" operator="ztm" initialValue={destination} onChange={value => { setDestination(value); invalidate() }} />
      <div className={layout.searchAction}><p>SKM → szacowane dojście → ZTM. Porównujemy wyłącznie zatwierdzone przesiadki.</p>
        <button className={styles.primary} disabled={!input || searching}>{searching ? 'Wyszukiwanie…' : 'Szukaj podróży'}</button></div>
    </form>
    <div className={layout.notice} role={current?.error ? 'alert' : 'status'}>
      {searching ? 'Porównujemy pociągi, miejsca przesiadki i dotarcie do celu…' : current?.error
        ?? (data && !plan ? notices[data.outcome] : !submitted ? 'Wybierz stację, godzinę i cel. Kursy oraz miejsce przesiadki dobierzemy z lokalnego rozkładu.' : '')}
    </div>
    {data && <div ref={resultSummary} tabIndex={-1} className={layout.summary}><div><p className={layout.selectedGoal}>{origin?.name} → {destination?.name}</p><p>{fullDate(data.requested_departure_at)} · rozkład planowany</p>
      <p>Najlepszy wynik tylko wśród aktualnie obsługiwanych połączeń.</p></div>
      <button type="button" className={layout.editSearch} onClick={() => { setEditing(true); window.requestAnimationFrame(() => document.querySelector<HTMLInputElement>('input[list]')?.focus()) }}>Zmień podróż</button>
      {data.results.length > 1 && <><button id={`${id}-alternatives`} type="button" aria-expanded={alternatives} onClick={() => setAlternatives(x => !x)}>Inne podróże ({data.results.length - 1})</button>
        {alternatives && <div className={layout.alternatives} role="group" aria-label="Warianty podróży">{data.results.map((item, index) =>
          <button key={planIdentity(item)} aria-pressed={index === selectedIndex} onClick={() => { setSelectedIndex(index); setAlternatives(false); setEvaluation(null)
            document.getElementById(`${id}-alternatives`)?.focus() }}>
            <strong>{index === 0 ? 'Rekomendowana' : `Alternatywa ${index}`} · dotarcie {clock(item.destination.arrival_at!)}</strong>
            <span>SKM {clock(item.origin.departure_at!)} → {item.arrival.stop_name} → {item.departure.line} {item.departure.direction}</span>
            <span>Dojście szac. {item.link.walking_minutes} min · {item.risk === 'tight' ? 'mały zapas' : 'zapas co najmniej 2 min'} przy 0 min opóźnienia</span>
          </button>)}</div>}</>}
    </div>}
    <div className={styles.board}>
      <JourneyCard plan={plan} arrival reference={data?.requested_departure_at ?? ''} />
      <JourneyCard plan={plan} arrival={false} reference={data?.requested_departure_at ?? ''} />
      <div className={`${styles.result} ${styles[state]} ${layout.analysis}`} aria-busy={pending}>
        <TransitFigure margin={figureMargin} />
        <div role="status" aria-live="polite" aria-atomic="true" className={styles.resultText}>
          <p className={styles.status}>{error ? 'Nie można ocenić' : pending ? 'Przeliczanie…' : labels[state]}</p>
          <output className={styles.margin} style={{ '--value-length': margin ? margin.amount.length + 1 : 1 } as CSSProperties}
            aria-label={result ? `Zapas czasu: ${result.margin_minutes} minut` : pending ? 'Przeliczanie wyniku' : 'Brak wyniku'}>
            {margin ? <>{result!.margin_minutes > 0 ? '+' : ''}{margin.amount}<span> {margin.unit}</span></> : <span className={styles.waiting}>—</span>}
          </output>
          <p className={styles.resultHint}>{result ? `Zapas po ${plan?.link.walking_minutes} min szacowanego dojścia` : error ? 'Wyszukaj podróż ponownie, aby odświeżyć dane.'
            : pending ? 'Sprawdzamy wybrane kursy…' : 'Tu pojawi się zapas przesiadki.'}</p>
        </div>
      </div>
      <div className={`${styles.delayControl} ${layout.simulation}`}>
        <div className={styles.sliderHeading}><label htmlFor={`${id}-delay`}>Opóźnienie pociągu SKM</label><output>+{delay} min</output></div>
        <div className={styles.slider}><input id={`${id}-delay`} type="range" min="0" max="30" step="1" value={delay}
          aria-valuetext={`${delay} minut symulowanego opóźnienia`} aria-describedby={`${id}-simulation`}
          disabled={!plan} onChange={e => setDelay(Number(e.target.value))} /></div>
        <div className={styles.sliderLimits} aria-hidden="true"><span>0 min</span><span>30 min</span></div>
        <p id={`${id}-simulation`} className={styles.delaySource}>Symulacja opóźnienia. Suwak nie zmienia wybranych kursów ani planowanej godziny dotarcia.</p>
      </div>
    </div>
    {error && <p className={styles.error} role="alert">{error}</p>}
    {plan && <div className={layout.details}><p>Przesiadka: {plan.arrival.stop_name} → {plan.departure.stop_name}. Szacowane dojście: {plan.link.walking_minutes} min.</p>
      <details><summary>Dlaczego ta podróż?</summary><p>{data?.reason}</p><p>Ranking przy 0 min opóźnienia. Podróż od odjazdu SKM: {Math.ceil(plan.total_minutes)} min, oczekiwanie po dojściu: {Math.round(plan.waiting_minutes * 10) / 10} min.</p>
        <p>Zatwierdzone powiązania: {data?.scope.approved_links}; z aktualnym dojściem: {data?.scope.available_links}.</p>
        {availability?.demo && <p>Pomiary ORS odtwarzane według stanu: {fullDate(availability.demo.walking_reference_at)}. To nie jest ich bieżąca aktualność.</p>}
        {data?.limitations.map(text => <p key={text}>{text}</p>)}</details></div>}
    <div className={styles.walkingNote}>
      <p>Wyłącznie lokalny rozkład planowany. Wynik nie jest globalnie najszybszą trasą.</p>
      {data?.sources.map(source => <p key={source.operator}><a href={source.documentation_url} target="_blank" rel="noreferrer">{source.attribution}</a> · {availability?.demo ? 'zakres oryginalnego feedu' : 'dni kursowania'} {source.service_start_date}–{source.service_end_date}</p>)}
      {plan?.link.walking.estimate && <p>Szacowane dojście na podstawie OpenRouteService. {plan.link.walking.estimate.attribution}. <a href={plan.link.walking.estimate.license_url}>CC BY-SA 4.0</a>. Peron SKM nie jest określony.</p>}
    </div>
  </section>
}
