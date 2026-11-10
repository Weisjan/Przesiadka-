import { useEffect, useRef, useState } from 'react'
import { request } from './api'
import type { Scenario } from './types'
import ScenarioForm from './ScenarioForm'
import TransferAnalysis from './TransferAnalysis'
import StatusFace from './StatusFace'
import styles from './Scenarios.module.css'

export default function Scenarios() {
  const [scenarios, setScenarios] = useState<Scenario[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [editor, setEditor] = useState<Scenario | 'new' | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [editing, setEditing] = useState(false)
  const deleteDialog = useRef<HTMLDialogElement>(null)
  const addButton = useRef<HTMLButtonElement>(null)
  const selected = scenarios.find(item => item.id === selectedId) ?? scenarios[0]
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError('')
    request<Scenario[]>('/api/scenarios', { signal: controller.signal })
      .then(data => { if (!controller.signal.aborted) setScenarios(data) })
      .catch((error: Error) => { if (!controller.signal.aborted) setError(error.message) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [attempt])
  useEffect(() => {
    if (!deleteOpen) return
    const trigger = document.activeElement as HTMLElement | null
    const modal = deleteDialog.current
    modal?.showModal()
    return () => { modal?.close(); if (trigger?.isConnected) trigger.focus() }
  }, [deleteOpen])

  async function openEditor() {
    if (!selected) return
    setEditing(true)
    setError('')
    try { setEditor(await request<Scenario>(`/api/scenarios/${selected.id}`)) }
    catch (error) { setError((error as Error).message) }
    finally { setEditing(false) }
  }
  async function deleteScenario() {
    if (!selected) return
    setDeleting(true)
    setError('')
    try {
      await request<void>(`/api/scenarios/${selected.id}`, { method: 'DELETE' })
      setScenarios(current => current.filter(item => item.id !== selected.id))
      setNotice('Usunięto scenariusz.')
      deleteDialog.current?.close()
      setDeleteOpen(false)
      addButton.current?.focus()
    } catch (error) { setError((error as Error).message) }
    finally { setDeleting(false) }
  }
  return <section className={styles.section} aria-label="Analiza przesiadki">
    <div className={styles.toolbar}>
      <label className={styles.selector}>Twój scenariusz
        <select aria-label="Wybierz scenariusz" value={selected?.id ?? ''} disabled={loading || !scenarios.length || editing}
          onChange={event => { setSelectedId(Number(event.target.value)); setNotice(''); setError('') }}>
          {!scenarios.length && <option value="">{loading ? 'Wczytywanie…' : 'Brak scenariuszy'}</option>}
          {scenarios.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select>
      </label>
      <button ref={addButton} className={styles.primary} disabled={loading || editing} onClick={() => setEditor('new')}>Dodaj scenariusz</button>
    </div>
    <p className={styles.notice} role="status">{notice}</p>
    {error && !deleteOpen && <div className={styles.error} role="alert"><p>{error}</p><button onClick={() => setAttempt(value => value + 1)}>Odśwież listę</button></div>}
    {loading ? <div className={styles.empty} aria-busy="true"><StatusFace emotion="loading" /><h1>Wczytywanie scenariuszy…</h1></div>
      : selected ? <>
        <TransferAnalysis key={selected.id} scenario={selected} />
        <div className={styles.actions}>
          <button disabled={editing} onClick={() => void openEditor()}>{editing ? 'Wczytywanie…' : 'Edytuj scenariusz'}</button>
          <button className={styles.danger} disabled={editing} onClick={() => { setError(''); setDeleteOpen(true) }}>Usuń scenariusz</button>
        </div>
      </> : !error && <div className={styles.empty}>
        <span className={styles.emptyRoute} aria-hidden="true">○ ───── ◇ ───── ○</span>
        <h1>Każda przesiadka<br />zaczyna się od planu.</h1>
        <p>Dodaj godziny przyjazdu i odjazdu.<br />Sprawdź, ile czasu zostaje na przesiadkę.</p>
        <button className={styles.primary} onClick={() => setEditor('new')}>Dodaj pierwszą przesiadkę</button>
      </div>}
    {editor !== null && <ScenarioForm scenario={editor === 'new' ? undefined : editor} onClose={() => setEditor(null)} onSaved={saved => {
      setScenarios(current => editor === 'new' ? [saved, ...current] : current.map(item => item.id === saved.id ? saved : item))
      setSelectedId(saved.id)
      setNotice(editor === 'new' ? 'Dodano scenariusz.' : 'Zapisano zmiany scenariusza.')
      setError('')
      setEditor(null)
    }} />}
    {deleteOpen && <dialog ref={deleteDialog} className={styles.dialog} aria-labelledby="delete-title"
      onCancel={event => { if (deleting) event.preventDefault(); else setDeleteOpen(false) }}>
      <h2 id="delete-title">Usunąć scenariusz?</h2>
      <p>„{selected?.name}” zostanie usunięty. Tej operacji nie można cofnąć.</p>
      {error && <p className={styles.error} role="alert">{error}</p>}
      <div className={styles.actions}>
        <button autoFocus disabled={deleting} onClick={() => { deleteDialog.current?.close(); setDeleteOpen(false) }}>Anuluj</button>
        <button className={styles.danger} disabled={deleting} onClick={() => void deleteScenario()}>{deleting ? 'Usuwanie…' : 'Usuń scenariusz'}</button>
      </div>
    </dialog>}
  </section>
}
