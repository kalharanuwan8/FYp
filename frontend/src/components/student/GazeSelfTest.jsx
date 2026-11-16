import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * PLAN 8 — guided gaze self-test (frontend only, no new endpoint).
 *
 * Six steps x 4 s, head still: look at the centre (ON), just past the LEFT edge (off),
 * just past the RIGHT edge (off), ABOVE the screen (off), DOWN at the desk/phone (off),
 * and the centre again (ON). Each step is judged from `frames_debug[].on_screen` in the
 * normal heartbeats (received through `subscribeHeartbeat`); a step passes when most
 * frames in its last 2 s match the expected state. Only pass/fail is shown.
 *
 * Props:
 *  - open
 *  - onClose()
 *  - onRecalibrate()                 (parent closes the test and restarts calibration)
 *  - subscribeHeartbeat(fn) -> off   (fn(response, { loopStartMs }); see useHeartbeatBus)
 */
const STEP_MS = 4000;
const SCORE_WINDOW_MS = 2000; // last 2 s of each step
const GRACE_MS = 2500; // wait for the final heartbeats to arrive before judging
const MIN_FRAMES = 2;
const PASS_RATIO = 0.6;
const APPROX_FRAME_MS = 333;

const STEPS = [
  {
    key: 'centre',
    label: 'Centre',
    expectOn: true,
    prompt: 'Look at the star in the middle of the screen',
    anchor: { x: 50, y: 50, glyph: '★' },
  },
  {
    key: 'left',
    label: 'Just past the left edge',
    expectOn: false,
    prompt: 'Look just past the LEFT edge of your screen, with your eyes only',
    anchor: { x: 1.5, y: 50, glyph: '◀' },
  },
  {
    key: 'right',
    label: 'Just past the right edge',
    expectOn: false,
    prompt: 'Look just past the RIGHT edge of your screen, with your eyes only',
    anchor: { x: 98.5, y: 50, glyph: '▶' },
  },
  {
    key: 'up',
    label: 'Above the screen',
    expectOn: false,
    prompt: 'Look ABOVE the top of your screen, with your eyes only',
    anchor: { x: 50, y: 2.5, glyph: '▲' },
  },
  {
    key: 'down',
    label: 'Down at the desk or phone',
    expectOn: false,
    prompt: 'Look DOWN at your desk or phone, as if checking a message',
    anchor: { x: 50, y: 97, glyph: '▼' },
  },
  {
    key: 'centre2',
    label: 'Back to the centre',
    expectOn: true,
    prompt: 'Look back at the star in the middle of the screen',
    anchor: { x: 50, y: 50, glyph: '★' },
  },
];

function exitPageFullscreen() {
  // Undo only the page-level fullscreen that calibration started.
  if (document.fullscreenElement !== document.documentElement) return;
  try {
    const p = document.exitFullscreen?.();
    if (p && typeof p.catch === 'function') p.catch(() => {});
  } catch {
    /* best-effort */
  }
}

/** Judge one step from the frames collected inside its scoring window. */
function judgeStep(step, frames) {
  let match = 0;
  let total = 0;
  frames.forEach((f) => {
    if (!f.face) {
      // No face while looking away counts as "not on screen"; while expecting ON it is a miss.
      total += 1;
      if (!step.expectOn) match += 1;
      return;
    }
    if (typeof f.on !== 'boolean') return; // blink / no verdict: neutral
    total += 1;
    if (f.on === step.expectOn) match += 1;
  });
  if (total < MIN_FRAMES) return { pass: false, noData: true };
  return { pass: match / total >= PASS_RATIO, noData: false };
}

const btnBase = {
  minHeight: 48,
  padding: '0 24px',
  borderRadius: 14,
  fontWeight: 700,
  fontSize: 15,
  cursor: 'pointer',
};
const btnPrimary = { ...btnBase, border: 'none', background: '#7ec8a3', color: '#0c121c' };
const btnGhost = {
  ...btnBase,
  fontWeight: 600,
  border: '1px solid rgba(255,255,255,0.35)',
  background: 'transparent',
  color: '#f4f7fb',
};

function GazeSelfTestRun({ open, onClose, onRecalibrate, subscribeHeartbeat }) {
  // 'intro' -> 'running' -> 'checking' -> 'result'
  const [stage, setStage] = useState('intro');
  const [stepIndex, setStepIndex] = useState(0);
  const [stepLeftSec, setStepLeftSec] = useState(Math.ceil(STEP_MS / 1000));
  const [results, setResults] = useState([]);
  const startRef = useRef(0);
  const framesRef = useRef([]); // {abs (performance.now ms), face, on}


  // Collect frames from heartbeats while a run is in progress.
  useEffect(() => {
    if (!open || (stage !== 'running' && stage !== 'checking') || !subscribeHeartbeat) {
      return undefined;
    }
    const off = subscribeHeartbeat((res, info) => {
      const list = res?.frames_debug;
      if (!Array.isArray(list) || list.length === 0) return;
      const arrived = performance.now();
      const loopStartMs = info?.loopStartMs;
      list.forEach((f, i) => {
        // Prefer the exact client capture time (t = seconds since the telemetry loop began);
        // otherwise approximate from arrival order.
        const abs =
          Number.isFinite(loopStartMs) && Number.isFinite(f?.t)
            ? loopStartMs + f.t * 1000
            : arrived - (list.length - 1 - i) * APPROX_FRAME_MS - APPROX_FRAME_MS;
        framesRef.current.push({ abs, face: Boolean(f?.face), on: f?.on_screen });
      });
    });
    return off;
  }, [open, stage, subscribeHeartbeat]);

  const finish = useCallback(() => {
    const start = startRef.current;
    const out = STEPS.map((step, i) => {
      const end = start + (i + 1) * STEP_MS;
      const from = end - SCORE_WINDOW_MS;
      const inWindow = framesRef.current.filter((f) => f.abs >= from && f.abs < end);
      return { key: step.key, ...judgeStep(step, inWindow) };
    });
    setResults(out);
    setStage('result');
  }, []);

  // Step sequencer + countdown.
  useEffect(() => {
    if (!open || stage !== 'running') return undefined;
    const id = setInterval(() => {
      const elapsed = performance.now() - startRef.current;
      const idx = Math.floor(elapsed / STEP_MS);
      if (idx >= STEPS.length) {
        clearInterval(id);
        setStage('checking');
        return;
      }
      setStepIndex(idx);
      setStepLeftSec(Math.max(1, Math.ceil((STEP_MS - (elapsed - idx * STEP_MS)) / 1000)));
    }, 100);
    return () => clearInterval(id);
  }, [open, stage]);

  // Wait for the last heartbeats, then judge.
  useEffect(() => {
    if (!open || stage !== 'checking') return undefined;
    const id = setTimeout(finish, GRACE_MS);
    return () => clearTimeout(id);
  }, [open, stage, finish]);

  const begin = useCallback(() => {
    framesRef.current = [];
    setResults([]);
    setStepIndex(0);
    setStepLeftSec(Math.ceil(STEP_MS / 1000));
    startRef.current = performance.now();
    setStage('running');
  }, []);

  const close = useCallback(() => {
    exitPageFullscreen();
    onClose?.();
  }, [onClose]);

  const recalibrate = useCallback(() => {
    onRecalibrate?.();
  }, [onRecalibrate]);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') close();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, close]);

  if (!open) return null;

  const step = STEPS[Math.min(stepIndex, STEPS.length - 1)];
  const passedCount = results.filter((r) => r.pass).length;
  const allPassed = results.length > 0 && passedCount === STEPS.length;
  const panel = { textAlign: 'center', maxWidth: 520, padding: 24 };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Gaze self-test"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 95,
        background: 'rgba(8, 12, 20, 0.94)',
        color: '#f4f7fb',
        fontFamily: 'Georgia, "Times New Roman", serif',
        display: 'grid',
        placeItems: 'center',
      }}
    >
      {stage === 'intro' && (
        <div style={panel}>
          <h2 style={{ fontSize: '1.6rem', margin: '0 0 0.6rem' }}>Quick gaze test</h2>
          <p style={{ opacity: 0.85, lineHeight: 1.5 }}>
            Keep your head still and follow the prompts with your eyes only: the centre, just past
            the left and right edges, above the screen, down at your desk, then the centre again.
            Each step takes 4 seconds.
          </p>
          <div style={{ display: 'flex', gap: 12, justifyContent: 'center', marginTop: 18 }}>
            <button type="button" onClick={begin} autoFocus style={btnPrimary}>
              Start test
            </button>
            <button type="button" onClick={close} style={btnGhost}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {stage === 'running' && (
        <>
          <div
            key={step.key + stepIndex}
            aria-hidden="true"
            style={{
              position: 'absolute',
              left: `${step.anchor.x}%`,
              top: `${step.anchor.y}%`,
              transform: 'translate(-50%, -50%)',
              fontSize: step.expectOn ? 34 : 28,
              lineHeight: 1,
              color: step.expectOn ? '#ffe27a' : '#7ec8a3',
              opacity: step.expectOn ? 1 : 0.8,
            }}
          >
            {step.anchor.glyph}
          </div>
          <div style={panel} role="status" aria-live="polite">
            <p style={{ opacity: 0.6, fontSize: 14, margin: '0 0 8px' }}>
              Step {stepIndex + 1} of {STEPS.length} · {stepLeftSec}s
            </p>
            <h2 style={{ fontSize: '1.5rem', margin: 0, lineHeight: 1.35 }}>{step.prompt}</h2>
            <p style={{ opacity: 0.6, fontSize: 13, marginTop: 14 }}>Keep your head still.</p>
          </div>
          <button
            type="button"
            onClick={close}
            style={{ ...btnGhost, position: 'absolute', bottom: 20, minHeight: 40, fontSize: 14 }}
          >
            Cancel
          </button>
        </>
      )}

      {stage === 'checking' && (
        <div style={panel} role="status">
          <h2 style={{ fontSize: '1.4rem', margin: 0 }}>Checking…</h2>
        </div>
      )}

      {stage === 'result' && (
        <div style={panel}>
          <h2 style={{ fontSize: '1.6rem', margin: '0 0 0.8rem' }}>
            {allPassed ? 'Gaze detection looks good ✓' : 'Some directions were missed'}
          </h2>
          <ul style={{ listStyle: 'none', padding: 0, margin: '0 auto', maxWidth: 340, textAlign: 'left' }}>
            {STEPS.map((s, i) => {
              const r = results[i];
              const ok = Boolean(r?.pass);
              return (
                <li
                  key={s.key}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 10,
                    padding: '6px 0',
                    borderBottom: '1px solid rgba(255,255,255,0.08)',
                  }}
                >
                  <span
                    aria-label={ok ? 'passed' : 'missed'}
                    style={{
                      width: 24,
                      fontSize: 20,
                      fontWeight: 700,
                      color: ok ? '#7ec8a3' : '#f08a8a',
                    }}
                  >
                    {ok ? '✓' : '✗'}
                  </span>
                  <span>{s.label}</span>
                  {r?.noData && (
                    <span style={{ opacity: 0.55, fontSize: 12 }}> · no data</span>
                  )}
                </li>
              );
            })}
          </ul>
          <div
            style={{
              display: 'flex',
              gap: 12,
              justifyContent: 'center',
              flexWrap: 'wrap',
              marginTop: 20,
            }}
          >
            {!allPassed && onRecalibrate && (
              <button type="button" onClick={recalibrate} autoFocus style={btnPrimary}>
                Recalibrate
              </button>
            )}
            <button type="button" onClick={begin} style={allPassed ? btnPrimary : btnGhost}>
              Run again
            </button>
            <button type="button" onClick={close} style={btnGhost}>
              Done
            </button>
          </div>
          {onRecalibrate && allPassed && (
            <p style={{ marginTop: 14 }}>
              <button
                type="button"
                onClick={recalibrate}
                style={{
                  background: 'none',
                  border: 'none',
                  color: '#f4f7fb',
                  opacity: 0.65,
                  textDecoration: 'underline',
                  cursor: 'pointer',
                  fontSize: 13,
                }}
              >
                Recalibrate anyway
              </button>
            </p>
          )}
        </div>
      )}
    </div>
  );
}

/** Mounting only while open gives every run a fresh state. */
export default function GazeSelfTest(props) {
  if (!props.open) return null;
  return <GazeSelfTestRun {...props} />;
}
