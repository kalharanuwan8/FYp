import { useState } from 'react';
import { Check, Lightbulb } from 'lucide-react';
import Dialog from '../common/Dialog';
import { usePreferences } from '../../context/PreferencesContext';
import { celebrateIfAllowed } from '../../utils/celebrate';

/** Tier 3 — one question, graded by the server, then an explicit continue step. */
export default function MilestoneQuiz({ message, payload, onRespond, interventionId }) {
  const options = Array.isArray(payload?.options) ? payload.options : [];
  const [selected, setSelected] = useState(null);
  const [showHint, setShowHint] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState(null);
  const [wasCorrect, setWasCorrect] = useState(null);
  const { reduceMotion } = usePreferences();

  const question =
    payload?.generated_question || message || 'Quick checkpoint — pick the best answer.';

  const handleSubmit = async () => {
    if (selected === null || submitting) return;
    setSubmitting(true);
    const answerLabel = options[selected] ?? String(selected);
    try {
      const res = await onRespond(interventionId, 'reengaged', {
        student_answer: answerLabel,
        selected_option: selected,
        milestone_item_id: payload?.milestone_item_id ?? null,
        defer_clear: true,
      });
      const ok = res?.is_correct;
      setWasCorrect(ok);
      if (ok) {
        setFeedback('Nice work — that matches the lesson! ✨');
        await celebrateIfAllowed({ reduceMotion });
      } else if (ok === false) {
        setFeedback("Not quite — that's okay, you're still learning. Keep going!");
      } else {
        setFeedback('Answer saved — keep going.');
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleContinue = async () => {
    await onRespond(interventionId, 'reengaged', { dismiss_only: true });
  };

  return (
    <Dialog
      title="Quick check"
      description="One question, then back to the lesson."
      allowEscape={false}
    >
      <p className="text-base font-medium text-text leading-relaxed">{question}</p>

      <div className="space-y-2" role="radiogroup" aria-label="Answer choices">
        {options.map((opt, idx) => {
          const isSelected = selected === idx;
          return (
            <button
              key={`${idx}-${opt}`}
              type="button"
              role="radio"
              aria-checked={isSelected}
              disabled={submitting || feedback !== null}
              onClick={() => setSelected(idx)}
              className={`w-full text-left min-h-12 px-4 py-3 rounded-2xl border text-sm transition-colors cursor-pointer flex items-center gap-3 disabled:cursor-default ${
                isSelected
                  ? 'border-primary border-2 bg-primary-soft text-text font-semibold'
                  : 'border-border bg-bg text-text hover:border-primary/50 font-medium'
              }`}
            >
              <span
                className={`w-5 h-5 rounded-full border-2 flex items-center justify-center shrink-0 ${
                  isSelected ? 'border-primary bg-primary text-on-primary' : 'border-border text-transparent'
                }`}
                aria-hidden="true"
              >
                <Check className="w-3 h-3" />
              </span>
              <span className="flex-1">{opt}</span>
            </button>
          );
        })}
      </div>

      {payload?.hint_text && (
        <div className="space-y-2">
          <button
            type="button"
            onClick={() => setShowHint((v) => !v)}
            aria-expanded={showHint}
            className="inline-flex items-center gap-1.5 min-h-11 text-sm font-semibold text-warning cursor-pointer"
          >
            <Lightbulb className="w-4 h-4" aria-hidden="true" />
            {showHint ? 'Hide hint' : 'Show a hint'}
          </button>
          {showHint && (
            <p className="text-sm text-text bg-warning/15 border border-warning/30 rounded-2xl px-3 py-2">
              {payload.hint_text}
            </p>
          )}
        </div>
      )}

      {feedback && (
        <p
          className={`text-sm font-medium ${wasCorrect ? 'text-success' : 'text-text-muted'}`}
          role="status"
          aria-live="polite"
        >
          {feedback}
        </p>
      )}

      {feedback ? (
        <button
          type="button"
          onClick={handleContinue}
          className="w-full min-h-12 rounded-2xl bg-primary text-on-primary text-sm font-semibold cursor-pointer"
        >
          Continue lesson
        </button>
      ) : (
        <div className="flex gap-2 pt-1">
          <button
            type="button"
            disabled={submitting}
            onClick={() => onRespond(interventionId, 'ignored')}
            className="flex-1 min-h-12 rounded-2xl border border-border text-text-muted text-sm font-semibold hover:bg-bg cursor-pointer disabled:opacity-50"
          >
            Skip
          </button>
          <button
            type="button"
            disabled={selected === null || submitting}
            onClick={handleSubmit}
            className="flex-1 min-h-12 rounded-2xl bg-primary text-on-primary text-sm font-semibold cursor-pointer disabled:opacity-50"
          >
            {submitting ? 'Checking…' : 'Check answer'}
          </button>
        </div>
      )}
    </Dialog>
  );
}
