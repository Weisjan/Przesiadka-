import { useEffect, useState } from 'react'
import { request } from './api'
import Scenarios from './Scenarios'
import Transit from './Transit'
import styles from './App.module.css'

export default function App() {
  const [health, setHealth] = useState<'loading' | 'success' | 'error'>('loading')
  const [attempt, setAttempt] = useState(0)
  const [view, setView] = useState<'transit' | 'scenarios'>('transit')
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
      <nav className={styles.nav} aria-label="Widoki aplikacji">
        <button aria-current={view === 'transit' ? 'page' : undefined} onClick={() => setView('transit')}>Rozkłady</button>
        <button aria-current={view === 'scenarios' ? 'page' : undefined} onClick={() => setView('scenarios')}>Scenariusze</button>
      </nav>
    </header>
    <main id="main"><div hidden={view !== 'transit'}><Transit /></div>{view === 'scenarios' && <Scenarios />}</main>
    <footer className={styles.footer}>
      <p>Przesiadka+ / lokalne MVP / Gdańsk</p>
      <div role="status">
        {health === 'loading' ? 'Sprawdzanie połączenia…' : health === 'success' ? 'Połączenie działa' : 'Brak połączenia z API'}
        {health === 'error' && <button onClick={() => setAttempt(value => value + 1)}>Sprawdź ponownie</button>}
      </div>
    </footer>
  </div>
}
