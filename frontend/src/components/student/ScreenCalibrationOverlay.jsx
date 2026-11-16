import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * PLAN 5 / PLAN 8 — 9-point screen calibration.
 *
 * Reads the display geometry, (preferably) goes fullscreen so the content area is the
 * screen, then shows nine "look at the star" dots in a 3×3 grid (5 % inset) for ~2 s
 * each: top right/centre/left, mid left/centre/right, bottom left/centre/right.
 * After the first 600 ms of each dot (eye travel time) frames are tagged with
 * `calib_target` {x, y} in 0..1 screen coordinates via `setCalibrationTarget`.
 * When the last dot ends, `finishCalibration` (from useMonitoringSession) flushes
 * the frames and resolves with the backend result.
 *
 * After the nine stars comes a ~4 s HEAD phase — eyes stay on the centre star while
 * the head slowly turns left/right and nods. Those frames are tagged with the
 * centre target so the mapper learns how the eyes compensate for head angle. The
 * success screen offers "Test it" (`onTest`), which opens the guided GazeSelfTest.
 *
 * Parent must call `setCalibrating(true)` on the monitoring hook while this is open
 * (that queues `calibration_phase: "start"`); `key` it to restart on retry.
 */
const DOT_MS = 2000;
const SETTLE_MS = 600;
const INSET = 0.05;
const HEAD_MS = 4000;
const DONE_DELAY_MS = 5000; // success screen auto-closes unless the student taps "Test it"
const CENTRE = { x: 0.5, y: 0.5 };

// 3×3 grid: top right/centre/left, mid left/centre/right, bottom left/centre/right
const DOTS = [
  { x: 1 - INSET, y: INSET },
  { x: 0.5, y: INSET },
  { x: INSET, y: INSET },
  { x: INSET, y: 0.5 },
  { x: 0.5, y: 0.5 },
  { x: 1 - INSET, y: 0.5 },
  { x: INSET, y: 1 - INSET },
  { x: 0.5, y: 1 - INSET },
  { x: 1 - INSET, y: 1 - INSET },
];

const clamp01 = (v) => Math.min(1, Math.max(0, v));

function readDisplay() {
  const scr = window.screen || {};
  return {
    w: scr.width || window.innerWidth,
    h: scr.height || window.innerHeight,
    innerW: window.innerWidth,
    innerH: window.innerHeight,
    dpr: window.devicePixelRatio || 1,
    orientation: scr.orientation?.type || (scr.width >= scr.height ? 'landscape' : 'portrait'),
  };
}

/** Viewport-normalised dot position → screen-normalised target. */
function toScreenTarget(dot) {
  const inFullscreen = Boolean(document.fullscreenElement || document.webkitFullscreenElement);
  const scr = window.screen || {};
  if (inFullscreen || !scr.width || !scr.height) return { x: dot.x, y: dot.y };
  // Windowed fallback: place the viewport inside the screen (browser chrome sits on top).
  const sideChrome = Math.max(0, (window.outerWidth - window.innerWidth) / 2);
  const topChrome = Math.max(0, window.outerHeight - window.innerHeight - sideChrome);
  const left = (window.screenX || 0) + sideChrome;
  const top = (window.screenY || 0) + topChrome;
  return {
    x: clamp01((left + dot.x * window.innerWidth) / scr.width),
    y: clamp01((top + dot.y * window.innerHeight) / scr.height),
  };
}

async function requestFullscreenOnPage() {
  if (document.fullscreenElement || document.webkitFullscreenElement) return;
  const el = document.documentElement;
  try {
    if (el.requestFullscreen) await el.requestFullscreen();
    else if (el.webkitRequestFullscreen) await el.webkitRequestFullscreen();
  } catch {
    /* Fullscreen is preferred, not required. */
  }
}

function exitPageFullscreen() {
  // Only undo the fullscreen this overlay started (page-level), never the video stage's.
  if (document.fullscreenElement !== document.documentElement) return;
  try {
    const p = document.exitFullscreen?.();
    if (p && typeof p.catch === 'function') p.catch(() => {});
  } catch {
    /* best-effort */
  }
}

export default function ScreenCalibrationOverlay({
  open,
  setCalibrationTarget,
  finishCalibration,
  onDone,
  onRetry,
  onTest,
  faceFound = true,
}) {
  // 'intro' → 'dots' → 'head' → 'finishing' → 'ok' | 'fail'
  const [stage, setStage] = useState('intro');
  const [dotIndex, setDotIndex] = useState(0);
  const [display, setDisplay] = useState(() => readDisplay());
  const [failReason, setFailReason] = useState('eyes');
  const startedRef = useRef(false);
  const doneTimerRef = useRef(null);
  const resultRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onResize = () => setDisplay(readDisplay());
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [open]);

  const runFinish = useCallback(async () => {
    setStage('finishing');
    let result = null;
    try {
      result = await finishCalibration?.();
    } catch (err) {
      console.warn('Calibration finish failed:', err);
    }
    if (result && result.ok) {
      resultRef.current = result;
      setStage('ok');
      doneTimerRef.current = setTimeout(() => {
        exitPageFullscreen();
        onDone?.(result);
      }, DONE_DELAY_MS);
    } else {
      setFailReason(result ? 'eyes' : 'server');
      setStage('fail');
    }
  }, [finishCalibration, onDone]);

  const handleStart = useCallback(async () => {
    if (startedRef.current) return;
    startedRef.current = true;
    await requestFullscreenOnPage();
    setDisplay(readDisplay());
    setDotIndex(0);
    setStage('dots');
  }, []);

  // Dot sequencer: one timer drives dot index + target tagging.
  useEffect(() => {
    if (!open || stage !== 'dots') return undefined;
    const t0 = performance.now();
    let currentIdx = -1;
    let tagged = false;
    const id = setInterval(() => {
      const elapsed = performance.now() - t0;
      const idx = Math.floor(elapsed / DOT_MS);
      if (idx >= DOTS.length) {
        clearInterval(id);
        setCalibrationTarget?.(null);
        setStage('head');
        return;
      }
      if (idx !== currentIdx) {
        currentIdx = idx;
        tagged = false;
        setCalibrationTarget?.(null); // no tagging while the eyes travel
        setDotIndex(idx);
      }
      if (!tagged && elapsed - idx * DOT_MS >= SETTLE_MS) {
        tagged = true;
        setCalibrationTarget?.(toScreenTarget(DOTS[idx]));
      }
    }, 50);
    return () => {
      clearInterval(id);
      setCalibrationTarget?.(null);
    };
  }, [open, stage, setCalibrationTarget]);

  // PLAN 8 head phase: eyes on the centre star, head turns + nods; frames tagged centre.
  useEffect(() => {
    if (!open || stage !== 'head') return undefined;
    const settleId = setTimeout(() => {
      setCalibrationTarget?.(toScreenTarget(CENTRE));
    }, SETTLE_MS);
    const endId = setTimeout(() => {
      setCalibrationTarget?.(null);
      runFinish();
    }, HEAD_MS);
    return () => {
      clearTimeout(settleId);
      clearTimeout(endId);
      setCalibrationTarget?.(null);
    };
  }, [open, stage, setCalibrationTarget, runFinish]);

  const handleDone = useCallback(() => {
    if (doneTimerRef.current) clearTimeout(doneTimerRef.current);
    doneTimerRef.current = null;
    exitPageFullscreen();
    onDone?.(resultRef.current);
  }, [onDone]);

  const handleTest = useCallback(() => {
    if (doneTimerRef.current) clearTimeout(doneTimerRef.current);
    doneTimerRef.current = null;
    // Stay fullscreen: the self-test measures looking past the real screen edges.
    onDone?.(resultRef.current);
    onTest?.();
  }, [onDone, onTest]);

  useEffect(
    () => () => {
      if (doneTimerRef.current) clearTimeout(doneTimerRef.current);
    },
    []
  );

  if (!open) return null;

  const dot = DOTS[Math.min(dotIndex, DOTS.length - 1)];

  const panel = {
    textAlign: 'center',
    maxWidth: 460,
    padding: 24,
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Screen calibration"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 90,
        background: 'rgba(8, 12, 20, 0.94)',
        color: '#f4f7fb',
        fontFamily: 'Georgia, "Times New Roman", serif',
        display: 'grid',
        placeItems: 'center',
      }}
    >
      <style>{`
        @keyframes calib-ring { from { transform: translate(-50%, -50%) scale(3.2); opacity: .25; }
                                to   { transform: translate(-50%, -50%) scale(1);   opacity: 1; } }
        @media (prefers-reduced-motion: reduce) { .calib-ring { animation: none !important; } }
      `}</style>

      {stage === 'intro' && (
        <div style={panel}>
          <h2 style={{ fontSize: '1.6rem', margin: '0 0 0.6rem' }}>Let&apos;s map your screen</h2>
          <p style={{ opacity: 0.85, lineHeight: 1.5 }}>
            Nine stars will appear, one after another. Keep your head still and look straight at
            each star until it moves. Then keep your eyes on the centre star while you slowly turn
            your head. It takes about 25 seconds.
          </p>
          <p style={{ opacity: 0.6, fontSize: 13, marginTop: 10 }}>
            Display {display.w}×{display.h} · window {display.innerW}×{display.innerH} ·{' '}
            {display.dpr}× · {display.orientation}
          </p>
          {!faceFound && (
            <p style={{ color: '#f0c674', marginTop: 8 }}>
              We can&apos;t see your face yet — sit with light in front of you.
            </p>
          )}
          <button
            type="button"
            onClick={handleStart}
            autoFocus
            style={{
              marginTop: 18,
              minHeight: 48,
              padding: '0 28px',
              borderRadius: 14,
              border: 'none',
              background: '#7ec8a3',
              color: '#0c121c',
              fontWeight: 700,
              fontSize: 16,
              cursor: 'pointer',
            }}
          >
            Start (goes fullscreen)
          </button>
        </div>
      )}

      {stage === 'dots' && (
        <>
          <div
            key={dotIndex}
            aria-live="polite"
            style={{
              position: 'absolute',
              left: `${dot.x * 100}%`,
              top: `${dot.y * 100}%`,
              width: 0,
              height: 0,
            }}
          >
            <div
              className="calib-ring"
              style={{
                position: 'absolute',
                left: 0,
                top: 0,
                width: 72,
                height: 72,
                borderRadius: '50%',
                border: '3px solid #7ec8a3',
                boxSizing: 'border-box',
                transform: 'translate(-50%, -50%)',
                animation: `calib-ring ${DOT_MS}ms linear forwards`,
              }}
            />
            <div
              style={{
                position: 'absolute',
                left: 0,
                top: 0,
                transform: 'translate(-50%, -52%)',
                fontSize: 30,
                lineHeight: 1,
                color: '#ffe27a',
              }}
            >
              ★
            </div>
          </div>
          <p
            style={{
              position: 'absolute',
              bottom: 20,
              left: 0,
              right: 0,
              textAlign: 'center',
              opacity: 0.7,
              fontSize: 14,
              margin: 0,
            }}
          >
            Look at the star · {dotIndex + 1} of {DOTS.length}
            {!faceFound ? ' · face not found' : ''}
          </p>
        </>
      )}

      {stage === 'head' && (
        <>
          <div
            aria-live="polite"
            style={{ position: 'absolute', left: '50%', top: '50%', width: 0, height: 0 }}
          >
            <div
              className="calib-ring"
              style={{
                position: 'absolute',
                left: 0,
                top: 0,
                width: 72,
                height: 72,
                borderRadius: '50%',
                border: '3px solid #7ec8a3',
                boxSizing: 'border-box',
                transform: 'translate(-50%, -50%)',
                animation: `calib-ring ${HEAD_MS}ms linear forwards`,
              }}
            />
            <div
              style={{
                position: 'absolute',
                left: 0,
                top: 0,
                transform: 'translate(-50%, -52%)',
                fontSize: 30,
                lineHeight: 1,
                color: '#ffe27a',
              }}
            >
              ★
            </div>
          </div>
          <p
            style={{
              position: 'absolute',
              top: '62%',
              left: 0,
              right: 0,
              textAlign: 'center',
              fontSize: 18,
              margin: 0,
              padding: '0 24px',
            }}
          >
            Keep your eyes on the star and slowly turn your head left and right, then nod.
            {!faceFound ? ' · face not found' : ''}
          </p>
        </>
      )}

      {stage === 'finishing' && (
        <div style={panel} role="status">
          <h2 style={{ fontSize: '1.4rem', margin: 0 }}>Mapping your screen…</h2>
        </div>
      )}

      {stage === 'ok' && (
        <div style={panel} role="status">
          <div style={{ fontSize: 56, color: '#7ec8a3', lineHeight: 1 }} aria-hidden="true">
            ✓
          </div>
          <h2 style={{ fontSize: '1.6rem', margin: '0.5rem 0 0' }}>Screen mapped ✓</h2>
          <div style={{ display: 'flex', gap: 12, justifyContent: 'center', marginTop: 18 }}>
            {onTest && (
              <button
                type="button"
                onClick={handleTest}
                autoFocus
                style={{
                  minHeight: 48,
                  padding: '0 24px',
                  borderRadius: 14,
                  border: 'none',
                  background: '#7ec8a3',
                  color: '#0c121c',
                  fontWeight: 700,
                  cursor: 'pointer',
                }}
              >
                Test it
              </button>
            )}
            <button
              type="button"
              onClick={handleDone}
              style={{
                minHeight: 48,
                padding: '0 24px',
                borderRadius: 14,
                border: '1px solid rgba(255,255,255,0.35)',
                background: 'transparent',
                color: '#f4f7fb',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              Done
            </button>
          </div>
        </div>
      )}

      {stage === 'fail' && (
        <div style={panel} role="alert">
          <h2 style={{ fontSize: '1.5rem', margin: '0 0 0.6rem' }}>
            {failReason === 'server'
              ? "Couldn't reach the server – retry"
              : "Couldn't see your eyes – retry"}
          </h2>
          <p style={{ opacity: 0.85, lineHeight: 1.5 }}>
            Face the camera with light in front of you, remove glare from glasses if you can, and
            look at each star.
          </p>
          <div style={{ display: 'flex', gap: 12, justifyContent: 'center', marginTop: 18 }}>
            <button
              type="button"
              onClick={() => onRetry?.()}
              autoFocus
              style={{
                minHeight: 48,
                padding: '0 24px',
                borderRadius: 14,
                border: 'none',
                background: '#7ec8a3',
                color: '#0c121c',
                fontWeight: 700,
                cursor: 'pointer',
              }}
            >
              Retry
            </button>
            <button
              type="button"
              onClick={() => {
                exitPageFullscreen();
                onDone?.({ ok: false, skipped: true });
              }}
              style={{
                minHeight: 48,
                padding: '0 24px',
                borderRadius: 14,
                border: '1px solid rgba(255,255,255,0.35)',
                background: 'transparent',
                color: '#f4f7fb',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              Skip (basic mode)
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
