import { useEffect, useId, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { request } from './api'
import { clock, fullDate, timeHints } from './dates'
import { durationParts, figureState } from './formatting'
import { journeyKey, readSearch, readSetup, readSuggestions, searchInput, suggestionInput, transportName } from './transitData'
import type { Journey, SearchResponse, SuggestedTransfer, SuggestionsResponse, TransferLink, TransitSource, TransitStop } from './transitData'
import TransitFigure from './TransitFigure'
import JourneyPicker from './JourneyPicker'
import styles from './Transit.module.css'

function CourseCard({ arrival, journey, stop, control, delay, disabled, onChoose, expanded, children, reference }: {
  arrival: boolean; journey: Journey | null; stop?: TransitStop; control?: ReactNode; delay: number
  disabled: boolean; onChoose: () => void; expanded?: boolean; children?: ReactNode; reference?: string
}) {
  const instant = arrival ? journey?.arrival_at : journey?.departure_at
  const hints = instant ? timeHints(instant, reference ?? instant, [instant, ...(reference ? [reference] : [])]) : []
  return <section className={`${styles.courseCard} ${arrival ? styles.arrivalCard : styles.departureCard}`}
    aria-label={arrival ? 'Twój pociąg SKM' : 'Sugerowana przesiadka ZTM'}>
    <div className={styles.station}>{control ?? <><span className={styles.stationLabel}>Stacja przyjazdu</span>
      <p className={styles.stop}>{stop?.stop_name ?? 'Wczytywanie stacji…'}</p></>}</div>
    <div className={styles.cardHeading}><h2>{arrival ? 'SKM Trójmiasto' : 'ZTM Gdańsk'}</h2>
      <button disabled={disabled} onClick={onChoose} aria-expanded={expanded}>
        {arrival ? journey ? 'Zmień pociąg' : 'Wybierz pociąg' : 'Inny kurs'} <span aria-hidden="true">↗</span>
      </button></div>
    <p className={styles.line}>{journey ? <>{journey.line} <span>{journey.operator === 'skm' ? journey.line === 'SKM' ? '' : 'SKM' : transportName(journey.route_type)}</span></> : '—'}</p>
    <p className={styles.direction}>{journey ? `Kierunek: ${journey.direction ?? 'niepodany w rozkładzie'}` : arrival ? 'Wybierz pociąg z lokalnego rozkładu.' : 'Propozycja pojawi się po wyborze celu.'}</p>
    {!arrival && journey && <p className={styles.stop}>{stop?.stop_name}</p>}
    {arrival && journey && <p className={styles.delayHint}>+{delay} min · symulacja opóźnienia</p>}
    {children}
    <div className={styles.cardTime}><span>{arrival ? 'Przyjazd' : 'Odjazd'}</span>
      {instant ? <details><summary aria-label={`${arrival ? 'Planowany przyjazd' : 'Planowany odjazd'} ${clock(instant)}. ${hints.join(', ')}`}>
        <time dateTime={instant}>{clock(instant)}</time></summary><p>{fullDate(instant)}<br />Dzień kursowania: {journey?.service_date}</p></details>
        : <span className={styles.unsetTime}>—:—</span>}
    </div>
    {hints.length > 0 && <p className={styles.timeHint}>{hints.join(' / ')}</p>}
  </section>
}

const labels = { success: 'Masz zapas', edge: 'Na styk', missed: 'Nie zdążysz', idle: 'Twoja przesiadka' }

export default function Transit() {
  const [setup, setSetup] = useState<{ link?: TransferLink; links?: TransferLink[]; sources?: TransitSource[]; error?: string } | null>(null)
  const [setupAttempt, setSetupAttempt] = useState(0)
  const [arrival, setArrival] = useState<Journey | null>(null)
  const [picker, setPicker] = useState(false)
  const [query, setQuery] = useState('')
  const [suggestionAttempt, setSuggestionAttempt] = useState(0)
  const [suggestions, setSuggestions] = useState<{ key: string; data?: SuggestionsResponse; error?: string } | null>(null)
  const [chosen, setChosen] = useState<{ key: string; item: SuggestedTransfer } | null>(null)
  const [alternativesOpen, setAlternativesOpen] = useState(false)
  const [delay, setDelay] = useState(0)
  const [response, setResponse] = useState<{ key: string; courseKey: string; data?: SearchResponse; error?: string } | null>(null)
  const id = useId()
  const base = arrival && setup?.links ? JSON.stringify({ ...suggestionInput(arrival, query), arrival_at: arrival.arrival_at, suggestionAttempt }) : ''
  const currentSuggestions = base && suggestions?.key === base ? suggestions : null
  const offers = currentSuggestions?.data
  const selected = chosen?.key === base ? chosen.item : null
  const link = selected?.link
  const departure = selected?.departure ?? null
  const payload = selected && arrival ? searchInput(selected.link, arrival, selected.departure, delay) : null
  const courseKey = selected && arrival ? JSON.stringify({ base, link: selected.link.id, arrival_at: arrival.arrival_at,
    departure: journeyKey(selected.departure), departure_at: selected.departure.departure_at, walking: selected.link.walking_minutes }) : ''
  const key = payload ? JSON.stringify({ courseKey, ...payload }) : ''
  const current = key && response?.key === key ? response : null
  const result = current?.data?.results[0]?.evaluation
  const error = current?.error
  const pending = !!payload && !current
  // Keep only the figure's last pose during a same-course calculation. Numeric results always use the current request key.
  const figureMargin = error ? null : result?.margin_minutes
    ?? (courseKey && response?.courseKey === courseKey ? response.data?.results[0]?.evaluation.margin_minutes : null) ?? null
  const state = figureState(result?.margin_minutes ?? null)
  const margin = result ? durationParts(result.margin_minutes) : null
  const walking = selected?.link.walking.estimate
  const recommended = offers?.recommendation
  const isRecommended = selected && recommended && selected.link.id === recommended.link.id
    && journeyKey(selected.departure) === journeyKey(recommended.departure)

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
  }, [setupAttempt])

  useEffect(() => {
    if (!base || !arrival || !setup?.links) return
    const controller = new AbortController()
    let disposed = false
    const timer = window.setTimeout(() => {
      request<unknown>('/api/transit/transfers/suggest', { method: 'POST', signal: controller.signal,
        body: JSON.stringify(suggestionInput(arrival, query)) })
        .then(value => readSuggestions(value, arrival, query, setup.links!))
        .then(data => {
          if (disposed) return
          setSuggestions({ key: base, data })
          setChosen(data.recommendation ? { key: base, item: data.recommendation } : null)
        })
        .catch((error: Error) => { if (!disposed) setSuggestions({ key: base, error: error.message }) })
    }, 180)
    return () => { disposed = true; controller.abort(); window.clearTimeout(timer) }
  }, [base])

  useEffect(() => {
    if (!payload || !selected || !arrival) return
    const controller = new AbortController()
    let disposed = false
    request<unknown>('/api/transit/transfers/search', { method: 'POST', signal: controller.signal, body: JSON.stringify(payload) })
      .then(value => readSearch(value, selected.departure, arrival, selected.link, selected.link.walking_minutes))
      .then(data => { if (!disposed) setResponse({ key, courseKey, data }) })
      .catch((error: Error) => { if (!disposed) setResponse({ key, courseKey, error: error.message }) })
    return () => { disposed = true; controller.abort() }
  }, [key])

  function resetSelection() {
    setChosen(null)
    setResponse(null)
    setDelay(0)
    setAlternativesOpen(false)
  }

  function changeQuery(value: string) {
    if (value.trim() !== query.trim()) resetSelection()
    setQuery(value)
  }

  const suggestionNotice = !arrival ? 'Najpierw wybierz pociąg SKM.' : !currentSuggestions ? 'Sprawdzanie dostępnych przesiadek…'
    : currentSuggestions.error ? currentSuggestions.error
      : offers?.outcome === 'walking_unavailable' ? 'Brak aktualnego szacunku dojścia. Zaktualizuj lokalny cache.'
        : offers?.outcome === 'no_match' ? 'Brak pasującego kursu z aktualnym dojściem. Spróbuj innej linii, kierunku lub przystanku.'
          : offers?.outcome === 'no_reachable' ? 'Brak osiągalnego kursu w ciągu 6 godzin. Zmień cel lub pociąg.'
            : offers?.outcome === 'choose_destination' && !offers.directions.length ? 'Brak osiągalnych kierunków w ciągu 6 godzin.' : ''

  return <section className={styles.transit} aria-label="Przesiadka z rozkładu">
    <h1 className={styles.srOnly}>Znajdź przesiadkę SKM → ZTM</h1>
    {(!setup || setup.error) && <div className={styles.setupNotice} role={setup?.error ? 'alert' : 'status'}>
      {setup?.error ? <><p>{setup.error}</p><button onClick={() => setSetupAttempt(value => value + 1)}>Sprawdź rozkłady ponownie</button></> : 'Sprawdzanie lokalnych rozkładów…'}
    </div>}
    <div className={styles.board}>
      <CourseCard arrival journey={arrival} stop={setup?.link?.arrival_stop} delay={delay} disabled={!setup?.link} onChoose={() => setPicker(true)} />
      <CourseCard arrival={false} journey={departure} stop={link?.departure_stop} delay={delay}
        reference={arrival?.arrival_at ?? undefined}
        disabled={!offers?.results.length} expanded={alternativesOpen} onChoose={() => setAlternativesOpen(value => !value)}
        control={<label className={styles.destination}>Dokąd chcesz jechać?
          <input type="search" value={query} maxLength={120} disabled={!arrival} placeholder="Linia, kierunek lub przystanek"
            aria-describedby={`${id}-suggestion-notice`} onChange={event => changeQuery(event.target.value)} />
        </label>}>
        <div id={`${id}-suggestion-notice`} className={styles.suggestionNotice} role={currentSuggestions?.error ? 'alert' : 'status'}>
          {suggestionNotice}
          {!selected && !!offers?.excluded_links.length && <p>Część przystanków pominięto z powodu braku aktualnego szacunku dojścia.</p>}
          {currentSuggestions?.error && <button onClick={() => { resetSelection(); setSuggestionAttempt(value => value + 1) }}>Ponów wyszukiwanie</button>}
        </div>
        {offers?.outcome === 'choose_destination' && offers.directions.length > 0 && <div className={styles.destinationHints} role="group" aria-label="Dostępne kierunki">
          {offers.directions.slice(0, 3).map(item => <button key={item.query} onClick={() => changeQuery(item.query)}>{item.line} · {item.direction}</button>)}
        </div>}
        {selected && <details className={styles.explanation}><summary>Dlaczego ten kurs?</summary>
          <p>{isRecommended ? offers?.reason : 'Kurs wybrany ręcznie z propozycji.'} Dobór przy 0 min opóźnienia.</p>
          <p>Suwak ocenia wybrany kurs. Zmiana opóźnienia nie przełącza odjazdu.</p>
          <p>{offers?.limitations.join(' ')}</p>
          {offers?.excluded_links.length ? <p>Część powiązań pominięto z powodu braku aktualnego dojścia.</p> : null}
          {selected.match.kind === 'stop' && <p>Kurs zatrzymuje się dalej na przystanku {selected.match.stop_name}.</p>}
        </details>}
        {alternativesOpen && offers && <div className={styles.alternatives} role="group" aria-label="Inne kursy ZTM">
          {offers.results.map(item => <button key={`${item.link.id}:${journeyKey(item.departure)}`}
            aria-pressed={selected?.link.id === item.link.id && journeyKey(selected.departure) === journeyKey(item.departure)}
            onClick={() => {
              if (selected?.link.id === item.link.id && journeyKey(selected.departure) === journeyKey(item.departure)) {
                setAlternativesOpen(false)
                return
              }
              resetSelection()
              setChosen({ key: base, item })
            }}>
            <strong>{clock(item.departure.departure_at!)} · {item.departure.line}</strong><span>{item.departure.direction}</span>
            <span>{item.link.departure_stop.stop_name} · dojście szac. {item.link.walking_minutes} min</span>
            <span>{fullDate(item.departure.departure_at!)}</span>
          </button>)}
          {offers.has_more && <p>Zawęż wyszukiwanie, aby zobaczyć inne pasujące kursy.</p>}
        </div>}
      </CourseCard>
      <div className={`${styles.result} ${styles[state]}`} aria-busy={pending}>
        <TransitFigure margin={figureMargin} />
        <div role="status" aria-live="polite" aria-atomic="true" className={styles.resultText}>
          <p className={styles.status}>{error ? 'Nie można ocenić' : pending ? 'Przeliczanie…' : labels[state]}</p>
          <output className={styles.margin} style={{ '--value-length': margin ? margin.amount.length + 1 : 1 } as CSSProperties}
            aria-label={result ? `Zapas czasu: ${result.margin_minutes} minut` : pending ? 'Przeliczanie wyniku' : 'Brak wyniku'}>
            {margin ? <>{result!.margin_minutes > 0 ? '+' : ''}{margin.amount}<span> {margin.unit}</span></> : <span className={styles.waiting}>—</span>}
          </output>
          <p className={styles.resultHint}>{result ? `Zapas po ${link?.walking_minutes} min szacowanego dojścia` : error ? 'Odśwież propozycje lub wybierz inny kurs.'
            : pending ? 'Sprawdzamy wybrany kurs…' : !arrival ? 'Wybierz swój pociąg.' : 'Wpisz cel lub wybierz kierunek.'}</p>
        </div>
      </div>
      <div className={styles.delayControl}>
        <div className={styles.sliderHeading}><label htmlFor={`${id}-delay`}>Opóźnienie pociągu SKM</label><output htmlFor={`${id}-delay`}>+{delay} min</output></div>
        <div className={styles.slider}><input id={`${id}-delay`} type="range" min="0" max="30" step="1" value={delay}
          aria-valuetext={`${delay} minut symulowanego opóźnienia`} aria-describedby={`${id}-delay-source`}
          disabled={!selected} onChange={event => setDelay(Number(event.target.value))} /></div>
        <div className={styles.sliderLimits} aria-hidden="true"><span>0 min</span><span>30 min</span></div>
        <p id={`${id}-delay-source`} className={styles.delaySource}>Opóźnienie jest symulacją. Rozkład planowany.</p>
      </div>
    </div>
    {error && <div className={styles.error} role="alert"><p>{error}</p><button onClick={() => {
      resetSelection()
      setSuggestionAttempt(value => value + 1)
    }}>Odśwież propozycje</button></div>}
    <div className={styles.walkingNote}>
      <p>Rozkład {setup?.sources?.map(source => <a key={source.operator} href={source.documentation_url}
        title={`${source.attribution}. Dni kursowania ${source.service_start_date}–${source.service_end_date}.`} target="_blank" rel="noreferrer">{source.operator.toUpperCase()} </a>)}</p>
      {walking && <p>Szacowane dojście {link?.walking_minutes} min. {walking.attribution}. <a href={walking.license_url}>CC BY-SA 4.0</a>. Peron SKM nie jest określony.</p>}
    </div>
    {picker && setup?.link && setup.sources && <JourneyPicker leg="arrival" linkId={setup.link.id} stop={setup.link.arrival_stop}
      source={setup.sources.find(source => source.operator === 'skm')!} selected={arrival}
      onClose={() => setPicker(false)} onChoose={journey => {
        if (!arrival || journeyKey(arrival) !== journeyKey(journey) || arrival.arrival_at !== journey.arrival_at) {
          resetSelection()
          setArrival(journey)
        }
        setPicker(false)
      }} />}
  </section>
}
