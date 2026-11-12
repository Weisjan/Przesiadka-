import styles from './TransitFigure.module.css'

export type FigureState = 'success' | 'edge' | 'missed' | 'idle' | 'loading' | 'error'

export default function TransitFigure({ state }: { state: FigureState }) {
  const running = state === 'edge'
  const walking = state === 'success'
  return <svg className={`${styles.figure} ${styles[state]}`} data-figure-state={state}
    viewBox="0 0 160 180" fill="none" aria-hidden="true" focusable="false">
    <circle cx={running ? 112 : walking ? 88 : 82} cy={running ? 28 : 25} r="16" fill="currentColor" />
    {running ? <g stroke="currentColor" strokeWidth="16" strokeLinecap="round" strokeLinejoin="round">
      <path d="M91 55 63 91 88 115 82 147" />
      <path className={styles.backLeg} d="M64 92 39 115 15 115" />
      <path d="M92 56 111 74 133 53" />
      <path className={styles.arm} d="M90 56 65 53 46 76" />
      <path d="M91 56 66 91" strokeWidth="23" />
    </g> : walking ? <g stroke="currentColor" strokeWidth="13" strokeLinecap="round" strokeLinejoin="round">
      <path d="M82 55 73 97" strokeWidth="20" />
      <path className={styles.frontLeg} d="M73 96 64 125 46 153" />
      <path className={styles.backLeg} d="M75 96 90 126 112 146" />
      <path className={styles.arm} d="M81 57 99 81 116 82" />
      <path d="M78 57 60 78 48 85" />
    </g> : <g stroke="currentColor" strokeWidth="13" strokeLinecap="round" strokeLinejoin="round">
      <path d="M82 57 77 99" strokeWidth="22" />
      <path d="M77 99 70 128 72 155M81 99 93 126 88 153" />
      <path d="M79 57 63 76 61 102M87 57 99 77 97 97" />
    </g>}
  </svg>
}
