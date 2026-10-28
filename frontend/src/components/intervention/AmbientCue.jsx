import { Hand } from 'lucide-react';

/** Tier 1 — a small, calm prompt at the top of the screen. Non-modal, nothing flashes. */
export default function AmbientCue({ message, onRespond, interventionId }) {
  return (
    <div className="pointer-events-none fixed inset-0 z-[60]">
      <div className="pointer-events-auto absolute top-5 left-1/2 -translate-x-1/2 max-w-md w-[92%] animate-slide-up">
        <div
          className="flex items-center gap-3 rounded-2xl border border-primary/35 bg-learning px-4 py-3 shadow-soft"
          role="status"
          aria-live="polite"
        >
          <span
            className="w-9 h-9 rounded-xl bg-primary-soft text-primary flex items-center justify-center shrink-0 border border-border"
            aria-hidden="true"
          >
            <Hand className="w-4 h-4" />
          </span>
          <p className="text-sm font-medium text-text flex-1">
            {message || 'Ready to continue when you are.'}
          </p>
          <button
            type="button"
            onClick={() => onRespond(interventionId, 'reengaged')}
            className="min-h-11 px-4 rounded-2xl bg-primary text-on-primary text-sm font-semibold cursor-pointer shrink-0"
          >
            I&apos;m here
          </button>
        </div>
      </div>
    </div>
  );
}
