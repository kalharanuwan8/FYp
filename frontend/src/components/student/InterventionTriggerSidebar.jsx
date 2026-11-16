import { useCallback, useEffect, useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

const TRIGGERS = [
  {
    key: 'ambient',
    tier: 1,
    local: 'ambient',
    label: 'Gentle reminder',
    detail: 'A small banner. The video keeps playing.',
  },
  {
    key: 'pacing',
    tier: 2,
    local: 'pacing',
    label: 'Pacing pause',
    detail: 'Pauses the lesson until they tap to continue.',
  },
  {
    key: 'milestone',
    tier: 3,
    local: 'milestone',
    label: 'Checkpoint question',
    detail: 'One question, then back to the lesson.',
  },
  {
    key: 'pace',
    local: 'pace',
    label: 'Slow the video',
    detail: 'Offers to play the lesson a little slower.',
  },
  {
    key: 'break',
    local: 'break',
    label: 'Short break',
    detail: 'A timed stretch break.',
  },
  {
    key: 'noise',
    local: 'noise',
    label: 'Noisy room',
    detail: 'Asks them to use headphones or move.',
  },
];

/**
 * Manual intervention sidebar for the video lesson.
 * Sits on the left edge of the video stage (including fullscreen) so each
 * prompt can be shown on demand during a demonstration.
 *
 * Tier 1–3 try the live session first. If the session cannot fire one
 * (still starting, another prompt pending, demo bypass off), the same
 * overlay is shown locally so the demonstration still works.
 * Break, pace, and noise are always local: the server picks the tier-4
 * variant itself and cannot force a noise notice.
 */
export default function InterventionTriggerSidebar({
  sessionReady = false,
  onShowLocal,
  onTriggerTier,
  onSimulateIgnoreChange,
}) {
  const [open, setOpen] = useState(true);
  const [busyKey, setBusyKey] = useState(null);
  const [note, setNote] = useState(null);
  const [simulateIgnore, setSimulateIgnore] = useState(false);

  useEffect(() => {
    const onKey = (e) => {
      if (e.ctrlKey && e.shiftKey && (e.key === 'I' || e.key === 'i')) {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

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

  const handleTrigger = useCallback(
    async (item) => {
      setNote(null);
      if (item.tier && sessionReady && onTriggerTier) {
        setBusyKey(item.key);
        try {
          await onTriggerTier(item.tier);
          return;
        } catch {
          onShowLocal?.(item.local);
          setNote('Shown on screen. The session did not record this one.');
          return;
        } finally {
          setBusyKey(null);
        }
      }
      onShowLocal?.(item.local);
      if (!sessionReady) {
        setNote('Preview only — the lesson session is still starting.');
      }
    },
    [onShowLocal, onTriggerTier, sessionReady]
  );

  return (
    <div
      className="absolute top-0 left-0 h-full z-40 flex items-start pointer-events-none"
      style={{
        transform: open ? 'translateX(0)' : 'translateX(-100%)',
        transition: 'transform 0.25s ease',
        width: 'min(18rem, 88vw)',
      }}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls="intervention-trigger-sidebar"
        className="pointer-events-auto absolute top-1/4 -right-9 w-9 min-h-36 rounded-r-xl bg-primary text-on-primary shadow-lift cursor-pointer flex flex-col items-center justify-center gap-1 text-[11px] font-bold"
        style={{ writingMode: 'vertical-rl' }}
        title="Show interventions (Ctrl+Shift+I)"
      >
        {open ? (
          <ChevronLeft className="w-4 h-4" aria-hidden="true" />
        ) : (
          <ChevronRight className="w-4 h-4" aria-hidden="true" />
        )}
        <span>Interventions</span>
      </button>

      <aside
        id="intervention-trigger-sidebar"
        aria-label="Trigger an intervention"
        aria-hidden={!open}
        className="pointer-events-auto h-full w-full overflow-y-auto border-r border-border bg-surface/95 shadow-lift text-xs"
      >
        <div className="px-4 pt-4 pb-2">
          <p className="font-display font-bold text-sm text-text">Show an intervention</p>
          <p className="mt-1 text-[11px] text-text-muted leading-relaxed">
            These are the same prompts a student sees. The lesson reacts the same way:
            a reminder stays on screen, and a pause or quiz stops the video.
          </p>
        </div>

        <div className="px-3 pb-3 space-y-2">
          {TRIGGERS.map((item) => (
            <button
              key={item.key}
              type="button"
              disabled={busyKey === item.key}
              onClick={() => handleTrigger(item)}
              className="w-full text-left rounded-xl bg-primary-soft text-primary px-3 py-2.5 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <span className="block font-bold">{item.label}</span>
              <span className="block mt-0.5 font-medium text-text-muted">{item.detail}</span>
            </button>
          ))}
        </div>

        <label className="mx-3 mb-3 flex items-start gap-2 min-h-11 cursor-pointer text-text font-semibold">
          <input
            type="checkbox"
            checked={simulateIgnore}
            onChange={(e) => toggleIgnore(e.target.checked)}
            className="w-4 h-4 mt-0.5"
          />
          <span>
            Leave the prompt up
            <span className="block font-normal text-text-muted">
              Buttons on the prompt stop working, so you can talk over it.
            </span>
          </span>
        </label>

        {note && (
          <p className="mx-4 mb-3 text-text-muted font-medium" role="status">
            {note}
          </p>
        )}
      </aside>
    </div>
  );
}
