import { useEffect, useRef } from 'react'
import walking from './assets/zielony_marsz.svg?raw'
import running from './assets/czerwony_bieg.svg?raw'
import standing from './assets/szary_stoi.svg?raw'
import { figureState } from './formatting'
import styles from './TransitFigure.module.css'

const figures = { success: { __html: walking }, edge: { __html: running }, missed: { __html: standing } }

export default function TransitFigure({ margin }: { margin: number | null }) {
  const state = figureState(margin)
  const container = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)')
    function updateMotion() {
      container.current?.querySelectorAll('svg').forEach(svg => {
        if (preference.matches || state === 'idle') {
          svg.pauseAnimations()
          svg.setCurrentTime(0)
        } else svg.unpauseAnimations()
      })
    }
    updateMotion()
    preference.addEventListener('change', updateMotion)
    return () => preference.removeEventListener('change', updateMotion)
  }, [state])

  return <div ref={container} className={styles.figure} data-figure-state={state} aria-hidden="true">
    {Object.entries(figures).map(([name, markup]) => <div key={name} data-model={name}
      className={`${styles.model} ${name === state ? styles.visible : ''} ${state === 'idle' && name === 'missed' ? styles.neutral : ''}`}
      // These reviewed local assets keep their original native SMIL animations.
      dangerouslySetInnerHTML={markup} />)}
  </div>
}
