import styles from './StatusFace.module.css'

export type FaceEmotion = 'success' | 'edge' | 'missed' | 'loading' | 'error' | 'unavailable'

interface StatusFaceProps {
  emotion: FaceEmotion
}

const mouths: Record<FaceEmotion, string> = {
  success: 'M9 18h3v3h8v-3h3v4h-3v2h-8v-2H9z',
  edge: 'M10 21h12v2H10z M12 18h8v1h-8z',
  missed: 'M9 22h3v-3h8v3h3v2h-5v-3h-4v3H9z',
  loading: 'M11 21h10v2H11z',
  error: 'M10 21h5v-2h7v2h-5v2h-7z',
  unavailable: 'M8 24v-4h4v-3h8v3h4v4h-3v-3h-3v-2h-4v2h-3v3z',
}

export default function StatusFace({ emotion }: StatusFaceProps) {
  return <svg key={emotion} className={`${styles.face} ${styles[emotion]}`} data-emotion={emotion}
    width={104} height={104} viewBox="0 0 32 32" fill="currentColor" shapeRendering="crispEdges" aria-hidden="true" focusable="false">
    <path className={styles.frame} d="M8 2h16v2h4v4h2v16h-2v4h-4v2H8v-2H4v-4H2V8h2V4h4z M8 4v2H6v2H4v16h2v2h2v2h16v-2h2v-2h2V8h-2V6h-2V4z" fillRule="evenodd" />
    <g className={styles.eyes}>
      {emotion === 'success' ? <path d="M8 12h2v-2h3v2h2v2h-3v-2h-1v2H8z M18 12h2v-2h3v2h2v2h-3v-2h-1v2h-3z" />
        : <><path d="M9 12h4v4H9z M19 12h4v4h-4z" />
          {emotion === 'edge' && <path d="M8 8h3v2h3v1h-3V9H8z M18 10h3V8h3v1h-3v2h-3z" />}
          {(emotion === 'missed' || emotion === 'unavailable') && <path d="M8 10h3V8h3v2h-3v2H8z M18 8h3v2h3v2h-3v-2h-3z" />}
          {emotion === 'error' && <path d="M8 8h6v2H8z M20 6h2v2h3v2h-3V8h-2z" />}</>}
    </g>
    <path d={mouths[emotion]} />
    {emotion === 'edge' && <path className={styles.drop} d="M27 6h2v3h2v4h-2v1h-3v-2h-1V9h2z" />}
    {emotion === 'unavailable' && <path className={styles.drop} d="M23 17h2v4h1v3h-4v-3h1z" />}
  </svg>
}
