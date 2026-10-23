import { useEffect, useState } from 'react';

/** Hidden examiner panel — Ctrl+Shift+D */
export default function DemoPanel({
  sessionId,
  lastVerdict,
  mlMode,
  confidence,
  onTriggerTier,
}) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onKey = (e) => {
      if (e.ctrlKey && e.shiftKey && (e.key === 'D' || e.key === 'd')) {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  if (!open) return null;

  return (
    <div className="fixed bottom-4 right-4 z-[80] w-72 rounded-2xl border border-border bg-surface shadow-lift p-4 space-y-3 text-xs animate-fade-in">
      <div className="flex items-center justify-between">
        <p className="font-display font-bold text-sm text-text">Demo panel</p>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="text-text-muted hover:text-text min-h-11 px-2"
          aria-label="Close demo panel"
        >
          Close
        </button>
      </div>
      <dl className="space-y-1 text-text-muted font-mono">
        <div className="flex justify-between gap-2">
          <dt>Session</dt>
          <dd className="text-text">{sessionId ?? '—'}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt>Verdict</dt>
          <dd className="text-text">{lastVerdict ?? '—'}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt>Model</dt>
          <dd className="text-text">{mlMode ?? '—'}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt>Confidence</dt>
          <dd className="text-text">
            {confidence != null ? `${Math.round(Number(confidence) * 100)}%` : '—'}
          </dd>
        </div>
      </dl>
      {onTriggerTier && (
        <div className="grid grid-cols-4 gap-1 pt-1">
          {[1, 2, 3, 4].map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => onTriggerTier(t)}
              className="min-h-11 rounded-xl bg-primary-soft text-primary font-bold cursor-pointer"
            >
              T{t}
            </button>
          ))}
        </div>
      )}
      <p className="text-[10px] text-text-muted">Toggle with Ctrl+Shift+D</p>
    </div>
  );
}
