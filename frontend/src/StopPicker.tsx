import { useEffect, useId, useRef, useState } from 'react'
import { request } from './api'
import { readStopGroups } from './plannerData'
import type { StopGroup } from './plannerData'
import styles from './Planner.module.css'

export default function StopPicker({ label, operator, onChange, initialValue }: {
  label: string; operator: 'skm' | 'ztm'; onChange: (group: StopGroup | null) => void; initialValue?: StopGroup | null
}) {
  const id = useId()
  const [query, setQuery] = useState(initialValue?.name ?? '')
  const [attempt, setAttempt] = useState(0)
  const selected = useRef(initialValue ? JSON.stringify(initialValue.stops.map(stop => stop.stop_id)) : '')
  const [reply, setReply] = useState<{ query: string; groups?: StopGroup[]; more?: boolean; error?: string } | null>(null)
  const current = reply?.query === query ? reply : null
  useEffect(() => {
    const controller = new AbortController()
    let disposed = false
    const timer = window.setTimeout(() => {
      request<unknown>(`/api/transit/journeys/stops?${new URLSearchParams({ operator, query, limit: '100' })}`, { signal: controller.signal })
        .then(data => readStopGroups(data, operator)).then(data => {
          if (disposed) return
          setReply({ query, groups: data.groups, more: data.has_more })
          const exact = data.groups.filter(group => group.name.toLocaleLowerCase('pl') === query.trim().toLocaleLowerCase('pl'))
          if (exact.length === 1) {
            const identity = JSON.stringify(exact[0].stops.map(stop => stop.stop_id))
            if (identity !== selected.current) { selected.current = identity; onChange(exact[0]) }
          }
        }).catch((error: Error) => { if (!disposed) setReply({ query, error: error.message }) })
    }, 180)
    return () => { disposed = true; controller.abort(); window.clearTimeout(timer) }
  }, [query, operator, attempt])
  return <div className={styles.stopPicker}>
    <label htmlFor={id}>{label}</label>
    <input id={id} type="search" required autoComplete="off" maxLength={120} list={`${id}-options`} value={query}
      placeholder={operator === 'skm' ? 'Wpisz stację SKM' : 'Wpisz nazwę przystanku ZTM'} aria-describedby={`${id}-hint`}
      onChange={event => {
        const text = event.target.value
        setQuery(text)
        const group = current?.groups?.find(group => group.name === text) ?? null
        selected.current = group ? JSON.stringify(group.stops.map(stop => stop.stop_id)) : ''
        onChange(group)
      }} />
    <datalist id={`${id}-options`}>{current?.groups?.map(group => <option key={group.name} value={group.name} />)}</datalist>
    <div id={`${id}-hint`} className={styles.fieldHint} role={current?.error ? 'alert' : 'status'}>
      {current?.error ? <>{current.error} <button type="button" onClick={() => setAttempt(x => x + 1)}>Ponów listę</button></>
        : !current ? 'Wyszukiwanie przystanków…' : !current.groups?.length ? 'Brak przystanku o tej nazwie. Spróbuj pełnej nazwy.'
          : current.more ? 'Wpisz dokładniejszą nazwę, aby zawęzić listę.' : 'Wybierz nazwę z podpowiedzi.'}
    </div>
  </div>
}
