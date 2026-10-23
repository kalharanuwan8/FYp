import { useEffect } from 'react';
import Dialog from '../common/Dialog';

/** Tier 2 — friendly check-in with emoji self-report. Outcomes stay verbatim. */
export default function PacingPrompt({ message, onRespond, interventionId, onPauseContent }) {
  useEffect(() => {
    if (onPauseContent) onPauseContent();
  }, [onPauseContent]);

  const moods = [
    { emoji: '😀', label: 'Going well', outcome: 'reengaged', report: 'good' },
    { emoji: '😐', label: 'Okay', outcome: 'reengaged', report: 'okay' },
    { emoji: '😩', label: 'Tough', outcome: 'reengaged', report: 'tough' },
  ];

  return (
    <Dialog
      title="Quick check-in"
      description={message || "How's it going? Pick how you feel."}
      allowEscape={false}
    >
      <div className="text-center" aria-hidden="true">
        <span className="text-3xl">👋</span>
      </div>

      <div className="grid grid-cols-3 gap-3" role="group" aria-label="How are you feeling">
        {moods.map((m) => (
          <button
            key={m.report}
            type="button"
            onClick={() => onRespond(interventionId, m.outcome, { self_report: m.report })}
            className="flex flex-col items-center gap-2 min-h-[5.5rem] rounded-2xl border border-border bg-bg hover:border-primary hover:bg-primary-soft transition-colors cursor-pointer p-3"
          >
            <span className="text-3xl" aria-hidden="true">
              {m.emoji}
            </span>
            <span className="text-xs font-semibold text-text">{m.label}</span>
          </button>
        ))}
      </div>

      <button
        type="button"
        onClick={() => onRespond(interventionId, 'ignored')}
        className="w-full min-h-11 text-sm font-semibold text-text-muted hover:text-text cursor-pointer"
      >
        Skip for now
      </button>
    </Dialog>
  );
}
