import { useEffect, useState } from 'react'
import { request } from './api'
import Scenarios from './Scenarios'
import styles from './App.module.css'

export default function App() {
  const [health, setHealth] = useState<'loading' | 'success' | 'error'>('loading')
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setHealth('loading')
    request<{ status: string }>('/api/health', { signal: controller.signal })
      .then(data => { if (!controller.signal.aborted) setHealth(data.status === 'ok' ? 'success' : 'error') })
      .catch(() => { if (!controller.signal.aborted) setHealth('error') })
    return () => controller.abort()
  }, [attempt])
  return <div className={styles.page}>
    <a className={styles.skip} href="#main">Przejdź do treści</a>
    <header className={styles.header}>
      <a className={styles.brand} href="#main">Przesiadka<span>+</span></a>
      <span>Gdańsk <span className={styles.separator}>/</span> demo lokalne</span>
    </header>
    <main id="main"><Scenarios /></main>
    <footer className={styles.footer}>
      <p>Twój rozkład. Spokojniejsza przesiadka.</p>
      <div role="status">
        {health === 'loading' ? 'Sprawdzanie połączenia…' : health === 'success' ? 'Połączenie działa' : 'Brak połączenia z API'}
        {health === 'error' && <button onClick={() => setAttempt(value => value + 1)}>Sprawdź ponownie</button>}
      </div>
    </footer>
  </div>
}
