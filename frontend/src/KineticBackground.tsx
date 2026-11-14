import { useId } from 'react'
import type { CSSProperties } from 'react'
import styles from './KineticBackground.module.css'

const strands = Array.from({ length: 28 }, (_, index) => ({
  x: 8 + index * 14,
  top: 66 + Math.sin(index * .2) * 50,
  bottom: 220 + Math.sin(index * .2 + 1.2) * 92,
  phase: `${-index * .47}s`,
}))

function Ribbon() {
  const spectrum = useId()
  return <svg className={styles.ribbon} viewBox="0 0 400 360" fill="none" focusable="false">
    <defs><linearGradient id={spectrum} x1="220" y1="0" x2="400" y2="0" gradientUnits="userSpaceOnUse">
      <stop stopColor="#FF786C" /><stop offset=".3" stopColor="#E9D66B" />
      <stop offset=".65" stopColor="#73D7D2" /><stop offset="1" stopColor="#8782FF" />
    </linearGradient></defs>
    {strands.map((strand, index) => <g key={index} className={styles.strand}
      style={{ '--phase': strand.phase } as CSSProperties}>
      <path className={styles.thread} d={`M${strand.x} ${strand.top}V${strand.bottom}`} />
      <path className={styles.illumination} d={`M${strand.x} ${strand.top}V${strand.bottom}`}
        stroke={`url(#${spectrum})`} />
    </g>)}
  </svg>
}

export default function KineticBackground() {
  return <div className={styles.scene} aria-hidden="true" data-kinetic-background>
    <div className={`${styles.field} ${styles.upperLeft}`}><Ribbon /></div>
    <div className={`${styles.field} ${styles.upperRight}`}><Ribbon /></div>
    <div className={`${styles.field} ${styles.lowerLeft}`}><Ribbon /></div>
    <div className={`${styles.field} ${styles.lowerRight}`}><Ribbon /></div>
  </div>
}
