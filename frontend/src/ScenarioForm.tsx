import { useEffect, useId, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { request } from './api'
import { dateTimeOptions, emptyDateTime, fromIso, toIso } from './dates'
import type { LocalDateTime } from './dates'
import type { Scenario, ScenarioInput } from './types'
import styles from './Scenarios.module.css'

const textFields = [
  ['name', 'Nazwa scenariusza', 120], ['interchange', 'Węzeł przesiadkowy', 120],
  ['arrival_line', 'Linia przyjazdowa', 80], ['departure_line', 'Linia odjazdowa', 80],
  ['direction', 'Kierunek linii odjazdowej', 120],
] as const

function DateTimeField({ label, value, onChange }: {
  label: string
  value: LocalDateTime
  onChange: (value: LocalDateTime) => void
}) {
  const id = useId()
  const options = dateTimeOptions(value)
  const gap = value.date && value.time && options.length === 0
  return <fieldset className={styles.dateGroup}>
    <legend>{label}</legend>
    <div className={styles.dateRow}>
      <label htmlFor={`${id}-date`}>Data<input id={`${id}-date`} aria-label={`${label}: data`} type="date" min="0001-01-01" max="9999-12-31" required
        value={value.date} aria-describedby={`${id}-help`} aria-invalid={!!gap}
        onChange={event => onChange({ ...value, date: event.target.value, offset: '' })} /></label>
      <label htmlFor={`${id}-time`}>Godzina<input id={`${id}-time`} aria-label={`${label}: godzina`} type="time" step="60" required
        value={value.time} aria-describedby={`${id}-help`} aria-invalid={!!gap}
        onChange={event => onChange({ ...value, time: event.target.value, offset: '' })} /></label>
    </div>
    <p id={`${id}-help`} className={gap ? styles.fieldError : styles.hint}>
      {gap ? 'Ta godzina nie istnieje w Warszawie przy zmianie czasu.' : 'Czas lokalny Warszawy. Dla kursu po północy wybierz następny dzień.'}
    </p>
    {options.length > 1 && <label>Godzina występuje dwukrotnie
      <select aria-label={`${label}: wystąpienie godziny`} required value={value.offset} onChange={event => onChange({ ...value, offset: event.target.value })}>
        <option value="">Wybierz wystąpienie</option>
        {options.map((option, index) => <option key={option} value={option.slice(-6)}>{index === 0 ? 'Pierwsze' : 'Drugie'} (UTC{option.slice(-6)})</option>)}
      </select>
    </label>}
  </fieldset>
}

export default function ScenarioForm({ scenario, onClose, onSaved }: {
  scenario?: Scenario
  onClose: () => void
  onSaved: (scenario: Scenario) => void
}) {
  const [fields, setFields] = useState({
    name: scenario?.name ?? '', interchange: scenario?.interchange ?? '',
    arrival_line: scenario?.arrival_line ?? '', departure_line: scenario?.departure_line ?? '',
    direction: scenario?.direction ?? '',
  })
  const [arrival, setArrival] = useState(scenario ? fromIso(scenario.arrival_at) : emptyDateTime)
  const [departure, setDeparture] = useState(scenario ? fromIso(scenario.departure_at) : emptyDateTime)
  const [walking, setWalking] = useState(String(scenario?.walking_minutes ?? 3))
  const [next, setNext] = useState<LocalDateTime[]>(scenario?.next_departures.map(fromIso) ?? [])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const dialog = useRef<HTMLDialogElement>(null)
  const errorSummary = useRef<HTMLParagraphElement>(null)
  useEffect(() => {
    const trigger = document.activeElement as HTMLElement | null
    const modal = dialog.current
    modal?.showModal()
    modal?.querySelector<HTMLInputElement>('input[name="name"]')?.focus()
    return () => { modal?.close(); if (trigger?.isConnected) trigger.focus() }
  }, [])
  useEffect(() => { if (error) errorSummary.current?.focus() }, [error])

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    let payload: ScenarioInput
    try {
      if (Object.values(fields).some(value => !value.trim())) throw new Error('Wypełnij wszystkie wymagane pola.')
      const minutes = Number(walking)
      if (!walking.trim() || !Number.isInteger(minutes) || minutes < 0 || minutes > 1440) throw new Error('Czas dojścia: podaj liczbę całkowitą od 0 do 1440.')
      payload = { ...fields, arrival_at: toIso(arrival), departure_at: toIso(departure), walking_minutes: minutes, next_departures: next.map(toIso) }
      const instants = payload.next_departures.map(value => Date.parse(value))
      if (instants.some((instant, index) => instant <= (index ? instants[index - 1] : Date.parse(payload.departure_at)))) {
        throw new Error('Kolejne odjazdy muszą być po pierwotnym kursie, rosnąco i bez powtórzeń.')
      }
    } catch (error) { setError((error as Error).message); return }
    setBusy(true)
    try {
      const saved = await request<Scenario>(scenario ? `/api/scenarios/${scenario.id}` : '/api/scenarios', {
        method: scenario ? 'PUT' : 'POST', body: JSON.stringify(payload),
      })
      onSaved(saved)
    } catch (error) { setError((error as Error).message) }
    finally { setBusy(false) }
  }

  return <dialog ref={dialog} className={`${styles.dialog} ${styles.editor}`} aria-labelledby="form-title"
    onCancel={event => { if (busy) event.preventDefault(); else onClose() }}>
    <form onSubmit={event => void save(event)}>
      <div className={styles.dialogHeading}><h2 id="form-title">{scenario ? 'Edytuj scenariusz' : 'Nowy scenariusz'}</h2>
        <button type="button" aria-label="Zamknij formularz" disabled={busy} onClick={onClose}>Zamknij</button>
      </div>
      <p className={styles.hint}>Wszystkie pola poza kolejnymi odjazdami są wymagane.</p>
      <fieldset className={styles.formFields} disabled={busy}>
        <legend className={styles.srOnly}>Dane scenariusza</legend>
        <div className={styles.fieldGrid}>
          {textFields.map(([field, label, maxLength]) => <label key={field} className={field === 'name' || field === 'direction' ? styles.fullWidth : undefined}>
            {label}<input name={field} autoFocus={field === 'name'} required maxLength={maxLength} value={fields[field]}
              onChange={event => setFields(current => ({ ...current, [field]: event.target.value }))} />
          </label>)}
        </div>
        <DateTimeField label="Przyjazd" value={arrival} onChange={setArrival} />
        <DateTimeField label="Odjazd" value={departure} onChange={setDeparture} />
        <label className={styles.walking}>Czas dojścia w minutach<input type="number" min="0" max="1440" step="1" required value={walking} onChange={event => setWalking(event.target.value)} /></label>
        <div className={styles.nextHeading}><h3>Kolejne odjazdy</h3><span>Opcjonalnie</span></div>
        <p className={styles.hint}>Ta sama linia i kierunek. Dodaj chronologicznie, po pierwotnym kursie.</p>
        {next.map((value, index) => <div key={index} className={styles.nextRow}>
          <DateTimeField label={`Kolejny odjazd ${index + 1}`} value={value} onChange={changed => setNext(current => current.map((item, position) => position === index ? changed : item))} />
          <button type="button" className={styles.danger} aria-label={`Usuń kolejny odjazd ${index + 1}`} onClick={() => setNext(current => current.filter((_, position) => position !== index))}>Usuń</button>
        </div>)}
        <button type="button" disabled={next.length >= 100} onClick={() => setNext(current => [...current, { ...emptyDateTime(), date: departure.date }])}>Dodaj kolejny odjazd</button>
      </fieldset>
      {error && <p ref={errorSummary} tabIndex={-1} className={styles.error} role="alert">{error}</p>}
      <div className={styles.formActions}>
        <button type="button" disabled={busy} onClick={onClose}>Anuluj</button>
        <button className={styles.primary} type="submit" disabled={busy}>{busy ? 'Zapisywanie…' : 'Zapisz scenariusz'}</button>
      </div>
    </form>
  </dialog>
}
