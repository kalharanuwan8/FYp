import { useEffect, useState } from 'react';

/**
 * 10 s calibration screen: look at the lesson so the pose baseline can lock.
 * Parent should set calibrating=true on the monitoring hook while this is open.
 */
const DURATION_SEC = 10;

export default function CalibrationOverlay({ open, onDone, onRetry, faceFound = true }) {
  const [left, setLeft] = useState(DURATION_SEC);

  useEffect(() => {
    if (!open) return undefined;
    setLeft(DURATION_SEC);
    const started = Date.now();
    const id = setInterval(() => {
      const remain = Math.max(0, DURATION_SEC - (Date.now() - started) / 1000);
      setLeft(remain);
      if (remain <= 0) {
        clearInterval(id);
        if (faceFound) onDone?.();
        else onRetry?.();
      }
    }, 100);
    return () => clearInterval(id);
  }, [open, faceFound, onDone, onRetry]);

  if (!open) return null;

  const progress = 1 - left / DURATION_SEC;

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 80,
        display: 'grid',
        placeItems: 'center',
        background: 'rgba(12, 18, 28, 0.72)',
        color: '#f4f7fb',
        fontFamily: 'Georgia, "Times New Roman", serif',
      }}
    >
      <div style={{ textAlign: 'center', maxWidth: 420, padding: 24 }}>
        <svg width="96" height="96" viewBox="0 0 96 96" aria-hidden>
          <circle cx="48" cy="48" r="40" fill="none" stroke="rgba(255,255,255,0.2)" strokeWidth="6" />
          <circle
            cx="48"
            cy="48"
            r="40"
            fill="none"
            stroke="#7ec8a3"
            strokeWidth="6"
            strokeDasharray={`${2 * Math.PI * 40}`}
            strokeDashoffset={`${2 * Math.PI * 40 * (1 - progress)}`}
            strokeLinecap="round"
            transform="rotate(-90 48 48)"
          />
        </svg>
        <h2 style={{ fontSize: '1.6rem', margin: '1rem 0 0.4rem' }}>Look at the lesson</h2>
        <p style={{ opacity: 0.85, lineHeight: 1.45 }}>
          Hold still for a few seconds so we can learn your usual head position.
          {!faceFound ? ' Face not found — we will retry.' : ''}
        </p>
        <p style={{ fontVariantNumeric: 'tabular-nums', marginTop: 12 }}>{left.toFixed(1)}s</p>
      </div>
    </div>
  );
}
