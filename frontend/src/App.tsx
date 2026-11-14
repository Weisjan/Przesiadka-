import Transit from './Transit'
import KineticBackground from './KineticBackground'
import styles from './App.module.css'

export default function App() {
  return <div className={styles.shell}>
    <KineticBackground />
    <div className={styles.page}>
      <a className={styles.skip} href="#main">Przejdź do treści</a>
      <header className={styles.header}><h1 className={styles.brand}>Przesiadka<span>+</span></h1></header>
      <main id="main"><Transit /></main>
    </div>
  </div>
}
