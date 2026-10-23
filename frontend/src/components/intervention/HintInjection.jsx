import { Lightbulb } from 'lucide-react';

/** Tier 3 (quiz) — scaffolded hint connected to the current question. */
export function HintInjectionPanel({ message, payload, onRespond, interventionId }) {
  return (
    <div className="rounded-2xl border border-primary/30 bg-primary-soft p-4 space-y-3 shadow-soft">
      <div className="flex items-center gap-2 text-primary">
        <Lightbulb className="w-4 h-4" aria-hidden="true" />
        <span className="text-sm font-bold">A hint for this question</span>
      </div>
      <p className="text-base text-text font-medium leading-relaxed">
        {payload?.generated_question || message || 'Need a nudge with this one?'}
      </p>
      {payload?.hint_text && (
        <p className="text-sm text-text leading-relaxed bg-surface rounded-xl px-3 py-2 border border-border">
          {payload.hint_text}
        </p>
      )}
      <button
        type="button"
        onClick={() => onRespond(interventionId, 'reengaged')}
        className="min-h-11 px-4 rounded-xl bg-primary hover:bg-primary-hover text-on-primary text-sm font-semibold cursor-pointer"
      >
        Thanks — back to the quiz
      </button>
    </div>
  );
}

export default HintInjectionPanel;
