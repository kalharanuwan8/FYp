import { useCallback, useEffect, useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import sessionService from '../../services/sessionService';

const TIER_BUTTONS = [
  { key: 't1', label: 'T1 Ambient cue', tier: 1 },
  { key: 't2', label: 'T2 Pacing pause', tier: 2 },
  { key: 't3', label: 'T3 Milestone quiz', tier: 3 },
  { key: 't4p', label: 'T4 Content pacing', tier: 4 },
  { key: 't4b', label: 'T4 Break', local: 'break' },
  { key: 'noise', label: 'Noise notice', local: 'noise' },
];

const fmt = (v, digits = 2) =>
  typeof v === 'number' && Number.isFinite(v) ? v.toFixed(digits) : '—';

/** Mini screen rectangle with a dot at the estimated gaze point (sx, sy in 0..1, may overshoot). */
function GazeMap({ gaze }) {
  const sx = gaze?.sx;
  const sy = gaze?.sy;
  const has = typeof sx === 'number' && typeof sy === 'number';
  // Allow the dot to sit a little outside the rectangle so "off screen" is visible.
  const px = has ? Math.max(-0.2, Math.min(1.2, sx)) : 0.5;
  const py = has ? Math.max(-0.2, Math.min(1.2, sy)) : 0.5;
  const onScreen = gaze?.on_screen;
  const color = !has ? '#94a3b8' : onScreen ? '#22c55e' : '#ef4444';
  return (
    <div className="px-6 py-3">
      <div
        className="relative w-full border-2 border-border rounded-md bg-bg"
        style={{ aspectRatio: '16 / 9', overflow: 'visible' }}
        aria-label={has ? (onScreen ? 'Gaze on screen' : 'Gaze off screen') : 'No gaze estimate'}
      >
        <span
          className="absolute rounded-full"
          style={{
            width: 12,
            height: 12,
            left: `calc(${px * 100}% - 6px)`,
            top: `calc(${py * 100}% - 6px)`,
            background: color,
            boxShadow: `0 0 0 3px ${color}33`,
            transition: 'left 0.25s linear, top 0.25s linear',
          }}
        />
        <span className="absolute left-1 top-0.5 text-[9px] text-text-muted">screen</span>
      </div>
    </div>
  );
}

/**
 * Examiner demo sidebar — right-edge slide-out with a visible "Demo" tab (Ctrl+Shift+D
 * toggles too). Rendered only when the backend reports `demo_mode` (GET /session/demo-config).
 *
 * Props:
 *  - onTriggerTier(tier, { force: true })  → Promise (backend forced trigger)
 *  - onTriggerLocal('break' | 'noise')     → fire a client-side intervention
 *  - onSimulateIgnoreChange(boolean)       → parent makes overlays non-interactive
 *  - gazeDebug                             → heartbeat `gaze_debug`
 *  - position 'fixed' (default) | 'absolute' (inside a relative stage)
 */
export default function DemoPanel({
  sessionId,
  lastVerdict,
  mlMode,
  confidence,
  gazeDebug,
  onTriggerTier,
  onTriggerLocal,
  onSimulateIgnoreChange,
  position = 'fixed',
}) {
  const [demoMode, setDemoMode] = useState(false);
  const [open, setOpen] = useState(false);
  const [simulateIgnore, setSimulateIgnore] = useState(false);
  const [busyKey, setBusyKey] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    sessionService
      .getDemoConfig()
      .then((cfg) => {
        if (!cancelled) setDemoMode(Boolean(cfg?.demo_mode));
      })
      .catch(() => {
        if (!cancelled) setDemoMode(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!demoMode) return undefined;
    const onKey = (e) => {
      if (e.ctrlKey && e.shiftKey && (e.key === 'D' || e.key === 'd')) {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [demoMode]);

  // Never leave overlays frozen if the panel unmounts with "simulate ignore" on.
  useEffect(
    () => () => {
      onSimulateIgnoreChange?.(false);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );

  const toggleIgnore = (checked) => {
    setSimulateIgnore(checked);
    onSimulateIgnoreChange?.(checked);
  };

  const handleButton = useCallback(
    async (btn) => {
      setError(null);
      if (btn.local) {
        onTriggerLocal?.(btn.local);
        return;
      }
      if (!onTriggerTier) return;
      setBusyKey(btn.key);
      try {
        await onTriggerTier(btn.tier, { force: true });
      } catch (err) {
        setError(err?.response?.data?.error || err?.message || 'Failed to trigger intervention');
      } finally {
        setBusyKey(null);
      }
    },
    [onTriggerTier, onTriggerLocal]
  );

  if (!demoMode) return null;

  const verdict = lastVerdict ?? '—';
  const verdictU = String(verdict).toUpperCase();
  const verdictColor =
    verdictU === 'DISTRACTED' ? 'text-danger' : verdictU === 'FOCUSED' ? 'text-success' : 'text-text';

  return (
    <div
      className={`${position} top-0 right-0 h-full z-[85] flex items-start pointer-events-none`}
      style={{
        // The tab hangs off the left edge, so the closed state keeps only the tab visible.
        transform: open ? 'translateX(0)' : 'translateX(100%)',
        transition: 'transform 0.25s ease',
        width: 'min(20rem, 92vw)',
      }}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls="demo-sidebar-body"
        className="pointer-events-auto absolute top-1/3 -left-9 w-9 min-h-24 rounded-l-xl bg-primary text-on-primary shadow-lift cursor-pointer flex flex-col items-center justify-center gap-1 text-[11px] font-bold"
        style={{ writingMode: 'vertical-rl' }}
        title="Demo panel (Ctrl+Shift+D)"
      >
        {open ? (
          <ChevronRight className="w-4 h-4" aria-hidden="true" />
        ) : (
          <ChevronLeft className="w-4 h-4" aria-hidden="true" />
        )}
        <span>Demo</span>
      </button>

      <aside
        id="demo-sidebar-body"
        aria-label="Demo panel"
        aria-hidden={!open}
        className="pointer-events-auto h-full w-full overflow-y-auto border-l border-border bg-surface shadow-lift text-xs"
      >
        <div className="px-4 pt-4 pb-2 flex items-center justify-between">
          <p className="font-display font-bold text-sm text-text">Demo panel</p>
          <span className="text-[10px] text-text-muted">Ctrl+Shift+D</span>
        </div>

        <div className="px-4 pb-3 grid grid-cols-2 gap-2">
          {TIER_BUTTONS.map((btn) => (
            <button
              key={btn.key}
              type="button"
              disabled={!sessionId && !btn.local ? true : busyKey === btn.key}
              onClick={() => handleButton(btn)}
              className="min-h-11 rounded-xl bg-primary-soft text-primary font-bold px-2 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {btn.label}
            </button>
          ))}
        </div>

        <label className="mx-4 mb-2 flex items-center gap-2 min-h-11 cursor-pointer text-text font-semibold">
          <input
            type="checkbox"
            checked={simulateIgnore}
            onChange={(e) => toggleIgnore(e.target.checked)}
            className="w-4 h-4"
          />
          Simulate ignore
          <span className="font-normal text-text-muted">(T1 → T2 auto-escalation)</span>
        </label>

        {error && (
          <p className="mx-4 mb-2 text-warning font-medium" role="alert">
            {error}
          </p>
        )}

        <div className="border-t border-border pt-2">
          <p className="px-4 pt-1 text-[11px] font-bold text-text-muted uppercase tracking-wide">
            Live gaze
          </p>
          <GazeMap gaze={gazeDebug} />
          <dl className="px-4 pb-4 space-y-1 text-text-muted font-mono">
            <Row label="Gaze" value={gazeDebug?.on_screen == null ? '—' : gazeDebug.on_screen ? 'on screen' : 'OFF screen'} />
            <Row label="off_dwell" value={gazeDebug ? `${fmt(gazeDebug.off_dwell_sec, 1)} s` : '—'} />
            <Row label="p_model" value={fmt(gazeDebug?.p_model)} />
            <Row label="p_gaze" value={fmt(gazeDebug?.p_gaze)} />
            <Row label="source" value={gazeDebug?.source ?? '—'} />
            <Row label="mapped" value={gazeDebug ? (gazeDebug.calibrated ? 'screen' : gazeDebug.mode || 'fallback') : '—'} />
            <div className="flex justify-between gap-2">
              <dt>Verdict</dt>
              <dd className={`font-bold ${verdictColor}`}>{verdict}</dd>
            </div>
            <Row label="Model" value={mlMode ?? '—'} />
            <Row
              label="Confidence"
              value={confidence != null ? `${Math.round(Number(confidence) * 100)}%` : '—'}
            />
            <Row label="Session" value={sessionId ?? '—'} />
          </dl>
        </div>
      </aside>
    </div>
  );
}

function Row({ label, value }) {
  return (
    <div className="flex justify-between gap-2">
      <dt>{label}</dt>
      <dd className="text-text">{value}</dd>
    </div>
  );
}
